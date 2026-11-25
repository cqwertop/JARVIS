# Architecture

```
 microphone ──► voice.Listener ──► conversation.classify ──► Assistant (main.py) ──► brains.* ──► tools.*
                (speech→text)       (meant for KAIRO?)         │    ▲                 (AI)        (actions)
                                                                ▼    │ barge-in
 speakers  ◄── voice.Speaker ◄──────────────────────────────── reply ┘
 screen    ◄── hud.Hud (status panel) + global hotkeys ──► mute / stop / talk
```

| Module | Responsibility |
|---|---|
| `main.py` | Entry point, CLI flags, `Assistant`: voice loop, conversation state, barge-in, status heartbeat |
| `conversation.py` | Pure logic: wake-word parsing, direct/maybe/ignore verdicts, follow-up windows, echo + interruption detection |
| `voice.py` | `Speaker` (edge-tts neural voice → SAPI fallback, interruptible), `Listener` (persistent mic stream, Google STT) |
| `brains.py` | System prompt from settings + memory; `ApiBrain`, `OllamaBrain`, `FallbackBrain`; `make_brain` factory |
| `pro_brain.py` | `ProBrain`: Claude through the Claude Agent SDK / Claude Code (the user's plan) |
| `tools.py` | Every action KAIRO can take (`@beta_tool` functions in `ALL_TOOLS`) |
| `memory.py` | Long-term memory store; semantic search via Ollama embeddings with keyword fallback |
| `tasks.py` | Tasks / assignments / tests with due dates |
| `settings.py` | Defaults + `data/settings.json` overrides |
| `hud.py` | tkinter status panel (own thread) and Win32 global hotkeys |
| `kairo_log.py` | Rotating log file (1 MB × 4) |
| `health_check.py` | Read-only maintenance checks → `data/health/` reports + desktop notification |

## Key decisions

- **Conversation mode instead of always-on listening.** The wake word opens a conversation, and follow-ups inside
  the window (`follow_up_seconds`) don't need it. Utterances that aren't clearly addressed to KAIRO are sent to the
  AI marked as "maybe", and the AI answers `<silent>` if they look like background talk. This handles both
  "no repeated wake word" and "don't answer the people in the room", without paying for an AI call on every
  sentence heard in standby.
- **Barge-in without echo cancellation.** While KAIRO speaks, the mic also hears KAIRO. An interruption only
  counts if it contains a signal KAIRO itself isn't saying: its name, or a stop word missing from the sentence
  being spoken. This is reliable with headphones and best-effort with speakers. The hotkey and the STOP button
  always work.
- **One tool definition, three backends.** `@beta_tool` functions supply the JSON schemas, so the Claude API,
  Claude Code (via an in-process MCP server) and Ollama all use the same tools.
- **Ollama prompt caching.** The system prompt is kept byte-identical (the time goes in the user message), so
  Ollama reuses its cached work on it. This cut follow-up latency on this CPU from about 120 s to about 15 s.
- **No new dependencies in session 1.** Everything uses packages that were already installed, plus the standard
  library (tkinter, ctypes, unittest).
- **Data in `data/`**, written atomically (temp file + rename). Corrupt files are kept as `*.corrupt.json` rather
  than overwritten.

## Threads

Main thread: voice or text loop. `speaker`: TTS worker. `hud`: tkinter mainloop. `hotkeys`: Win32 message loop.
Reminder checker. `ProBrain` runs an asyncio loop in its own thread. All cross-thread communication uses
queues and events.
