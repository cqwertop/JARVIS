"""Finds and installs new KAIRO versions published on GitHub Releases.

How it works:
  - Reads the release list from the GitHub API (no account or key needed).
  - Beta (pre-release) versions are only offered to people already on a beta, unless settings say otherwise
    ("updates": {"include_beta": true}).
  - Picks the file that matches how KAIRO was installed: the .msixbundle for the MSIX package, KAIRO-Setup-*.exe
    for the Windows installer. Running from source, it just points you to the release page (use git pull).
  - Downloads it, checks its SHA-256 against the checksum GitHub publishes for that file, then opens it.
    Windows itself then checks the signature and installs the update; nothing runs silently.

Versions look like 0.10.0 or 0.10.0-beta.1. A beta comes before the final release with the same number.
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import paths
from version import __version__

log = logging.getLogger("kairo.updater")

REPO = "cqwertop/KAIRO"
API_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
FIRST_CHECK_DELAY = 60          # seconds after start-up
CHECK_INTERVAL = 12 * 60 * 60   # then every 12 hours

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-.]?(?:b|beta)\.?(\d+))?$", re.IGNORECASE)


class UpdateError(Exception):
    """Something went wrong; the message is written for the user."""


def parse_version(text: str) -> tuple | None:
    """'0.10.0' -> (0, 10, 0, inf); '0.10.0-beta.2' / 'v0.10.0b2' -> (0, 10, 0, 2). None if not a version."""
    m = _VERSION.match(text.strip())
    if not m:
        return None
    major, minor, patch, beta = m.groups()
    return int(major), int(minor), int(patch), int(beta) if beta is not None else float("inf")


def is_beta(text: str) -> bool:
    v = parse_version(text)
    return v is not None and v[3] != float("inf")


def install_kind() -> str:
    """'msix' (installed from the .msixbundle), 'installer' (Windows installer), or 'source'."""
    if not paths.FROZEN:
        return "source"
    if sys.platform == "win32" and "\\WindowsApps\\" in sys.executable:
        return "msix"
    if sys.platform == "win32":
        return "installer"
    return "other"


@dataclass
class Release:
    version: str
    name: str
    page_url: str
    notes: str
    prerelease: bool
    asset_name: str | None = None
    asset_url: str | None = None
    asset_size: int = 0
    sha256: str | None = None


def _asset_for(kind: str, assets: list[dict]) -> dict | None:
    pattern = {"msix": r"\.msixbundle$", "installer": r"^KAIRO-Setup-.*\.exe$"}.get(kind)
    if not pattern:
        return None
    return next((a for a in assets if re.search(pattern, a.get("name", ""), re.IGNORECASE)), None)


def pick_update(releases: list[dict], current: str = __version__, include_beta: bool | None = None,
                kind: str | None = None) -> Release | None:
    """The newest release that's newer than `current` (and has a file for this install type, when it needs one)."""
    kind = kind or install_kind()
    if include_beta is None:
        include_beta = is_beta(current)
    current_v = parse_version(current)
    if current_v is None:
        return None
    best, best_v = None, current_v
    for r in releases:
        if r.get("draft"):
            continue
        v = parse_version(r.get("tag_name", ""))
        if v is None or v <= best_v:
            continue
        if (r.get("prerelease") or v[3] != float("inf")) and not include_beta:
            continue
        asset = _asset_for(kind, r.get("assets", []))
        if kind in ("msix", "installer") and asset is None:
            continue  # this release has nothing this install can use
        digest = (asset or {}).get("digest") or ""
        best_v = v
        best = Release(
            version=r["tag_name"].lstrip("vV"),
            name=r.get("name") or r["tag_name"],
            page_url=r.get("html_url") or RELEASES_PAGE,
            notes=(r.get("body") or "").strip(),
            prerelease=bool(r.get("prerelease")),
            asset_name=(asset or {}).get("name"),
            asset_url=(asset or {}).get("browser_download_url"),
            asset_size=int((asset or {}).get("size") or 0),
            sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None,
        )
    return best


def fetch_releases(timeout: float = 15) -> list[dict]:
    req = urllib.request.Request(API_URL, headers={"User-Agent": "KAIRO-updater",
                                                   "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise UpdateError("GitHub is limiting update checks right now. Try again in an hour.") from exc
        raise UpdateError(f"GitHub answered with error {exc.code}. Try again later.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Couldn't reach GitHub to check for updates. Check your internet connection.") from exc
    except ValueError as exc:
        raise UpdateError("GitHub sent an answer KAIRO couldn't read. Try again later.") from exc


def check(include_beta: bool | None = None) -> Release | None:
    return pick_update(fetch_releases(), include_beta=include_beta)


def download(release: Release, progress: Callable[[int, int], None] | None = None,
             folder: Path | None = None) -> Path:
    """Download the update file and verify its checksum. Returns the file's path."""
    if not release.asset_url or not release.asset_name:
        raise UpdateError("This update has no file for your kind of install. Download it from the release page.")
    if not release.sha256:
        raise UpdateError("This update has no published checksum, so KAIRO won't install it automatically. "
                          "Download it from the release page instead.")
    folder = folder or Path(tempfile.gettempdir()) / "KAIRO-update"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / Path(release.asset_name).name
    partial = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    req = urllib.request.Request(release.asset_url, headers={"User-Agent": "KAIRO-updater"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(partial, "wb") as out:
            total = int(resp.headers.get("Content-Length") or release.asset_size or 0)
            done = 0
            while chunk := resp.read(256 * 1024):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError("The download didn't finish. Check your internet connection and try again.") from exc
    if digest.hexdigest() != release.sha256:
        partial.unlink(missing_ok=True)
        raise UpdateError("The downloaded file doesn't match its published checksum, so it was deleted. "
                          "Try again later.")
    partial.replace(target)
    return target


def launch(path: Path):
    """Open the downloaded update. Windows shows its own install screen and checks the file's signature."""
    if sys.platform == "win32":
        os.startfile(str(path))
    else:
        subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", str(path)])


class BackgroundChecker:
    """Checks shortly after start-up and then every 12 hours. Calls on_found(release) once per new version."""

    def __init__(self, on_found: Callable[[Release], None], include_beta: bool | None = None):
        self._on_found = on_found
        self._include_beta = include_beta
        self._announced: set[str] = set()
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True, name="update-check").start()

    def _loop(self):
        delay = FIRST_CHECK_DELAY
        while not self._stop.wait(delay):
            delay = CHECK_INTERVAL
            try:
                release = check(self._include_beta)
            except UpdateError as exc:
                log.info("Update check skipped: %s", exc)
                continue
            except Exception as exc:
                log.warning("Update check failed: %r", exc)
                continue
            if release and release.version not in self._announced:
                self._announced.add(release.version)
                log.info("Update available: %s (you have %s).", release.version, __version__)
                try:
                    self._on_found(release)
                except Exception as exc:
                    log.warning("Update notice failed: %r", exc)

    def stop(self):
        self._stop.set()
