# PyInstaller recipe for the KAIRO app - the same file builds Windows, macOS and Linux.
#   pyinstaller packaging/kairo.spec --noconfirm
# Output: dist/KAIRO/ (Windows, Linux) or dist/KAIRO.app (macOS).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
ASSETS = Path(SPECPATH) / "assets"
sys.path.insert(0, str(ROOT))
from version import __version__  # noqa: E402

WIN, MAC = sys.platform == "win32", sys.platform == "darwin"

# speech_recognition converts audio with a small 'flac' program it ships; keep only this platform's copy.
import speech_recognition  # noqa: E402

sr_dir = Path(speech_recognition.__file__).parent
flac = {"win32": ["flac-win32.exe"], "darwin": ["flac-mac"]}.get(sys.platform, ["flac-linux-x86", "flac-linux-x86_64"])
datas = [(str(sr_dir / f), "speech_recognition") for f in flac if (sr_dir / f).exists()]
datas += [(str(sr_dir / "version.txt"), "speech_recognition")] if (sr_dir / "version.txt").exists() else []
datas += [(str(ASSETS / "kairo.png"), "assets")]

local_modules = ["main", "brains", "pro_brain", "voice", "tools", "conversation", "memory", "tasks", "hud", "settings",
                 "credentials", "platform_support", "health_check", "kairo_log", "paths", "providers", "version",
                 "kairo_setup", "checks", "steps", "updater", "update_ui"]
hidden = local_modules + collect_submodules("keyring.backends") + ["edge_tts", "claude_agent_sdk", "mcp", "anthropic"]
if WIN:
    hidden += ["comtypes", "comtypes.client", "comtypes.stream", "pycaw.pycaw", "winsound", "winreg"]

a = Analysis(
    [str(ROOT / "kairo_app.py")],
    pathex=[str(ROOT), str(ROOT / "installer")],
    datas=datas,
    hiddenimports=hidden,
    excludes=["matplotlib", "numpy", "pandas", "scipy", "IPython", "pytest", "PyInstaller"],
    noarchive=False,
)
# The Claude Agent SDK ships its own 360 MB copy of Claude Code. KAIRO uses the Claude Code the user installs
# themselves (only needed for the "Claude plan" option), so leave the bundled copy out.
a.datas = [d for d in a.datas if "_bundled" not in d[0].replace("\\", "/").split("/")]
a.binaries = [b for b in a.binaries if "_bundled" not in b[0].replace("\\", "/").split("/")]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="KAIRO",
    console=False,  # a normal windowed app - no black terminal window
    icon=str(ASSETS / ("kairo.ico" if WIN else "kairo.icns" if MAC else "kairo.png")),
    version=str(Path(SPECPATH) / "windows" / "version_info.txt") if WIN else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="KAIRO", upx=False)

if MAC:
    app = BUNDLE(
        coll,
        name="KAIRO.app",
        icon=str(ASSETS / "kairo.icns"),
        bundle_identifier="com.kairo.assistant",
        version=__version__,
        info_plist={
            "CFBundleShortVersionString": __version__,
            "NSMicrophoneUsageDescription": "KAIRO listens for your voice commands when you turn listening on.",
            "NSAppleEventsUsageDescription": "KAIRO controls apps like Music and Spotify when you ask it to.",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
        },
    )
