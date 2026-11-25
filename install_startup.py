"""Makes KAIRO start automatically (hidden, in the background) when you log in to Windows.

    .venv\\Scripts\\python.exe install_startup.py            add KAIRO to startup + the Start menu, and start it now
    .venv\\Scripts\\python.exe install_startup.py --remove   take KAIRO out of startup and the Start menu

It puts a small launcher, KAIRO.vbs, in your Startup folder. That runs main.py with no window.
It also adds "KAIRO" to the Start menu, so you can type KAIRO in the Windows search bar to start it, or to bring
its panel back if you hid it. Output goes to kairo.log in this folder.
To stop KAIRO, say "goodbye Kairo" (or right-click its panel -> Quit KAIRO).
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROGRAMS = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
STARTUP = PROGRAMS / "Startup"
LAUNCHER = STARTUP / "KAIRO.vbs"
SHORTCUT = PROGRAMS / "KAIRO.lnk"
ICON = HERE / "packaging" / "assets" / "kairo.ico"
PYTHON = HERE / ".venv" / "Scripts" / "python.exe"

# Window style 0 = hidden. Using python.exe (not pythonw) inside a hidden console means the programs
# KAIRO starts (Claude Code, PowerShell) share that hidden console instead of flashing windows.
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
        f"$s.Description = 'KAIRO voice assistant'; "
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
        print("KAIRO removed from startup and the Start menu.")
        return
    LAUNCHER.write_text(VBS, encoding="utf-8")
    print(f"Installed: {LAUNCHER}")
    make_shortcut()
    subprocess.Popen(["wscript.exe", str(LAUNCHER)])
    print("KAIRO is starting in the background. Say 'Kairo' when you need it.")
    print("Hid the panel? Type KAIRO in the Windows search bar and open it, or press Ctrl+Alt+H.")


if __name__ == "__main__":
    main()
