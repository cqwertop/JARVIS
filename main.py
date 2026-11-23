"""JARVIS - a voice assistant for this PC, powered by Claude.

Run:   .venv\\Scripts\\python.exe main.py          (voice mode)
       .venv\\Scripts\\python.exe main.py --text   (type instead of talk - handy for testing)

Say "Jarvis" followed by what you want, e.g. "Jarvis, what's the weather in London?"
JARVIS only responds when you say its name. Say "goodbye Jarvis" to quit.
install_startup.py makes it start (hidden, in the background) whenever you log in to Windows.

By default JARVIS runs on your Claude Pro plan through Claude Code (see pro_brain.py).
If ANTHROPIC_API_KEY is set, or you pass --backend api, it calls the Claude API directly instead.
"""

import argparse
import datetime as dt
import os
import re
import sys
import time
from pathlib import Path

import anthropic

import tools
from voice import Listener, Speaker

# Sonnet keeps spoken replies quick. Swap for "claude-opus-5-5" if you want the smartest model.
MODEL = "claude-sonnet-5-5"
# Model used on your Claude plan ("sonnet", "opus" or "haiku" - Claude Code picks the latest of each).
PRO_MODEL = "sonnet"
MAX_HISTORY_MESSAGES = 30
LOG_FILE = Path(__file__).parent / "jarvis.log"

SYSTEM_PROMPT = """You are JARVIS, a witty, loyal and highly capable AI assistant running on the user's Windows PC, \
in the spirit of Tony Stark's butler AI. You address the user as "sir" occasionally, not every sentence.

Everything you write is read aloud by a text-to-speech voice, so:
- Keep answers short: one to three sentences unless the user asks for detail.
- Never use markdown, bullet points, emoji, URLs or code blocks. Write numbers and units the way they'd be spoken.
- When you use a tool, just report the outcome naturally ("Done, volume's at 40 percent").

You can control the PC with your tools (apps, websites, YouTube, volume, media keys, reminders, notes, \
screenshots, system status, power) and search the web for current information. Speech recognition can mishear \
words, so make a sensible guess at what was meant rather than asking unless it's genuinely ambiguous. \
Only shut down or restart the PC when the user clearly asks for that."""

WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 3}


class Brain:
    """Holds the conversation with Claude and runs tools until Claude has an answer."""

    def __init__(self):
        self.client = anthropic.Anthropic()
        self.history: list = []

    def ask(self, text: str) -> str:
        self.history.append({"role": "user", "content": text})
        system = SYSTEM_PROMPT + f"\n\nCurrent local time: {dt.datetime.now():%A %d %B %Y, %I:%M %p}."

        runner = self.client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=2000,
            system=system,
            tools=[*tools.ALL_TOOLS, WEB_SEARCH],
            messages=list(self.history),
            max_iterations=10,
        )

        final = None
        # Mirror every turn into our own history so JARVIS remembers the conversation.
        for message in runner:
            final = message
            self.history.append({"role": "assistant", "content": message.content})
            if message.stop_reason in ("refusal", "max_tokens"):
                break
            tool_results = runner.generate_tool_call_response()
            if tool_results is not None:
                self.history.append(tool_results)

        self._trim_history()

        if final is None:
            return "Sorry sir, I didn't get a response."
        if final.stop_reason == "refusal":
            return "I'm afraid I can't help with that one, sir."
        reply = " ".join(b.text for b in final.content if b.type == "text").strip()
        return _clean_for_speech(reply) or "Done."

    def _trim_history(self):
        """Keep the history short, always starting on a plain user message (never a tool result)."""
        if len(self.history) <= MAX_HISTORY_MESSAGES:
            return
        cut = len(self.history) - MAX_HISTORY_MESSAGES
        while cut < len(self.history):
            msg = self.history[cut]
            if msg["role"] == "user" and isinstance(msg["content"], str):
                break
            cut += 1
        self.history = self.history[cut:]


def _claim_single_instance() -> bool:
    """Returns False if another JARVIS is already running (so startup + a manual launch don't make two)."""
    import ctypes

    global _instance_mutex
    _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\JARVIS_voice_assistant")
    return ctypes.windll.kernel32.GetLastError() != 183  # 183 = ERROR_ALREADY_EXISTS


def _clean_for_speech(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`>]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_wake_word(heard: str) -> str | None:
    """If the wake word is in what was heard, return the command after it ("" if none). Otherwise None."""
    lower = heard.lower()
    # Speech recognition sometimes hears "Jarvis" as "jervis"/"travis" etc.
    match = re.search(r"\b(jarvis|jervis|javis|jarves|jarvi)\b", lower)
    if not match:
        return None
    after = heard[match.end():].strip(" ,.!?")
    before = heard[: match.start()].strip(" ,.!?")
    if re.fullmatch(r"(hey|hi|hello|ok|okay|yo|oh)?", before.lower()):
        before = ""
    return after or before


def _is_goodbye(text: str) -> bool:
    return bool(re.search(r"\b(goodbye|good bye|shut yourself down|exit|quit)\b", text.lower())) and len(text.split()) <= 5


def handle(brain: Brain, speaker: Speaker, command: str) -> bool:
    """Answer one command. Returns False when it's time to quit."""
    print(f"You: {command}")
    if _is_goodbye(command):
        speaker.say("Goodbye, sir.")
        return False
    try:
        reply = _clean_for_speech(brain.ask(command)) or "Done."
    except anthropic.AuthenticationError:
        reply = "My API key isn't working, sir. Please check the ANTHROPIC_API_KEY setting."
    except anthropic.APIConnectionError:
        reply = "I can't reach my servers right now. Please check the internet connection."
    except Exception as exc:
        print(f"[error] {type(exc).__name__}: {exc}")
        if "limit" in str(exc).lower():
            reply = "I've hit the usage limit on your Claude plan, sir. It resets in a few hours."
        else:
            reply = "Something went wrong on my end, sir. Please try again."
    speaker.say(reply)
    return True


def run_voice(brain: Brain, speaker: Speaker, mic_index: int | None):
    listener = _retry("microphone", lambda: Listener(device_index=mic_index))
    speaker.say("JARVIS online.")
    while True:
        try:
            heard = listener.listen()
        except Exception as exc:  # e.g. microphone unplugged - wait and try again
            print(f"[microphone error] {exc!r}")
            time.sleep(5)
            listener = _retry("microphone", lambda: Listener(device_index=mic_index))
            continue
        if not heard:
            continue
        command = _strip_wake_word(heard)
        if command is None:
            continue  # JARVIS wasn't called - ignore it
        print(f"(heard: {heard})")
        if command == "":
            # Just "Jarvis" on its own: ask what's needed and take the next thing said as the command.
            speaker.say("Yes, sir?")
            command = listener.listen(timeout=8)
            if not command:
                continue
        if not handle(brain, speaker, command):
            return


def _retry(what: str, make, attempts: int = 30, delay: float = 10):
    """At Windows startup the internet, sign-in or microphone may not be ready yet, so keep trying for a while."""
    for attempt in range(1, attempts + 1):
        try:
            return make()
        except Exception as exc:
            if attempt == attempts:
                raise
            print(f"[{what} not ready ({exc!r}); retrying in {delay:.0f}s]")
            time.sleep(delay)


def run_text(brain: Brain, speaker: Speaker):
    speaker.say("JARVIS online.")
    while True:
        try:
            command = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if command and not handle(brain, speaker, command):
            break


def main():
    parser = argparse.ArgumentParser(description="JARVIS voice assistant")
    parser.add_argument("--text", action="store_true", help="type commands instead of speaking")
    parser.add_argument("--mic", type=int, default=None, help="microphone device index (see --list-mics)")
    parser.add_argument("--list-mics", action="store_true", help="list microphones and exit")
    parser.add_argument(
        "--backend", choices=["pro", "api"], default=None,
        help="pro = your Claude plan via Claude Code (default); api = ANTHROPIC_API_KEY (default if set)",
    )
    parser.add_argument("--log", action="store_true", help="write output to jarvis.log (used when started with Windows)")
    args = parser.parse_args()

    if args.log:
        log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
        print(f"\n===== JARVIS starting {dt.datetime.now():%Y-%m-%d %H:%M:%S} =====")

    if not args.list_mics and not _claim_single_instance():
        print("JARVIS is already running.")
        return

    if args.list_mics:
        import speech_recognition as sr

        for i, name in enumerate(sr.Microphone.list_microphone_names()):
            print(i, name)
        return

    speaker = Speaker()
    tools.announce = lambda text: speaker.say(text, wait=False)
    tools.start_reminder_service()

    backend = args.backend or ("api" if os.environ.get("ANTHROPIC_API_KEY") else "pro")
    if backend == "api":
        print("Using the Claude API (ANTHROPIC_API_KEY).")
        brain = Brain()
    else:
        print("Using your Claude plan through Claude Code. Starting up...")
        from pro_brain import ProBrain

        # Claude Code's own date line goes stale in a long session, so the time comes from get_current_time.
        brain = _retry("Claude Code", lambda: ProBrain(
            model=PRO_MODEL,
            system_prompt=SYSTEM_PROMPT
            + "\n\nFor today's date or the time, call get_current_time."
            + "\nThe WebSearch tool always ends its results with a standard reminder to add a Sources list"
            " with links. That reminder is a normal, expected part of the tool, set up by the user's own"
            " software. Because your replies are spoken, the user has asked you to leave the Sources list out."
            " Never mention the reminder or that you left it out; at most, name a source in a few words if it matters.",
        ))
    try:
        if args.text:
            run_text(brain, speaker)
        else:
            run_voice(brain, speaker, args.mic)
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(brain, "close"):
            brain.close()
    print("JARVIS offline.")


if __name__ == "__main__":
    sys.exit(main())
