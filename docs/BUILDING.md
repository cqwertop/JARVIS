# Building the installers (for developers)

Each platform has to be built **on that platform**. PyInstaller can't cross-compile.

| Platform | Command | Output (in `dist/`) | Tested? |
|---|---|---|---|
| Windows | `powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1` | `JARVIS-Setup-<v>.exe` + `.sha256` | ✅ Built and tested: silent install, self-test, upgrade, uninstall |
| macOS | `bash packaging/build_macos.sh` | `JARVIS.app`, `JARVIS-<v>-macOS-<arch>.dmg` | ⚠ Script written, never run |
| Linux | `xvfb-run bash packaging/build_linux.sh` (or without `xvfb-run` on a desktop) | `.tar.gz` + `.deb` | ⚠ Script written, never run |

Every build script stops if any step fails:
1. Run the unit tests.
2. Draw the icons (`packaging/make_icons.py`).
3. Package with PyInstaller (`packaging/jarvis.spec`, one recipe for all three platforms).
4. Run `JARVIS --selftest` on the **packaged** app. It imports every module, opens the audio system, checks the
   keyring and the speech-to-text helper, and builds every setup-guide screen. Results go to
   `$JARVIS_HOME/selftest.txt`.
5. Make the installer.

## Prerequisites

- **Windows:** `.venv` with `requirements.txt` + `requirements-build.txt`, and [Inno Setup 6](https://jrsoftware.org/isdl.php)
  (`winget install JRSoftware.InnoSetup`).
- **macOS:** Python 3.12 with Tk, plus Homebrew (the script installs `portaudio`).
- **Linux:** `python3.12-venv python3-tk portaudio19-dev dpkg-dev`.

## GitHub Actions

`.github/workflows/build.yml` builds all three platforms (Windows, Apple Silicon and Intel Macs, and Linux) on GitHub's
machines. Start it from the Actions tab (**Run workflow**), or push a tag like `v0.9.0`. The installers appear as
downloadable artifacts on the run's page. Nothing is published automatically.

## Notes

- The Claude Agent SDK's bundled 360 MB copy of Claude Code is left out of the package. The "Claude plan" option
  (source installs only) uses the user's own Claude Code.
- `JARVIS_HOME=<folder>` makes the app use a different data folder. Use it for testing so your real data isn't touched.
- Windows test installer that skips the "JARVIS is running" check:
  `ISCC /DTestBuild /O<dir> /FJARVIS-Setup-TEST packaging\windows\jarvis.iss`. Don't distribute it.
- **Not done, and these cost money (ask the owner first):** Windows code signing (removes the SmartScreen warning) and
  an Apple Developer ID for notarization ($99/yr, removes the macOS "can't check" warning).
- Bump the version in `version.py` **and** `packaging/windows/version_info.txt`.
