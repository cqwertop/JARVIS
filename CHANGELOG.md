# Changelog

## 0.9.1 (2026-11-24) - renamed to KAIRO

### Changed
- **The assistant is now called KAIRO** (it was JARVIS). The wake word is "Kairo"; common mis-hearings such as
  "Cairo" also work. Program, installer, MSIX package, files, data folder and docs all use the new name.

### Upgrading from JARVIS
- Your data folder (`%LOCALAPPDATA%\JARVIS` on Windows) is moved to `%LOCALAPPDATA%\KAIRO` the first time KAIRO runs.
- API keys saved under "JARVIS" in the system password store are moved to "KAIRO" the first time they're used.
- The Windows installer upgrades a JARVIS install in place: it removes the old JARVIS program folder and shortcuts,
  and keeps start at login on if it was on.
- If you changed `wake_words` or `assistant_name` in your own `settings.json`, update those to the new name.

## Session 2 (2026-11-23), branch `dev/session-1`

### Fixed
- A hidden panel (right-click → Hide this panel) could only come back by restarting KAIRO. Now **Ctrl+Alt+H**
  toggles it, and opening KAIRO again (Start menu, Windows search) shows the running copy's panel instead.
  `install_startup.py` adds a **KAIRO** Start menu entry for source installs.
- A flaky provider test: the fake server closed connections with unread data, which resets them on Windows.

### Added
- **Other companies' AI services:** OpenAI, Google Gemini, OpenRouter, Groq, Mistral, DeepSeek, xAI, or any
  OpenAI-compatible API (`providers.py`, `brains.OpenAICompatBrain`, backend `online`). Tools work through standard
  function calling. Models without tool support still talk. API errors are explained in plain words.
- **Setup guide** (`installer/kairo_setup.py`): system check, AI choice with a provider picker, official key
  links, free key check, model list, microphone test, voice samples, listening modes, real download progress with
  Retry/Skip/Cancel. Keys go to the OS keyring (`credentials.py`).
- **Packaged app** (`kairo_app.py`, `packaging/kairo.spec`) with `--selftest`, `--setup` and `--remove-user-data`.
- **Windows installer** (Inno Setup): per-user, no admin, Start menu and desktop shortcuts, optional start at login,
  upgrades keep data, and the uninstaller asks before deleting data.
- **macOS and Linux:** `platform_support.py` adapters, the `.dmg` build script, `.deb` and `.tar.gz` build scripts,
  and a GitHub Actions workflow. **Untested on real machines.**
- Per-user data folders (`paths.py`), `KAIRO_HOME` override, icons, version info.
- Beginner docs: `docs/INSTALLATION.md`, `docs/AI-SERVICES.md`, `docs/TROUBLESHOOTING.md`, `docs/BUILDING.md`.
- Tests for providers and the OpenAI-compatible brain (fake local server). 53 tests in total.

### Changed
- The "Claude plan" option is only offered when running from source (personal use), not in packaged installers.

## Session 1 (2026-11-23), branch `dev/session-1`

### Added
- **Conversation mode:** say "Kairo" once, then follow up without the name for 20 s (configurable).
  Also `wake_word`, `always` and `push_to_talk` modes.
- **Background-speech filtering:** speech that isn't addressed to KAIRO by name goes to the AI marked "maybe",
  and the AI stays silent if it was meant for someone else.
- **Interrupting KAIRO:** say "stop" or "Kairo, <new request>" while it talks. Speech output can be stopped in
  under 0.1 s.
- **On-screen status panel** (listening indicator) with MUTE / STOP / TALK buttons. Global hotkeys
  Ctrl+Alt+M / S / J.
- **Mute** fully closes the microphone.
- **Long-term memory** (`remember`, `recall`, `forget`, `list_all_memories`) with semantic search through the local
  `embeddinggemma`.
- **Tasks and school tracking** (`add_task`, `list_tasks`, `complete_task`, `delete_task`) with due dates and
  overdue flags.
- **Local AI backend (Ollama)** with tool calling, plus **automatic fallback** when Claude is offline or out of usage.
- **Settings file** `data/settings.json` covering voice, personality, listen mode, backends and hotkeys.
- **Health check** (`health_check.py`) with desktop notifications.
- **46 automated tests**, git repository, `requirements.txt`, and the README, ARCHITECTURE and ROADMAP docs.

### Fixed
- Background speech that mentioned "Kairo" ran as a command. From the old log: "Amazon Kairo" opened Amazon,
  and "11 Kairo", "Ray Kairo" and "Kairo G" produced confused replies.
- "Hey Kairo" + pause + command lost the command. KAIRO was saying "Yes, sir?" while you spoke. It now beeps and
  listens.
- Glitches from the recognition service (JSONDecodeError) were treated as microphone failures, which caused a
  5-second pause and a recalibration each time.
- A failed internet connection logged a warning on every phrase (46 lines). This is now limited to one warning every
  5 minutes.
- The log file grew forever. It now rotates at 1 MB.
- `close_application` with a 1–2 letter name could kill many unrelated programs. Short names are now refused.
- `read_notes(0)` returned every note.
- The one-off MCI error 277 on playback is now retried once.
- Personal files (`notes.txt`, `reminders.json`) moved to `data/`, which git ignores.
