"""Tasks, homework, tests and project deadlines.

Stored in data/tasks.json. JARVIS never submits schoolwork - this only keeps track of it.
"""

import datetime as dt
import json
import logging
import threading
from pathlib import Path

log = logging.getLogger("jarvis.tasks")

KINDS = ("task", "assignment", "test", "project", "study")


def parse_due(due: str) -> dt.datetime | None:
    """Accepts 'YYYY-MM-DD' (end of that day) or 'YYYY-MM-DD HH:MM' / ISO. Empty -> None."""
    due = (due or "").strip()
    if not due:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = dt.datetime.strptime(due, fmt)
            if fmt == "%Y-%m-%d":
                parsed = parsed.replace(hour=23, minute=59)
            return parsed
        except ValueError:
            continue
    raise ValueError(f"Due date {due!r} must look like 2026-12-01 or 2026-12-01 15:30.")


def describe_due(due: dt.datetime, now: dt.datetime) -> str:
    days = (due.date() - now.date()).days
    clock = "" if (due.hour, due.minute) == (23, 59) else f" at {due:%I:%M %p}".replace(" 0", " ")
    if due < now:
        return f"OVERDUE (was due {due:%a %b %d}{clock})"
    if days == 0:
        return f"due today{clock}"
    if days == 1:
        return f"due tomorrow{clock}"
    if days < 7:
        return f"due {due:%A}{clock} ({days} days)"
    return f"due {due:%a %b %d}{clock} ({days} days)"


class TaskStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.items: list[dict] = []
        if path.exists():
            try:
                self.items = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                log.error("Could not read %s: %s", path, exc)
                path.with_suffix(".corrupt.json").write_bytes(path.read_bytes())

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, title: str, due: str = "", kind: str = "task", subject: str = "", priority: int = 2, notes: str = "") -> dict:
        if not title.strip():
            raise ValueError("A task needs a title.")
        parsed = parse_due(due)
        with self._lock:
            item = {
                "id": max((i["id"] for i in self.items), default=0) + 1,
                "title": title.strip(),
                "kind": kind if kind in KINDS else "task",
                "subject": subject.strip(),
                "due": parsed.isoformat(timespec="minutes") if parsed else None,
                "priority": max(1, min(3, int(priority))),
                "notes": notes.strip(),
                "done": False,
                "created": dt.datetime.now().isoformat(timespec="seconds"),
            }
            self.items.append(item)
            self._save()
            return item

    def get(self, task_id: int) -> dict | None:
        return next((i for i in self.items if i["id"] == task_id), None)

    def set_done(self, task_id: int, done: bool = True) -> dict | None:
        with self._lock:
            item = self.get(task_id)
            if item:
                item["done"] = done
                item["completed"] = dt.datetime.now().isoformat(timespec="seconds") if done else None
                self._save()
            return item

    def delete(self, task_id: int) -> dict | None:
        with self._lock:
            item = self.get(task_id)
            if item:
                self.items.remove(item)
                self._save()
            return item

    def open_items(self, subject: str = "", kind: str = "") -> list[dict]:
        def sort_key(i):
            due = i["due"] or "9999"
            return (due, i["priority"])

        items = [
            i for i in self.items
            if not i["done"]
            and (not subject or subject.lower() in i["subject"].lower())
            and (not kind or i["kind"] == kind)
        ]
        return sorted(items, key=sort_key)

    def format(self, items: list[dict], now: dt.datetime | None = None) -> str:
        now = now or dt.datetime.now()
        lines = []
        for i in items:
            due = describe_due(dt.datetime.fromisoformat(i["due"]), now) if i["due"] else "no due date"
            prio = {1: "high priority", 2: "", 3: "low priority"}[i["priority"]]
            subject = f" [{i['subject']}]" if i["subject"] else ""
            bits = ", ".join(b for b in (due, prio, "done" if i["done"] else "") if b)
            lines.append(f"#{i['id']} {i['kind']}{subject}: {i['title']} - {bits}")
        return "\n".join(lines)
