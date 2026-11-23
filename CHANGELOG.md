# Changelog

## Session 1 (2026-11-23), branch `dev/session-1`

### Added
- **Conversation mode:** say "Jarvis" once, then follow up without the name for 20 s (configurable).
  Also `wake_word`, `always` and `push_to_talk` modes.
- **Background-speech filtering:** speech that isn't addressed to JARVIS by name goes to the AI marked "maybe",
  and the AI stays silent if it was meant for someone else.
- **Interrupting JARVIS:** say "stop" or "Jarvis, <new request>" while it talks. Speech output can be stopped in
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
- Background speech that mentioned "Jarvis" ran as a command. From the old log: "Amazon Jarvis" opened Amazon,
  and "11 Jarvis", "Ray Jarvis" and "Jarvis G" produced confused replies.
- "Hey Jarvis" + pause + command lost the command. JARVIS was saying "Yes, sir?" while you spoke. It now beeps and
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
