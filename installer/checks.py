"""System checks for the JARVIS setup wizard (Windows, macOS, Linux).

Each check returns plain values; the wizard turns them into friendly sentences.
Originally written by the installer session; reworked to run inside the packaged app.
"""

import platform
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import psutil

MIN_RAM_GB = 4
MIN_FREE_DISK_GB = 2
OLLAMA_URL = "http://localhost:11434"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


@dataclass
class SystemReport:
    os_name: str = ""
    os_version: str = ""
    cpu_arch: str = ""
    cpu_cores: int = 0
    ram_gb: float = 0.0
    gpu_name: str | None = None
    disk_free_gb: float = 0.0
    internet: bool = False
    microphones: list[str] = field(default_factory=list)
    already_set_up: bool = False
    claude_code_found: bool = False
    ollama_found: bool = False
    ollama_running: bool = False
    ollama_models: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    good_news: list[str] = field(default_factory=list)


def friendly_os() -> tuple[str, str]:
    system = platform.system()
    if system == "Windows":
        build = sys.getwindowsversion().build
        return ("Windows 11" if build >= 22000 else "Windows 10"), f"build {build}"
    if system == "Darwin":
        return "macOS", platform.mac_ver()[0]
    try:
        info = platform.freedesktop_os_release()
        return info.get("NAME", "Linux"), info.get("VERSION_ID", "")
    except OSError:
        return "Linux", platform.release()


def gpu_name() -> str | None:
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join ', '"],
                capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW).stdout.strip()
        elif sys.platform == "darwin":
            out = subprocess.run(["system_profiler", "SPDisplaysDataType"], capture_output=True, text=True,
                                 timeout=20).stdout
            names = [line.split(":", 1)[1].strip() for line in out.splitlines() if "Chipset Model" in line]
            out = ", ".join(names)
        else:
            if not shutil.which("lspci"):
                return None
            out = subprocess.run(["lspci"], capture_output=True, text=True, timeout=10).stdout
            names = [line.split(": ", 1)[1] for line in out.splitlines() if "VGA" in line or "3D controller" in line]
            out = ", ".join(names)
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


def internet_ok(timeout: float = 4.0) -> bool:
    for host in ("api.anthropic.com", "ollama.com", "www.google.com"):
        try:
            with socket.create_connection((host, 443), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def ollama_path() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    candidates = []
    if sys.platform == "win32":
        import os

        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "Programs" / "Ollama" / "ollama.exe")
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Ollama.app/Contents/Resources/ollama"))
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def input_microphones() -> list[str]:
    """Names of devices that can record (outputs are filtered out)."""
    try:
        import pyaudio

        pa = pyaudio.PyAudio()
        try:
            names = []
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    names.append(info["name"])
            return names
        finally:
            pa.terminate()
    except Exception:
        return []


def check_system(data_dir: Path, *, with_gpu: bool = True, with_network: bool = True) -> SystemReport:
    import steps  # local import: steps imports JARVIS modules

    r = SystemReport()
    r.os_name, r.os_version = friendly_os()
    r.cpu_arch = platform.machine() or "unknown"
    r.cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 0
    r.ram_gb = round(psutil.virtual_memory().total / 1024 ** 3, 1)
    r.gpu_name = gpu_name() if with_gpu else None
    data_dir.mkdir(parents=True, exist_ok=True)
    r.disk_free_gb = round(shutil.disk_usage(data_dir).free / 1024 ** 3, 1)
    r.internet = internet_ok() if with_network else False
    r.microphones = input_microphones()
    r.already_set_up = steps.current_settings().get("setup_complete", False)
    r.claude_code_found = shutil.which("claude") is not None
    r.ollama_found = ollama_path() is not None
    status = steps.ollama_status()
    r.ollama_running = status["running"]
    r.ollama_models = status["models"]
    r.ollama_found = r.ollama_found or r.ollama_running

    supported = {"Windows 10", "Windows 11", "macOS"}
    if r.os_name not in supported and sys.platform != "linux":
        r.problems.append(f"{r.os_name} hasn't been tested with JARVIS. It may still work.")
    if r.ram_gb < MIN_RAM_GB:
        r.problems.append(f"This computer has {r.ram_gb} GB of memory. JARVIS needs at least {MIN_RAM_GB} GB.")
    if r.disk_free_gb < MIN_FREE_DISK_GB:
        r.problems.append(f"Only {r.disk_free_gb} GB of free space is left. Please free up at least {MIN_FREE_DISK_GB} GB.")
    if with_network and not r.internet:
        r.problems.append("JARVIS can't reach the internet. Connect to Wi-Fi or a cable, then press Check again. "
                          "(You can still use a local AI model without internet once it's downloaded.)")
    if not r.microphones:
        r.problems.append("No microphone was found. You can still type to JARVIS, or plug one in and press Check again.")

    r.good_news.append(f"{r.os_name} {r.os_version} ({r.cpu_arch}, {r.cpu_cores} processor cores).")
    if r.ram_gb >= MIN_RAM_GB:
        r.good_news.append(f"Memory: {r.ram_gb} GB" + (" - enough to run a local AI model too." if r.ram_gb >= 8 else "."))
    if r.disk_free_gb >= MIN_FREE_DISK_GB:
        r.good_news.append(f"Free space: {r.disk_free_gb} GB.")
    if r.internet:
        r.good_news.append("Internet connection: working.")
    if r.microphones:
        r.good_news.append(f"Microphone found: {r.microphones[0]}" + (f" (and {len(r.microphones) - 1} more)" if len(r.microphones) > 1 else ""))
    if r.already_set_up:
        r.good_news.append("JARVIS is already set up on this computer. You can change your choices here.")
    return r


def describe_results(report: SystemReport) -> str:
    if not report.problems:
        return "Your computer is ready!"
    return "Your computer needs one more thing before JARVIS can start." if len(report.problems) == 1 else \
        "A few things need attention, but you can usually continue."


def ram_needed_gb(model_size_gb: float) -> float:
    """Rough memory needed to run a model of this download size comfortably alongside everything else."""
    return round(model_size_gb * 1.3 + 2.5, 1)
