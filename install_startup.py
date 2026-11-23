"""Makes JARVIS start automatically (hidden, in the background) when you log in to Windows.

    .venv\\Scripts\\python.exe install_startup.py            add JARVIS to startup and start it now
    .venv\\Scripts\\python.exe install_startup.py --remove   take JARVIS out of startup

It puts a small launcher, JARVIS.vbs, in your Startup folder. That runs main.py with no window.
Output goes to jarvis.log in this folder. To stop JARVIS, say "goodbye Jarvis" (or end python.exe in Task Manager).
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STARTUP = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
LAUNCHER = STARTUP / "JARVIS.vbs"
PYTHON = HERE / ".venv" / "Scripts" / "python.exe"

# Window style 0 = hidden. Using python.exe (not pythonw) inside a hidden console means the programs
# JARVIS starts (Claude Code, PowerShell) share that hidden console instead of flashing windows.
VBS = f'''Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "{HERE}"
shell.Run """{PYTHON}"" ""{HERE / 'main.py'}"" --log", 0, False
'''


def main():
    if "--remove" in sys.argv:
        LAUNCHER.unlink(missing_ok=True)
        print("JARVIS removed from startup.")
        return
    LAUNCHER.write_text(VBS, encoding="utf-8")
    print(f"Installed: {LAUNCHER}")
    subprocess.Popen(["wscript.exe", str(LAUNCHER)])
    print("JARVIS is starting in the background. Say 'Jarvis' when you need it.")


if __name__ == "__main__":
    main()
