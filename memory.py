"""Long-term memory: things you ask KAIRO to remember about you, your preferences and your projects.

Stored in data/memory.json (plain JSON on this PC - you can open, back up or delete it any time).
Search is semantic when the local Ollama embedding model is available (finds "robot arm" when you ask
about "robotics"), and falls back to keyword matching when it isn't.

You stay in control: "what do you remember about me", "forget that", "show me everything you've stored".
"""

import datetime as dt
import difflib
import hashlib
import json
import logging
import math
import re
import threading
import urllib.request
from pathlib import Path

log = logging.getLogger("kairo.memory")

CATEGORIES = ("preference", "project", "person", "school", "device", "fact")


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _words(text: str) -> set[str]:
    stop = {"the", "a", "an", "my", "i", "is", "are", "to", "of", "and", "in", "on", "for", "me", "about", "what", "do", "you"}
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in stop and len(w) > 1}


class Embedder:
    """Text -> vector using Ollama's /api/embed. Disabled automatically if Ollama isn't running."""

    def __init__(self, url: str, model: str, timeout: float = 20):
        self.url, self.model, self.timeout = url.rstrip("/"), model, timeout
        self._available: bool | None = None

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        if self._available is False or not texts:
            return None
        try:
            req = urllib.request.Request(
                self.url + "/api/embed",
                data=json.dumps({"model": self.model, "input": texts}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                vecs = json.loads(resp.read())["embeddings"]
            self._available = True
            return vecs
        except Exception as exc:
            if self._available is not False:
                log.info("Semantic memory search unavailable (%r); using keyword search.", exc)
            self._available = False
            return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class MemoryStore:
    def __init__(self, path: Path, embedder: Embedder | None = None):
        self.path = path
        self.vectors_path = path.with_name(path.stem + "_vectors.json")
        self.embedder = embedder
        self._lock = threading.RLock()
        self.items: list[dict] = self._load(self.path, [])
        self._vectors: dict[str, list[float]] = self._load(self.vectors_path, {})

    @staticmethod
    def _load(path: Path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            backup = path.with_suffix(".corrupt.json")
            log.error("Could not read %s (%s). Kept a copy at %s and started fresh.", path, exc, backup)
            try:
                backup.write_bytes(path.read_bytes())
            except OSError:
                pass
            return default

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)  # atomic: a crash mid-write never leaves a half-written memory file
        live = {self._key(i) for i in self.items}
        self._vectors = {k: v for k, v in self._vectors.items() if k in live}
        self.vectors_path.write_text(json.dumps(self._vectors), encoding="utf-8")

    @staticmethod
    def _key(item: dict) -> str:
        return hashlib.sha1(item["text"].encode()).hexdigest()[:16]

    def _next_id(self) -> int:
        return max((i["id"] for i in self.items), default=0) + 1

    def _ensure_vectors(self, items: list[dict]):
        if not self.embedder:
            return
        missing = [i for i in items if self._key(i) not in self._vectors]
        if missing:
            vecs = self.embedder.embed([i["text"] for i in missing])
            if vecs:
                for item, vec in zip(missing, vecs):
                    self._vectors[self._key(item)] = vec

    # ------------------------------------------------------------------ operations
    def add(self, text: str, category: str = "fact") -> tuple[dict, bool]:
        """Returns (item, is_new). Near-duplicates update the existing memory instead of adding another."""
        text = text.strip()
        if not text:
            raise ValueError("Nothing to remember.")
        category = category if category in CATEGORIES else "fact"
        with self._lock:
            for item in self.items:
                if difflib.SequenceMatcher(None, item["text"].lower(), text.lower()).ratio() > 0.85:
                    item.update(text=text, category=category, updated=_now())
                    self._save()
                    return item, False
            item = {"id": self._next_id(), "text": text, "category": category, "created": _now(), "updated": _now()}
            self.items.append(item)
            self._save()
            return item, True

    def search(self, query: str, limit: int = 8, category: str = "") -> list[dict]:
        with self._lock:
            pool = [i for i in self.items if not category or i["category"] == category]
            if not pool:
                return []
            if not query.strip():
                return sorted(pool, key=lambda i: i["updated"], reverse=True)[:limit]
            scored: list[tuple[float, dict]] = []
            self._ensure_vectors(pool)
            qvec = None
            if self.embedder and self._vectors:
                got = self.embedder.embed([query])
                qvec = got[0] if got else None
            qwords = _words(query)
            for item in pool:
                kw = len(qwords & _words(item["text"] + " " + item["category"])) / (len(qwords) or 1)
                sem = _cosine(qvec, self._vectors[self._key(item)]) if qvec and self._key(item) in self._vectors else 0.0
                score = max(kw, sem)
                threshold = 0.45 if qvec else 0.2
                if score >= threshold:
                    scored.append((score, item))
            scored.sort(key=lambda s: s[0], reverse=True)
            if qvec is not None:
                self._save_vectors_quietly()
            return [i for _, i in scored[:limit]]

    def _save_vectors_quietly(self):
        try:
            self.vectors_path.parent.mkdir(parents=True, exist_ok=True)
            self.vectors_path.write_text(json.dumps(self._vectors), encoding="utf-8")
        except OSError:
            pass

    def delete(self, ids: list[int]) -> list[dict]:
        with self._lock:
            removed = [i for i in self.items if i["id"] in ids]
            self.items = [i for i in self.items if i["id"] not in ids]
            if removed:
                self._save()
            return removed

    def all(self, category: str = "") -> list[dict]:
        with self._lock:
            return [i for i in self.items if not category or i["category"] == category]

    def preferences_summary(self, limit: int = 25) -> str:
        prefs = [i for i in self.all() if i["category"] in ("preference", "person")][-limit:]
        return "\n".join(f"- {i['text']}" for i in prefs)
