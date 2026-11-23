# JARVIS Roadmap & Backlog

**Read this first at the start of every development session.** Update "Status" and "Next up" before you finish.

## Status (end of session 1, 2026-11-23)

| Phase | State |
|---|---|
| 1. Repository audit | ✅ Done (findings below) |
| 2. Stability (logging, errors, tests, git) | ✅ Core done. 46 tests, rotating log, health check |
| 3. Core intelligence (model abstraction, memory) | 🟡 Claude API / Claude plan / Ollama + fallback, long-term memory done. Missing: streaming, token/cost tracking, conversation summarization |
| 4. Voice | 🟡 Conversation mode, background filtering, barge-in, mute, HUD done. **Missing: local speech recognition** (needs approval to install) |
| 5. Desktop automation | 🟡 Existing app/web/media/volume/power tools. Missing: window switching, file management, document reading |
| 6. Productivity | 🟡 Tasks, school deadlines, reminders done. Missing: calendar, proactive deadline alerts, daily plan |
| 7. Cross-platform | 🔴 Windows only. Shared code is now guarded, but Linux/macOS adapters are not written or tested |
| 8. Mobile | 🔴 Not started |
| 9. Plugins, research, smart home | 🔴 Not started |
| 10. Polish, installer, packaging | 🔴 Not started |

## Audit findings (session 1)

What existed: about 700 lines of Python. There was a voice loop that required "Jarvis" in every command, Google
speech recognition, an edge-tts voice with a SAPI fallback, Claude through the API or the Claude plan (Agent SDK),
18 Windows tools, Startup-folder autostart, and no tests, git, config or docs.

Problems found in `jarvis.log`:
- 46 of the listening failures were caused by no internet. Cloud speech recognition makes JARVIS deaf offline.
  → Local STT is the top voice priority.
- Background mentions of the name ran as commands. → Fixed (conversation.classify plus `<silent>`).
- "Hey Jarvis" + pause lost the command. → Fixed.
- Recognizer JSONDecodeError was mishandled as a mic failure. → Fixed.

Hardware: i5-8400 (6 cores), 16 GB RAM, **no NVIDIA GPU**. Ollama 0.40 installed, with qwen3:8b, gemma3:4b,
embeddinggemma and others. qwen3:8b on CPU takes about 120 s cold and 12–20 s warm per reply. Claude through the
plan takes about 1–11 s.

## Next up (priority order)

1. **Local speech recognition** (faster-whisper `base.en` or `small.en` + Silero VAD). This makes JARVIS work
   offline and stops audio going to Google. ⚠ Needs approval to install about 200 MB of packages and models. Keep
   Google as a fallback.
2. **Automated fix loop** (maintenance phase 2). health_check finds a failure → new git branch → headless
   `claude -p` with a restricted toolset fixes it → tests run → the branch is kept for review or deleted. Never
   auto-merge. ⚠ Needs approval: it runs unattended and uses plan usage.
3. **Scheduled health check.** A Windows Task Scheduler entry running `health_check.py --notify` every 6 hours.
   ⚠ Needs approval (system change).
4. **Proactive deadlines.** Morning summary at first wake, plus spoken or desktop alerts for items due tomorrow.
5. **Streaming replies.** Start speaking the first sentence while the rest is generated, which cuts perceived
   latency by about 50%.
6. **Calendar** (Google Calendar or local ICS). ⚠ Needs approval for account access.
7. **Desktop automation:** window switching or focusing, file search, open recent projects, "prepare my workspace"
   workflows.
8. **Developer mode tools:** git status, run tests, summarize repo (read-only first).
9. **Phone alerts via ntfy** (free; uses the public ntfy.sh server or self-hosted). Push health-check failures to the
   phone.
10. **Encryption of memory at rest** with Windows DPAPI.

## Larger tracks (need design decisions before work starts)

### Graphical installer (directive 2)
A real cross-platform GUI installer is a substantial project. Proposed approach, which needs the owner's sign-off:
- Package JARVIS with **PyInstaller** (one folder, bundled Python, no terminal).
- Use a **web-tech setup wizard** in a pywebview or Tauri window for the polished UI: system check, AI engine
  choice (Ollama, llama.cpp, Transformers, API), model picker, microphone test and keyring storage.
- Native wrappers: Inno Setup (`.exe`) on Windows, `.dmg` on macOS, AppImage or `.deb` on Linux.
- API keys go to OS credential storage via `keyring` (new dependency).
- ⚠ Important licensing point: the **Claude-plan backend (Claude Code sign-in) is for personal use only**. Anthropic
  doesn't allow apps distributed to other people to run on someone's plan sign-in. A distributed installer must
  offer the API key option and local models, not the plan backend.
- macOS distribution without Gatekeeper warnings needs an Apple Developer ID ($99/yr). ⚠ Paid, so ask first.

### Mobile companion
Android first (Kotlin, foreground service + notification listener), paired over the LAN with a QR code and
end-to-end encryption. For remote access, prefer ntfy or Tailscale over opening ports. iOS: Shortcuts + App Intents
only, because of background execution limits. Requires a mobile dev setup on this PC (Android Studio). ⚠ Ask first.

### Cross-platform
Replace the Windows-only calls (`os.startfile`, `Get-StartApps`, pycaw, SAPI, MCI, `keybd_event`, `shutdown`, the
mutex and RegisterHotKey) with a `platform/` adapter package, then test on real Linux and macOS machines before
claiming support.

## Known limitations
- Barge-in with speakers (no headphones) is best effort. The STOP button and hotkey always work.
- The Ollama fallback's first reply is slow (about 2 min on this CPU). Ollama as the primary backend warms up at
  startup.
- qwen3:8b gets simple arithmetic and context wrong sometimes. It's a fallback, not a replacement.
- Speech recognition needs the internet (see Next up #1).
