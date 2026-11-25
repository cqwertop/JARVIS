"""Where KAIRO keeps things.

Running from source (developer mode): data/ and kairo.log sit next to the code, as before.
Installed app (PyInstaller build): the program folder may be read-only and is replaced on every update, so
personal data lives in the standard per-user place for each operating system:
    Windows  %LOCALAPPDATA%\\KAIRO
    macOS    ~/Library/Application Support/KAIRO
    Linux    $XDG_DATA_HOME/kairo  (usually ~/.local/share/kairo)
Updates and uninstalls never touch that folder unless the user asks for complete removal.
"""

import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

# Read-only resources shipped with KAIRO (code, icons).
APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def user_home_dir() -> Path:
    override = os.environ.get("KAIRO_HOME")  # used by tests and portable installs
    if override:
        return Path(override)
    if not FROZEN:
        return Path(__file__).resolve().parent
    if sys.platform == "win32":
        base, name, old_name = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")), "KAIRO", "JARVIS"
    elif sys.platform == "darwin":
        base, name, old_name = Path.home() / "Library" / "Application Support", "KAIRO", "JARVIS"
    else:
        base, name, old_name = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")), "kairo", "jarvis"
    return _moved_from_old_name(base / old_name, base / name)


def _moved_from_old_name(old: Path, new: Path) -> Path:
    """This app used to be called JARVIS. Move an existing JARVIS data folder to the new name the first time.
    If it can't be moved (e.g. the old app is still running), keep using the old folder so nothing is lost."""
    if new.exists() or not old.is_dir():
        return new
    try:
        old.rename(new)
        return new
    except OSError:
        return old


HOME = user_home_dir()
DATA_DIR = HOME / "data"
LOG_FILE = HOME / "kairo.log"
