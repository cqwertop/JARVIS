# Installing KAIRO

KAIRO installs like any other app. No programming or terminal knowledge is needed on Windows or Mac.
After installing, a **setup guide** opens and walks you through choosing KAIRO's AI, testing your microphone and
picking a voice. It takes about 3 minutes.

| Your computer | Download | Status |
|---|---|---|
| Windows 10 or 11 (64-bit) | `KAIRO-Setup-<version>.exe` | ✅ Tested |
| Mac (Apple Silicon or Intel, macOS 11+) | `KAIRO-<version>-macOS-arm64.dmg` / `-x86_64.dmg` | ⚠ Builds, but not yet tested on a real Mac |
| Linux (Ubuntu, Debian, Mint, Fedora...) | `kairo_<version>_amd64.deb` or `KAIRO-<version>-linux-x86_64.tar.gz` | ⚠ Builds, but not yet tested on a real Linux desktop |

**What you need:** about 400 MB of free space (plus 2–6 GB if you choose a local AI model), a microphone and
speakers or headphones, and an internet connection for setup.

---

## Windows

1. Double-click **KAIRO-Setup-<version>.exe**.
2. If Windows shows *"Windows protected your PC"*, click **More info** then **Run anyway**. (This appears because
   the installer isn't signed with a paid certificate yet. It doesn't mean anything is wrong.)
3. Click **Next** through the installer. You don't need an administrator password.
4. Leave **Open KAIRO now** ticked and click **Finish**. The setup guide opens.

KAIRO is now in your Start menu. **KAIRO Settings** in the Start menu opens the setup guide again whenever you want
to change something.

**Updating:** run the new installer. Your memories, tasks, settings and keys are kept.

**Uninstalling:** Settings → Apps → KAIRO → Uninstall. You'll be asked whether to delete your personal data too.
The default is to keep it.

Your data lives in `%LOCALAPPDATA%\KAIRO`. Your API keys are in Windows Credential Manager, never in a file.

## Mac

1. Open the **.dmg** file. Choose the `arm64` one for Apple Silicon Macs (M1 or later) and `x86_64` for older Intel
   Macs. Apple menu → About This Mac shows which you have.
2. Drag **KAIRO** onto the **Applications** folder.
3. Open Applications, **right-click** (or Control-click) KAIRO and choose **Open**, then **Open** again.
   You only need to do this the first time, because KAIRO isn't from the App Store.
4. Click **OK** when macOS asks for microphone access.

Your data lives in `~/Library/Application Support/KAIRO`. Your API keys are in your Keychain.

**Uninstalling:** drag KAIRO from Applications to the Bin. To also remove your data, delete the folder above and
the "KAIRO" entries in Keychain Access.

## Linux

**Ubuntu, Debian, Mint, Pop!_OS:** double-click the `.deb` file to open it in your software centre and click
**Install**. Or in a terminal: `sudo apt install ./kairo_<version>_amd64.deb`

**Any other distribution:** unpack the `.tar.gz`, open a terminal in the folder, and run `./install.sh`.
This installs only for you, so no password is needed.

Then open **KAIRO** from your applications menu.

Some features use small system programs. If something doesn't work, install these with your package manager:
`pulseaudio-utils` (volume), `playerctl` (music control), `ffmpeg` (KAIRO's voice), `libnotify-bin` (reminder
pop-ups). On Ubuntu: `sudo apt install pulseaudio-utils playerctl ffmpeg libnotify-bin`

Your data lives in `~/.local/share/kairo`. Your API keys are in your desktop's keyring (GNOME Keyring or KWallet).

**Uninstalling:** `sudo apt remove kairo` (for the .deb), or `~/.local/lib/kairo/uninstall.sh` (for the .tar.gz).

---

## The setup guide, step by step

1. **Welcome**
2. **System check:** looks at your memory, disk space, graphics card, microphones and internet connection, and
   tells you in plain words what will work well.
3. **How should KAIRO think?**
   - **Online AI service:** Claude, ChatGPT (OpenAI), Gemini and others. Fast and smart, and needs an API key. See
     [AI-SERVICES.md](AI-SERVICES.md).
   - **Ollama (on this computer):** free and private, works offline, slower without a strong graphics card.
     The guide shows each model's download size and whether your computer can run it, and asks before downloading.
4. **Your key or model:** paste your key and press **Check key** (free), then pick a model. Or pick an Ollama model.
5. **Voice:** choose your microphone and watch the level meter while you talk. Then pick a voice, press **Play
   sample**, and choose how KAIRO listens:
   - **Conversation (recommended):** say "Kairo" once, then just keep talking.
   - **Wake word:** say "Kairo" every time.
   - **Always listening:** no name needed.
   - **Push to talk:** press Ctrl+Alt+J.
   - **Text only:** type instead of talking.
6. **Extras:** start at login, and show the status panel.
7. **Install:** the guide shows each step with real progress, and you can **Retry**, **Skip** or **Cancel**
   anything that fails.
8. **Done:** press **Start KAIRO**.

Something not working? See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
