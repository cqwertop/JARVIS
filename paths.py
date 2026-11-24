"""Where JARVIS keeps things.

Running from source (developer mode): data/ and jarvis.log sit next to the code, as before.
Installed app (PyInstaller build): the program folder may be read-only and is replaced on every update, so
personal data lives in the standard per-user place for each operating system:
    Windows  %LOCALAPPDATA%\\JARVIS
    macOS    ~/Library/Application Support/JARVIS
    Linux    $XDG_DATA_HOME/jarvis  (usually ~/.local/share/jarvis)
Updates and uninstalls never touch that folder unless the user asks for complete removal.
"""

import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

# Read-only resources shipped with JARVIS (code, icons).
APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def user_home_dir() -> Path:
    override = os.environ.get("JARVIS_HOME")  # used by tests and portable installs
    if override:
        return Path(override)
    if not FROZEN:
        return Path(__file__).resolve().parent
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "JARVIS"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "JARVIS"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "jarvis"


HOME = user_home_dir()
DATA_DIR = HOME / "data"
LOG_FILE = HOME / "jarvis.log"
