"""macOS and Linux versions of the things KAIRO does through Windows-only APIs.

Windows keeps its original, tested code in tools.py / voice.py; those modules call into here on other systems.
Everything uses programs that ship with the OS (osascript, afplay, say, open on macOS) or common desktop
tools on Linux (pactl, playerctl, notify-send, gio, loginctl, systemctl, ffplay/mpg123/paplay, espeak-ng/spd-say).
A missing Linux tool produces a clear message naming the package to install, not a crash.
"""

import configparser
import difflib
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger("kairo.platform")
MAC = sys.platform == "darwin"
LINUX = sys.platform.startswith("linux")


class Unsupported(RuntimeError):
    """Raised with a user-readable explanation when this computer lacks what an action needs."""


def _run(cmd: list[str], timeout: float = 15) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _need(*names: str, package_hint: str = "") -> str:
    for n in names:
        path = shutil.which(n)
        if path:
            return path
    hint = f" (install the '{package_hint}' package)" if package_hint else ""
    raise Unsupported(f"This needs {' or '.join(names)}, which isn't installed{hint}.")


def _osascript(script: str) -> str:
    out = _run(["osascript", "-e", script])
    if out.returncode != 0:
        raise Unsupported(out.stderr.strip() or "AppleScript failed")
    return out.stdout.strip()


# --------------------------------------------------------------------------- applications

def _mac_apps() -> dict[str, Path]:
    apps: dict[str, Path] = {}
    for root in (Path("/Applications"), Path("/System/Applications"), Path("/System/Applications/Utilities"),
                 Path.home() / "Applications"):
        if root.exists():
            for app in root.glob("*.app"):
                apps[app.stem] = app
    return apps


def _linux_desktop_entries() -> dict[str, dict]:
    dirs = [Path.home() / ".local/share/applications", Path("/usr/share/applications"),
            Path("/usr/local/share/applications"), Path("/var/lib/flatpak/exports/share/applications"),
            Path.home() / ".local/share/flatpak/exports/share/applications", Path("/var/lib/snapd/desktop/applications")]
    entries: dict[str, dict] = {}
    for d in dirs:
        if not d.exists():
            continue
        for f in d.glob("*.desktop"):
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(f, encoding="utf-8")
                e = cp["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError):
                continue
            if e.get("NoDisplay", "false").lower() == "true" or e.get("Type", "Application") != "Application":
                continue
            name = e.get("Name")
            if name and name not in entries:
                entries[name] = {"id": f.stem, "exec": e.get("Exec", ""), "file": str(f)}
    return entries


def _best_match(key: str, names: list[str]) -> str | None:
    lowered = {n.lower(): n for n in names}
    if key in lowered:
        return lowered[key]
    for cand_lower, cand in sorted(lowered.items(), key=lambda kv: len(kv[0])):
        if cand_lower.startswith(key) or key in cand_lower:
            return cand
    close = difflib.get_close_matches(key, list(lowered), n=1, cutoff=0.6)
    return lowered[close[0]] if close else None


_ALIASES = {"vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
            "browser": "firefox", "terminal": "terminal", "files": "files", "file manager": "files"}


def open_application(name: str) -> str:
    key = name.lower().strip()
    key = _ALIASES.get(key, key)
    if MAC:
        apps = _mac_apps()
        match = _best_match(key, list(apps))
        if not match:
            return f"I couldn't find an app called {name} on this Mac."
        subprocess.Popen(["open", str(apps[match])])
        return f"Opened {match}."
    entries = _linux_desktop_entries()
    match = _best_match(key, list(entries))
    if match:
        entry = entries[match]
        launcher = shutil.which("gtk-launch")
        if launcher:
            subprocess.Popen([launcher, entry["id"]], start_new_session=True)
        elif shutil.which("gio"):
            subprocess.Popen(["gio", "launch", entry["file"]], start_new_session=True)
        else:
            cmd = [a for a in shlex.split(entry["exec"]) if not re.fullmatch(r"%[a-zA-Z]", a)]
            subprocess.Popen(cmd, start_new_session=True)
        return f"Opened {match}."
    exe = shutil.which(key.replace(" ", "-")) or shutil.which(key.replace(" ", ""))
    if exe:
        subprocess.Popen([exe], start_new_session=True)
        return f"Opened {name}."
    return f"I couldn't find an app called {name} on this computer."


def open_path(target: str):
    """Open a file, folder or URL with the default app."""
    if MAC:
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen([_need("xdg-open", package_hint="xdg-utils"), target], start_new_session=True)


# --------------------------------------------------------------------------- sound

def set_volume(level: int):
    if MAC:
        _osascript(f"set volume output volume {level} without output muted")
        return
    if shutil.which("pactl"):
        _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])
        _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
        return
    _run([_need("amixer", package_hint="alsa-utils"), "-q", "sset", "Master", f"{level}%", "unmute"])


def get_volume() -> tuple[int, bool]:
    if MAC:
        vol = int(_osascript("output volume of (get volume settings)"))
        muted = _osascript("output muted of (get volume settings)") == "true"
        return vol, muted
    if shutil.which("pactl"):
        vol_out = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]).stdout
        mute_out = _run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"]).stdout
        m = re.search(r"(\d+)%", vol_out)
        return (int(m.group(1)) if m else 0), "yes" in mute_out.lower()
    out = _run([_need("amixer", package_hint="alsa-utils"), "sget", "Master"]).stdout
    m = re.search(r"\[(\d+)%\]", out)
    return (int(m.group(1)) if m else 0), "[off]" in out


def set_mute(muted: bool):
    if MAC:
        _osascript(f"set volume output muted {'true' if muted else 'false'}")
    elif shutil.which("pactl"):
        _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if muted else "0"])
    else:
        _run([_need("amixer", package_hint="alsa-utils"), "-q", "sset", "Master", "mute" if muted else "unmute"])


def media_control(action: str) -> str:
    if MAC:
        verbs = {"play_pause": "playpause", "next": "next track", "previous": "previous track", "stop": "pause"}
        done = []
        for app in ("Spotify", "Music"):
            running = _osascript(f'application "{app}" is running') == "true"
            if running:
                _osascript(f'tell application "{app}" to {verbs[action]}')
                done.append(app)
        return f"Sent {action} to {', '.join(done)}." if done else "No music app (Spotify or Music) is running."
    cmd = {"play_pause": "play-pause", "next": "next", "previous": "previous", "stop": "stop"}[action]
    _run([_need("playerctl", package_hint="playerctl"), cmd])
    return f"Sent {action}."


# --------------------------------------------------------------------------- power

def power(action: str) -> str:
    if MAC:
        if action == "lock":
            _run(["pmset", "displaysleepnow"])
            return "Locked (screen off)."
        if action == "sleep":
            _run(["pmset", "sleepnow"])
            return "Going to sleep."
        if action in ("shutdown", "restart"):
            verb = "shut down" if action == "shutdown" else "restart"
            _osascript(f'tell application "System Events" to {verb}')
            return f"Asked macOS to {verb}. It may ask to save open work."
        if action == "cancel_shutdown":
            return "On a Mac, cancel from the dialog macOS shows."
    else:
        if action == "lock":
            _run([_need("loginctl", package_hint="systemd"), "lock-session"])
            return "Locked."
        if action == "sleep":
            _run([_need("systemctl", package_hint="systemd"), "suspend"])
            return "Going to sleep."
        if action in ("shutdown", "restart"):
            flag = "-h" if action == "shutdown" else "-r"
            out = _run([_need("shutdown", package_hint="systemd"), flag, "+1"])
            if out.returncode != 0:
                raise Unsupported("This user isn't allowed to schedule a shutdown.")
            return f"{action.title()} in one minute. Say 'cancel shutdown' to stop it."
        if action == "cancel_shutdown":
            _run(["shutdown", "-c"])
            return "Shutdown cancelled."
    return f"Unknown action {action}."


# --------------------------------------------------------------------------- audio playback & fallback voice

def play_audio(path: Path, stop: threading.Event) -> bool:
    """Play an mp3, returning False if stopped early. Raises Unsupported if there's no player."""
    if MAC:
        cmd = ["afplay", str(path)]
    else:
        for player, args in (("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]), ("mpg123", ["-q"]),
                             ("mpv", ["--no-video", "--really-quiet"]), ("cvlc", ["--play-and-exit", "--quiet"])):
            if shutil.which(player):
                cmd = [player, *args, str(path)]
                break
        else:
            raise Unsupported("No audio player found (install the 'mpg123' or 'ffmpeg' package).")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while proc.poll() is None:
        if stop.wait(0.05):
            proc.terminate()
            return False
    return True


def say_offline(text: str, stop: threading.Event) -> bool:
    """Built-in, offline speech (used when the neural voice can't be reached)."""
    if MAC:
        cmd = ["say", text]
    else:
        exe = _need("espeak-ng", "espeak", "spd-say", package_hint="espeak-ng")
        cmd = [exe, "--wait", text] if exe.endswith("spd-say") else [exe, text]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while proc.poll() is None:
        if stop.wait(0.05):
            proc.terminate()
            return False
    return True


def beep():
    if MAC:
        subprocess.Popen(["afplay", "/System/Library/Sounds/Tink.aiff"])
    else:
        sys.stdout.write("\a")


# --------------------------------------------------------------------------- notifications

def notify(title: str, message: str):
    try:
        if MAC:
            safe_t, safe_m = title.replace('"', "'"), message.replace('"', "'")
            _run(["osascript", "-e", f'display notification "{safe_m}" with title "{safe_t}"'])
        elif shutil.which("notify-send"):
            _run(["notify-send", "--app-name=KAIRO", title, message])
    except Exception as exc:
        log.warning("Notification failed: %r", exc)


# --------------------------------------------------------------------------- start at login

def autostart_path() -> Path:
    if MAC:
        return Path.home() / "Library" / "LaunchAgents" / "com.kairo.assistant.plist"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "kairo.desktop"


def set_autostart(enabled: bool, command: list[str]):
    path = autostart_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if MAC:
        args = "".join(f"<string>{a}</string>" for a in command)
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict><key>Label</key><string>com.kairo.assistant</string>'
            f"<key>ProgramArguments</key><array>{args}</array><key>RunAtLoad</key><true/></dict></plist>\n",
            encoding="utf-8",
        )
    else:
        path.write_text(
            "[Desktop Entry]\nType=Application\nName=KAIRO\nComment=Voice assistant\n"
            f"Exec={shlex.join(command)}\nX-GNOME-Autostart-enabled=true\n",
            encoding="utf-8",
        )
