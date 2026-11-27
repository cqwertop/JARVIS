"""Entry point of the installed KAIRO app (what KAIRO.exe / KAIRO.app runs).

    KAIRO                  first run: the setup wizard; afterwards: start the assistant
    KAIRO --setup          open the setup wizard again
    KAIRO --selftest       check the packaged app works (used by the build scripts), then exit
    KAIRO <main.py flags>  e.g. --backend ollama, --mode text
"""

import sys
from pathlib import Path

import paths

sys.path.insert(0, str(paths.APP_DIR / "installer"))


def _show_crash(exc: BaseException):
    """The installed app has no console, so tell the user in a window and leave details in the log."""
    import logging
    import traceback

    logging.getLogger("kairo").critical("KAIRO crashed:\n%s", traceback.format_exc())
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("KAIRO had a problem",
                             f"KAIRO stopped because of an unexpected problem:\n\n{type(exc).__name__}: {exc}\n\n"
                             f"Details are in {paths.LOG_FILE}. Starting KAIRO again usually helps.")
        root.destroy()
    except Exception:
        pass


def selftest() -> int:
    """Import everything the packaged app needs and exercise the parts that don't need a person present."""
    import importlib
    import tempfile

    results = []
    for mod in ("main", "brains", "pro_brain", "voice", "tools", "conversation", "memory", "tasks", "hud", "settings",
                "credentials", "platform_support", "health_check", "kairo_setup", "checks", "steps", "updater", "update_ui",
                "speech_recognition", "pyaudio", "edge_tts", "anthropic", "claude_agent_sdk", "psutil", "PIL",
                "keyring"):
        importlib.import_module(mod)
        results.append(mod)
    if sys.platform == "win32":
        for mod in ("comtypes", "pycaw.pycaw", "winsound"):
            importlib.import_module(mod)

    import settings
    import tools

    s = settings.load(Path(tempfile.mkdtemp()) / "settings.json")
    assert s["listen_mode"] == "conversation"
    assert len(tools.ALL_TOOLS) >= 26
    import pyaudio

    pa = pyaudio.PyAudio()
    devices = pa.get_device_count()
    pa.terminate()
    import keyring

    backend = type(keyring.get_keyring()).__name__
    import kairo_setup

    kairo_setup.selftest()
    import speech_recognition as sr

    flac = sr.get_flac_converter()  # speech recognition needs this bundled program
    summary = (f"selftest ok: {len(results)} modules, {len(tools.ALL_TOOLS)} tools, {devices} audio devices, "
               f"keyring={backend}, flac={Path(flac).name}, data={paths.DATA_DIR}")
    print(summary)
    paths.HOME.mkdir(parents=True, exist_ok=True)
    (paths.HOME / "selftest.txt").write_text(summary + "\n", encoding="utf-8")  # windowed app has no console
    return 0


def remove_user_data() -> int:
    """Complete removal (only when the user ticks it in the uninstaller): saved keys, settings, memories, tasks, logs."""
    import shutil

    import credentials
    import providers

    for pid in providers.PROVIDERS:
        credentials.delete(providers.credential_name(pid))
    if paths.FROZEN or "KAIRO_HOME" in __import__("os").environ:  # never delete a developer's source folder
        shutil.rmtree(paths.HOME, ignore_errors=True)
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if "--remove-user-data" in argv:
        return remove_user_data()
    if "--selftest" in argv:
        try:
            return selftest()
        except BaseException as exc:
            import traceback

            paths.HOME.mkdir(parents=True, exist_ok=True)
            (paths.HOME / "selftest.txt").write_text("selftest FAILED\n" + traceback.format_exc(), encoding="utf-8")
            raise SystemExit(1) from exc
    import settings

    if "--setup" in argv or not settings.load().get("setup_complete"):
        import kairo_log

        kairo_log.setup(to_file=True)
        import kairo_setup

        return kairo_setup.run(argv)
    import main as kairo_main

    return kairo_main.main() or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - last-chance handler for the windowed app
        _show_crash(exc)
        sys.exit(1)
