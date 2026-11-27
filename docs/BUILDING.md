# Building the installers (for developers)

Each platform has to be built **on that platform**. PyInstaller can't cross-compile.

| Platform | Command | Output (in `dist/`) | Tested? |
|---|---|---|---|
| Windows | `powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1` | `KAIRO-Setup-<v>.exe` + `.sha256` | ✅ Built and tested: silent install, self-test, upgrade, uninstall |
| Windows (MSIX) | `powershell -ExecutionPolicy Bypass -File packaging\build_msix.ps1 [-Rebuild]` | `KAIRO-<v>.msixbundle` + `KAIRO.cer` | ⚠ Manifest checked by makeappx; full app not yet installed from the bundle |
| macOS | `bash packaging/build_macos.sh` | `KAIRO.app`, `KAIRO-<v>-macOS-<arch>.dmg` | ⚠ Script written, never run |
| Linux | `xvfb-run bash packaging/build_linux.sh` (or without `xvfb-run` on a desktop) | `.tar.gz` + `.deb` | ⚠ Script written, never run |

Every build script stops if any step fails:
1. Run the unit tests.
2. Draw the icons (`packaging/make_icons.py`).
3. Package with PyInstaller (`packaging/kairo.spec`, one recipe for all three platforms).
4. Run `KAIRO --selftest` on the **packaged** app. It imports every module, opens the audio system, checks the
   keyring and the speech-to-text helper, and builds every setup-guide screen. Results go to
   `$KAIRO_HOME/selftest.txt`.
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
- `KAIRO_HOME=<folder>` makes the app use a different data folder. Use it for testing so your real data isn't touched.
- Windows test installer that skips the "KAIRO is running" check:
  `ISCC /DTestBuild /O<dir> /FKAIRO-Setup-TEST packaging\windows\kairo.iss`. Don't distribute it.
- **Not done, and these cost money (ask the owner first):** Windows code signing (removes the SmartScreen warning) and
  an Apple Developer ID for notarization ($99/yr, removes the macOS "can't check" warning).
- Bump the version in `version.py` **and** `packaging/windows/version_info.txt`. Betas are `X.Y.Z-beta.N`
  (`filevers=(X, Y, Z, N)`); final releases are `X.Y.Z` (`filevers=(X, Y, Z, 1000)`).
- **Releases and auto-update:** tag releases `vX.Y.Z` or `vX.Y.Z-beta.N` and mark betas as pre-releases. KAIRO's
  updater reads the GitHub release list and needs the `.msixbundle` (and/or `KAIRO-Setup-*.exe`) attached to the
  release. It verifies downloads with the SHA-256 that GitHub shows for each file, so upload files unchanged.
  The MSIX bundle must be signed with the same certificate as before, or Windows won't accept it as an update.
- **MSIX bundle:** signed with a self-signed certificate (`CN=KAIRO Project`), created in your user certificate
  store on the first build and reused after that. Windows only installs the bundle on PCs that trust `KAIRO.cer`:
  import it into **Local Machine > Trusted People** (needs admin), then double-click the `.msixbundle`. The package
  turns off file and registry write virtualization, so it uses the same `%LOCALAPPDATA%\KAIRO` data folder and
  Run-key start-at-login as the Inno Setup build. It adds a `kairo` command, which start-at-login uses.
