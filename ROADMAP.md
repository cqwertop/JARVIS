# KAIRO Roadmap & Backlog

**Read this first at the start of every development session.** Update "Status" and "Next up" before you finish.

## Status (session 2, 2026-11-23)

| Phase | State |
|---|---|
| 1. Repository audit | ✅ Done (findings below) |
| 2. Stability (logging, errors, tests, git) | ✅ Core done. 46 tests, rotating log, health check |
| 3. Core intelligence (model abstraction, memory) | 🟡 Claude API / Claude plan / OpenAI-compatible APIs (OpenAI, Gemini, OpenRouter, Groq, Mistral, DeepSeek, xAI, custom) / Ollama + fallback, long-term memory done. Missing: streaming, token/cost tracking, conversation summarization |
| 4. Voice | 🟡 Conversation mode, background filtering, barge-in, mute, HUD done. **Missing: local speech recognition** (needs approval to install) |
| 5. Desktop automation | 🟡 Existing app/web/media/volume/power tools. Missing: window switching, file management, document reading |
| 6. Productivity | 🟡 Tasks, school deadlines, reminders done. Missing: calendar, proactive deadline alerts, daily plan |
| 7. Cross-platform | 🟡 macOS/Linux adapters written (`platform_support.py`) and installers scripted, but **never run on a real Mac or Linux machine**. Next: run the GitHub Actions build, then test on real hardware |
| 8. Mobile | 🔴 Not started |
| 9. Plugins, research, smart home | 🔴 Not started |
| 10. Polish, installer, packaging | 🟡 Setup guide (8 screens, keyring, provider keys, real progress) + Windows installer built and tested (install/upgrade/uninstall). Mac .dmg and Linux .deb/.tar.gz scripted, untested. Not signed (paid certificates, ask first) |

## Audit findings (session 1)

What existed: about 700 lines of Python. There was a voice loop that required "Kairo" in every command, Google
speech recognition, an edge-tts voice with a SAPI fallback, Claude through the API or the Claude plan (Agent SDK),
18 Windows tools, Startup-folder autostart, and no tests, git, config or docs.

Problems found in `kairo.log`:
- 46 of the listening failures were caused by no internet. Cloud speech recognition makes KAIRO deaf offline.
  → Local STT is the top voice priority.
- Background mentions of the name ran as commands. → Fixed (conversation.classify plus `<silent>`).
- "Hey Kairo" + pause lost the command. → Fixed.
- Recognizer JSONDecodeError was mishandled as a mic failure. → Fixed.

Hardware: i5-8400 (6 cores), 16 GB RAM, **no NVIDIA GPU**. Ollama 0.40 installed, with qwen3:8b, gemma3:4b,
embeddinggemma and others. qwen3:8b on CPU takes about 120 s cold and 12–20 s warm per reply. Claude through the
plan takes about 1–11 s.

## Next up (priority order)

1. **Local speech recognition** (faster-whisper `base.en` or `small.en` + Silero VAD). This makes KAIRO work
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

### Installer follow-ups
- Run `.github/workflows/build.yml` (needs the repo on GitHub, so ask the owner before pushing anywhere) and test the
  .dmg/.deb on real machines.
- llama.cpp and Transformers engines are shown as "coming later" in the setup guide.
- Code signing: a Windows certificate and an Apple Developer ID ($99/yr). ⚠ Paid, so ask first.
- Auto-update check (currently: download and run the new installer; data is kept).
- Mobile pairing screen (waits for the mobile companion).

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
