"""The real work behind each setup-wizard step.

Every function either succeeds or raises StepError with a message written for a beginner: what happened
and what to try. Runs inside the packaged KAIRO app, so everything KAIRO needs is already present -
nothing here installs Python packages. (Friendly-error approach from the original installer session.)
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import credentials
import paths
import providers
import settings as settings_mod

OLLAMA_URL = "http://localhost:11434"

# Local models KAIRO works well with. Sizes are the download sizes listed on ollama.com (approximate);
# the real total shows during the download. All of these support tool use (checked again after download).
OLLAMA_CATALOG = [
    {"name": "qwen3:4b", "label": "Qwen 3 (4B)", "size_gb": 2.5,
     "about": "Good all-rounder for most computers. Recommended."},
    {"name": "qwen3:8b", "label": "Qwen 3 (8B)", "size_gb": 5.2,
     "about": "Smarter, but slower without a graphics card. Needs 16 GB of memory."},
    {"name": "llama3.2:3b", "label": "Llama 3.2 (3B)", "size_gb": 2.0,
     "about": "Smallest and fastest. Best for older computers."},
]
EMBEDDING_MODEL = {"name": "embeddinggemma", "size_gb": 0.6,
                   "about": "Helps KAIRO search its memory by meaning (optional)."}

VOICES = [
    ("en-GB-RyanNeural", "Ryan - British, calm (the classic KAIRO)"),
    ("en-GB-SoniaNeural", "Sonia - British"),
    ("en-US-GuyNeural", "Guy - American"),
    ("en-US-JennyNeural", "Jenny - American"),
    ("en-AU-WilliamNeural", "William - Australian"),
    ("en-IN-PrabhatNeural", "Prabhat - Indian English"),
]


class StepError(Exception):
    """A step failed. The message explains what happened and what to try."""


# --------------------------------------------------------------------------- settings

def current_settings() -> dict:
    path = settings_mod.SETTINGS_FILE
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}
    return {}


def save_settings(changes: dict, log: Callable[[str], None] = print):
    try:
        settings_mod.update(changes)
    except OSError as exc:
        raise StepError(f"Your settings couldn't be saved ({exc.strerror}). Check that the disk isn't full.") from exc
    log(f"Saved your choices to {settings_mod.SETTINGS_FILE}.")


# --------------------------------------------------------------------------- online AI keys

def check_key(provider_id: str, key: str, base_url: str = "", log: Callable[[str], None] = print) -> list[str]:
    """Make sure a key works (free - it only lists models) and return the chat models it can use."""
    info = providers.PROVIDERS[provider_id]
    log(f"Checking your key with {info['label']} (this doesn't cost anything)...")
    if info["kind"] == "anthropic":
        import anthropic

        try:
            page = anthropic.Anthropic(api_key=key, max_retries=1, timeout=20).models.list(limit=100)
            models = [m.id for m in page.data]
        except anthropic.AuthenticationError as exc:
            raise StepError("Anthropic didn't accept this key. Copy the whole key again (it starts with 'sk-ant-'), "
                            "with no spaces, and check it hasn't been deleted on the Anthropic Console.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise StepError("This key works but isn't allowed to use Claude yet. On the Anthropic Console, check "
                            "Billing - API use needs credit added.") from exc
        except anthropic.APIConnectionError as exc:
            raise StepError("Couldn't reach Anthropic. Check your internet connection and press Retry.") from exc
    else:
        try:
            models = providers.list_models(base_url or info["base_url"], key, info["label"])
        except providers.ProviderError as exc:
            raise StepError(str(exc)) from exc
    if not models:
        raise StepError(f"The key works, but {info['label']} didn't list any chat models for it.")
    log(f"The key works ({len(models)} models available).")
    return models


def store_key(provider_id: str, key: str, log: Callable[[str], None] = print):
    try:
        credentials.put(providers.credential_name(provider_id), key)
    except RuntimeError as exc:
        raise StepError(str(exc)) from exc
    store = {"win32": "Windows Credential Manager", "darwin": "your Mac's Keychain"}.get(sys.platform, "your keyring")
    log(f"Your key is stored safely in {store} - not in any KAIRO file.")


# --------------------------------------------------------------------------- Ollama

def _ollama(path: str, payload: dict | None = None, timeout: float = 10):
    req = urllib.request.Request(OLLAMA_URL + path, data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def ollama_status() -> dict:
    try:
        with _ollama("/api/tags", timeout=2) as resp:
            models = [m["name"] for m in json.loads(resp.read())["models"]]
        return {"running": True, "models": models}
    except Exception:
        return {"running": False, "models": []}


def has_model(name: str, models: list[str]) -> bool:
    return name in models or f"{name}:latest" in models


def start_ollama(log: Callable[[str], None] = print) -> bool:
    """Ollama is installed but not running: start it in the background and wait up to 20 s."""
    import checks

    exe = checks.ollama_path()
    if not exe:
        return False
    log("Starting Ollama...")
    kwargs = {"creationflags": checks.NO_WINDOW} if sys.platform == "win32" else {"start_new_session": True}
    subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    for _ in range(40):
        if ollama_status()["running"]:
            log("Ollama is running.")
            return True
        time.sleep(0.5)
    return False


def model_capabilities(name: str) -> list[str]:
    try:
        with _ollama("/api/show", {"model": name}) as resp:
            return json.loads(resp.read()).get("capabilities", [])
    except Exception:
        return []


def pull_model(name: str, progress: Callable[[str, int, int], None], cancelled: Callable[[], bool],
               log: Callable[[str], None] = print):
    """Download a model, reporting real progress (bytes done, bytes total) from Ollama."""
    if not ollama_status()["running"] and not start_ollama(log):
        raise StepError("Ollama isn't running. Open the Ollama app (or install it from ollama.com), then press Retry.")
    log(f"Downloading {name}. You can keep using your computer while this runs.")
    try:
        resp = _ollama("/api/pull", {"model": name, "stream": True}, timeout=60)
    except urllib.error.URLError as exc:
        raise StepError("Couldn't start the download. Check your internet connection and press Retry.") from exc
    last_status = ""
    with resp:
        for raw in resp:
            if cancelled():
                raise StepError("Download cancelled. Press Retry to continue it - finished parts are kept.")
            line = json.loads(raw)
            if "error" in line:
                raise StepError(f"Ollama couldn't download {name}: {line['error']}. Press Retry.")
            status = line.get("status", "")
            progress(status, int(line.get("completed", 0) or 0), int(line.get("total", 0) or 0))
            if status != last_status and not status.startswith("pulling "):
                log(status)
            last_status = status
    if not has_model(name, ollama_status()["models"]):
        raise StepError(f"{name} didn't finish downloading. Press Retry - it continues where it stopped.")
    log(f"{name} is downloaded.")


def test_model(name: str, log: Callable[[str], None] = print) -> str:
    log(f"Asking {name} to say hello (the first answer can take a minute while it loads)...")
    try:
        with _ollama("/api/chat", {"model": name, "stream": False, "think": False,
                                   "messages": [{"role": "user", "content": "Say hello in five words or fewer."}]},
                     timeout=300) as resp:
            reply = json.loads(resp.read())["message"]["content"].strip()
    except urllib.error.HTTPError as exc:
        if "think" in exc.read().decode(errors="ignore").lower():
            with _ollama("/api/chat", {"model": name, "stream": False,
                                       "messages": [{"role": "user", "content": "Say hello in five words or fewer."}]},
                         timeout=300) as resp:
                reply = json.loads(resp.read())["message"]["content"].strip()
        else:
            raise StepError(f"{name} didn't answer ({exc.code}). Press Retry.") from exc
    except Exception as exc:
        raise StepError(f"{name} didn't answer. Your computer may be low on memory - try a smaller model.") from exc
    if "tools" not in model_capabilities(name):
        log(f"Note: {name} can't use tools, so it can chat but can't control your computer.")
    log(f'{name} says: "{reply}"')
    return reply


# --------------------------------------------------------------------------- microphone & speaker

def mic_level_meter(device_name: str, seconds: float, on_level: Callable[[float], None],
                    stop: Callable[[], bool] = lambda: False) -> float:
    """Record for a few seconds and report loudness 0..1 as it goes. Nothing is saved. Returns the peak."""
    import array
    import math

    import pyaudio

    def rms(data: bytes) -> float:
        samples = array.array("h", data)
        return math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0

    pa = pyaudio.PyAudio()
    index = None
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("maxInputChannels", 0) > 0 and (not device_name or info["name"] == device_name):
            index = i
            break
    try:
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1600,
                         input_device_index=index)
    except Exception as exc:
        pa.terminate()
        hint = {"darwin": " On a Mac, allow it in System Settings > Privacy & Security > Microphone.",
                "win32": " On Windows, check Settings > Privacy & security > Microphone."}.get(sys.platform, "")
        raise StepError("KAIRO couldn't open the microphone." + hint) from exc
    peak = 0.0
    try:
        end = time.monotonic() + seconds
        while time.monotonic() < end and not stop():
            data = stream.read(1600, exception_on_overflow=False)
            level = min(1.0, rms(data) / 6000)
            peak = max(peak, level)
            on_level(level)
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
    return peak


def speak_sample(voice: str, text: str = "Hello! I'm KAIRO, your personal assistant. I'm ready to help."):
    from voice import Speaker

    s = settings_mod.load()["voice"]
    speaker = Speaker(neural_voice=voice, rate=s["rate"], volume=s["volume"], fallback_voice=s["fallback_voice"])
    speaker.say(text)


# --------------------------------------------------------------------------- start at login

def kairo_command() -> list[str]:
    if paths.FROZEN and sys.platform == "win32" and "\\WindowsApps\\" in sys.executable:
        # Installed from the MSIX bundle: Windows won't start the packaged exe by its path, so use the
        # "kairo" command the package adds (see packaging/msix/AppxManifest.xml).
        return [str(Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
                    / "Microsoft" / "WindowsApps" / "kairo.exe")]
    if paths.FROZEN:
        return [sys.executable]
    return [sys.executable, str(paths.APP_DIR / "main.py"), "--log"]


def set_start_at_login(enabled: bool, log: Callable[[str], None] = print):
    cmd = kairo_command()
    try:
        if sys.platform == "win32":
            import subprocess as sp
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                 winreg.KEY_SET_VALUE)
            with key:
                if enabled:
                    winreg.SetValueEx(key, "KAIRO", 0, winreg.REG_SZ, sp.list2cmdline(cmd))
                else:
                    try:
                        winreg.DeleteValue(key, "KAIRO")
                    except FileNotFoundError:
                        pass
        else:
            import platform_support

            platform_support.set_autostart(enabled, cmd)
    except OSError as exc:
        raise StepError(f"Couldn't change the start-at-login setting ({exc}).") from exc
    log("KAIRO will start when you log in." if enabled else "KAIRO won't start by itself when you log in.")


def start_at_login_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, "KAIRO")
                return True
        except OSError:
            return False
    import platform_support

    return platform_support.autostart_path().exists()


def launch_kairo(extra: list[str] | None = None):
    cmd = kairo_command() + (extra or [])
    kwargs = {"creationflags": 0x00000008 | 0x00000200} if sys.platform == "win32" else {"start_new_session": True}
    if sys.platform == "win32" and not paths.FROZEN:
        pyw = Path(sys.executable).with_name("pythonw.exe")
        if pyw.exists():
            cmd[0] = str(pyw)
    subprocess.Popen(cmd, cwd=str(paths.APP_DIR), **kwargs)
