# JARVIS

A voice assistant for your PC. Talk to it naturally, and it can open apps, play music, set reminders, keep track
of homework and deadlines, remember things about you and your projects, and answer questions using Claude
(or a local AI model when you're offline or out of Claude usage).

**Works on:** Windows 10/11 (tested). Linux and macOS are **not supported yet** (see [ROADMAP.md](ROADMAP.md)).

## Starting JARVIS

- Double-click **`start_jarvis.bat`**, or
- Run `.venv\Scripts\python.exe install_startup.py` once so JARVIS starts by itself whenever you log in.

A small panel appears in the bottom-right corner of the screen. It always shows whether JARVIS is listening:

| Panel says | Meaning |
|---|---|
| STANDBY | Microphone on, waiting for you to say "Jarvis" |
| LISTENING | In a conversation: just talk, no need to say "Jarvis" |
| THINKING / SPEAKING | Working on your request / answering |
| MIC OFF | Microphone fully closed; nothing is being heard |

Drag the panel to move it. Right-click it to hide it until JARVIS restarts.

## Talking to JARVIS

1. Say **"Jarvis, …"** followed by what you want: *"Jarvis, open VS Code."*
2. After it answers, **just keep talking**. Follow-ups don't need the name: *"Actually, open my robotics project."*
3. When you've been quiet for 20 seconds, JARVIS goes back to waiting for its name.

| You say | What happens |
|---|---|
| "Hey Jarvis" (then a pause) | Beep, and JARVIS listens for your request |
| "Stop" / "Jarvis, stop" (while it talks) | It stops talking |
| "Jarvis, open Spotify" (while it talks) | It stops and does the new request |
| "That's all" | Ends the conversation |
| "Goodbye Jarvis" | Shuts JARVIS down |

When you talk without saying its name, JARVIS checks whether you were talking to it. If you were talking to
someone else, it stays quiet.

**Keyboard shortcuts** (work in any app):
- **Ctrl+Alt+M**: microphone off / on
- **Ctrl+Alt+S**: stop talking
- **Ctrl+Alt+J**: talk without saying "Jarvis"

### Things to try
- "What's the weather in Chicago?" / "Play lofi hip hop on YouTube" / "Set the volume to 30"
- "Remind me to take the pizza out in 12 minutes"
- "I have a chemistry test on Friday, add it to my list" / "What's due this week?" / "I finished the worksheet"
- "Remember that my robotics project uses an Arduino Mega" / "What do you remember about my projects?"
- "Show me everything you've stored" / "Forget that"

## Settings

Your settings are in **`data/settings.json`**. Put only the things you want to change there; every option and its
default is listed (with explanations) at the top of [`settings.py`](settings.py). Examples:

```json
{
  "listen_mode": "conversation",
  "follow_up_seconds": 30,
  "voice": { "neural_voice": "en-US-GuyNeural", "rate": "+0%" },
  "personality": { "style": "casual", "address_user_as": "" }
}
```

`listen_mode` can be one of:
- `conversation` (default): say the name once, then talk freely
- `wake_word`: always say the name
- `always`: no name needed (uses more AI usage)
- `push_to_talk`: microphone opens only when you press Ctrl+Alt+J

## Which AI answers

| Backend | When | Cost |
|---|---|---|
| Your Claude plan (default) | Claude Code is installed and signed in | Counts toward your plan's usage limits |
| Claude API | `ANTHROPIC_API_KEY` is set | Pay per use (separate from a Claude subscription) |
| Local model (Ollama) | `--backend ollama`, or **automatically** when Claude is unreachable or out of usage | Free, private, works offline |

The local model (`qwen3:8b`) runs on your processor, so it's slow. The first answer takes about 2 minutes while it
loads, and later answers take 10–20 seconds. It works, but Claude is much faster and smarter.

## Your data and privacy

Everything personal is kept in the **`data/`** folder on this PC. That folder is never uploaded to git.

- `memory.json`: what JARVIS remembers (you can read, edit or delete it, or ask JARVIS to)
- `tasks.json`, `reminders.json`, `notes.txt`: your lists
- `settings.json`: your settings

Microphone audio is **never saved**. Speech recognition currently uses Google's free online recognizer, so speech is
sent to Google to be turned into text. A local, offline option is planned (see ROADMAP.md). While muted, the
microphone is fully closed.

## Health check

```
.venv\Scripts\python.exe health_check.py --notify
```

This checks that the code compiles, that the tests pass, that JARVIS is alive, that the AI backends are
reachable, and whether there are new errors in the log. If anything is wrong, it shows a desktop notification.
Reports are saved in `data/health/`.

## For developers

- Run tests: `.venv\Scripts\python.exe -m unittest discover -s tests -t .`
- Text mode (no microphone): `start_jarvis.bat --text` (add `--no-speech` to skip the voice)
- How it fits together: [ARCHITECTURE.md](ARCHITECTURE.md). What's next: [ROADMAP.md](ROADMAP.md). History: [CHANGELOG.md](CHANGELOG.md).
- To add an ability, write a function in `tools.py` with `@beta_tool` and add it to `ALL_TOOLS`. All three AI
  backends pick it up automatically.
