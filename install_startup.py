"""Makes JARVIS start automatically (hidden, in the background) when you log in to Windows.

    .venv\\Scripts\\python.exe install_startup.py            add JARVIS to startup + the Start menu, and start it now
    .venv\\Scripts\\python.exe install_startup.py --remove   take JARVIS out of startup and the Start menu

It puts a small launcher, JARVIS.vbs, in your Startup folder. That runs main.py with no window.
It also adds "JARVIS" to the Start menu, so you can type JARVIS in the Windows search bar to start it, or to bring
its panel back if you hid it. Output goes to jarvis.log in this folder.
To stop JARVIS, say "goodbye Jarvis" (or right-click its panel -> Quit JARVIS).
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROGRAMS = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
STARTUP = PROGRAMS / "Startup"
LAUNCHER = STARTUP / "JARVIS.vbs"
SHORTCUT = PROGRAMS / "JARVIS.lnk"
ICON = HERE / "packaging" / "assets" / "jarvis.ico"
PYTHON = HERE / ".venv" / "Scripts" / "python.exe"

# Window style 0 = hidden. Using python.exe (not pythonw) inside a hidden console means the programs
# JARVIS starts (Claude Code, PowerShell) share that hidden console instead of flashing windows.
VBS = f'''Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "{HERE}"
shell.Run """{PYTHON}"" ""{HERE / 'main.py'}"" --log", 0, False
'''


def make_shortcut():
    """Start menu entry that runs the same hidden launcher (a second launch just shows the panel)."""
    def q(p):  # PowerShell single-quoted string
        return "'" + str(p).replace("'", "''") + "'"

    wscript = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"
    script = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({q(SHORTCUT)}); "
        f"$s.TargetPath = {q(wscript)}; "
        f"$s.Arguments = {q(chr(34) + str(LAUNCHER) + chr(34))}; "
        f"$s.WorkingDirectory = {q(HERE)}; "
        f"$s.Description = 'JARVIS voice assistant'; "
        + (f"$s.IconLocation = {q(ICON)}; " if ICON.exists() else "")
        + "$s.Save()"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True)
    if result.returncode == 0 and SHORTCUT.exists():
        print(f"Start menu entry: {SHORTCUT}")
    else:
        print(f"Couldn't add the Start menu entry: {result.stderr.strip()}")


def main():
    if "--remove" in sys.argv:
        LAUNCHER.unlink(missing_ok=True)
        SHORTCUT.unlink(missing_ok=True)
        print("JARVIS removed from startup and the Start menu.")
        return
    LAUNCHER.write_text(VBS, encoding="utf-8")
    print(f"Installed: {LAUNCHER}")
    make_shortcut()
    subprocess.Popen(["wscript.exe", str(LAUNCHER)])
    print("JARVIS is starting in the background. Say 'Jarvis' when you need it.")
    print("Hid the panel? Type JARVIS in the Windows search bar and open it, or press Ctrl+Alt+H.")


if __name__ == "__main__":
    main()
