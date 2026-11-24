"""JARVIS - a voice assistant for this PC.

Run:   .venv\\Scripts\\python.exe main.py            (voice mode)
       .venv\\Scripts\\python.exe main.py --text     (type instead of talk - handy for testing)

Talking to JARVIS (default "conversation" mode):
  Say "Jarvis, <request>". After it answers you can just keep talking - follow-ups don't need the name
  until you've been quiet for a while (follow_up_seconds in settings). Say "stop" / "Jarvis, stop" to cut it off,
  "that's all" to end the conversation, "goodbye Jarvis" to shut it down.
  The on-screen panel shows whether the microphone is on. Ctrl+Alt+M mutes, Ctrl+Alt+S stops speech,
  Ctrl+Alt+J talks without the name. Settings: data/settings.json (all options are listed in settings.py).

AI: your Claude plan through Claude Code by default; the Claude API if ANTHROPIC_API_KEY is set; a local Ollama
model with --backend ollama. If Claude is unreachable or out of usage, JARVIS falls back to the local model.
install_startup.py makes JARVIS start (hidden, in the background) whenever you log in to Windows.
"""

import argparse
import datetime as dt
import json
import logging
import os
import re
import sys
import threading
import time

import queue

import brains
import conversation as conv
import credentials
import paths
import jarvis_log
import settings as settings_mod
import tools
from voice import Listener, Speaker, chime, list_microphones

log = logging.getLogger("jarvis")
STATUS_FILE = settings_mod.DATA_DIR / "status.json"


def clean_for_speech(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`>]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def friendly_error(exc: Exception) -> str:
    name = type(exc).__name__
    text = str(exc).lower()
    if name == "AuthenticationError":
        return "My API key isn't working. Please check the ANTHROPIC_API_KEY setting."
    if name in ("APIConnectionError", "ConnectionError", "URLError") or "getaddrinfo" in text:
        return "I can't reach my servers right now. Please check the internet connection."
    if "limit" in text:
        return "I've hit the usage limit on the Claude plan. It resets in a few hours."
    return "Something went wrong on my end. Please try again."


class Assistant:
    """Ties together the brain, the voice, the on-screen panel and the conversation logic."""

    def __init__(self, settings: dict, brain, speaker: Speaker, mic_index: int | None = None):
        self.s = settings
        self.brain = brain
        self.speaker = speaker
        self.mic_index = mic_index
        self.mode = settings["listen_mode"]
        self.wake_words = settings["wake_words"]
        self.state = conv.ConversationState(settings["follow_up_seconds"])
        self.muted = self.mode in ("push_to_talk", "text")
        self.talk_requested = threading.Event()
        self.typed: "queue.Queue[str]" = queue.Queue()
        self.running = True
        self.hud = None
        self._hud_state = None
        self.last_error = ""
        self._last_status_write = 0.0

    # ------------------------------------------------------------------ controls (HUD buttons / hotkeys)
    def submit_text(self, text: str):
        """A message typed into the on-screen panel. Handled by the main loop, in order."""
        self.speaker.stop()
        self.typed.put(text)
        self.talk_requested.set()  # wake the loop if it's idle

    def quit(self):
        self.running = False
        self.speaker.stop()
        self.talk_requested.set()

    def toggle_mute(self):
        if self.mode == "text":
            return
        if self.mode == "push_to_talk":
            self.talk()
            return
        self.muted = not self.muted
        log.info("Microphone %s.", "muted" if self.muted else "unmuted")
        if self.muted:
            self.state.end()
        if self.hud:
            self.hud.set_muted(self.muted)
        self._show("muted" if self.muted else "standby", "Microphone is off" if self.muted else "Say 'Jarvis' to start")

    def stop_speaking(self):
        self.speaker.stop()

    def talk(self):
        """Listen for one command without needing the wake word (works even while muted)."""
        if self.mode == "text":
            return
        self.speaker.stop()
        self.talk_requested.set()

    def attach_hud(self, hud):
        self.hud = hud
        speaking_ref = {"prev": None}

        def on_speaker_state(speaking: bool):
            if speaking:
                speaking_ref["prev"] = self._hud_state
                self._show("speaking")
            elif self._hud_state == "speaking":
                self._show(speaking_ref["prev"] or "standby")

        self.speaker.on_state = on_speaker_state

    def _show(self, state: str, detail: str | None = None):
        self._hud_state = state
        if self.hud:
            self.hud.set_state(state, detail)
        self._write_status(state)

    def _write_status(self, state: str, force: bool = False):
        """data/status.json lets the health check (and future dashboards) see that JARVIS is alive."""
        now = time.time()
        if not force and now - self._last_status_write < 30:
            return
        self._last_status_write = now
        try:
            STATUS_FILE.write_text(json.dumps({
                "pid": os.getpid(), "state": state, "updated": dt.datetime.now().isoformat(timespec="seconds"),
                "backend": getattr(self.brain, "name", "?"), "listen_mode": self.mode, "muted": self.muted,
                "last_error": self.last_error,
            }, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------ thinking
    def think(self, command: str, maybe: bool = False) -> str | None:
        """Ask the AI. Returns the reply to speak, or None if JARVIS should stay silent."""
        if self.s["log_transcripts"]:
            log.info("You: %s%s", command, "  (not addressed by name)" if maybe else "")
        self._show("thinking", command)
        try:
            reply = self.brain.ask(conv.maybe_prompt(command) if maybe else command)
        except Exception as exc:
            log.error("AI request failed: %r", exc)
            self.last_error = f"{dt.datetime.now():%H:%M} {type(exc).__name__}: {exc}"[:300]
            self._write_status("error", force=True)
            return friendly_error(exc)
        if conv.is_silent_reply(reply):
            log.info("(Not meant for me - staying quiet.)")
            return None
        return clean_for_speech(reply) or "Done."

    def handle_text(self, command: str) -> bool:
        """Text mode: one typed command. Returns False when it's time to quit."""
        if conv.is_goodbye(command):
            self.speaker.say("Goodbye.")
            return False
        reply = self.think(command)
        if reply:
            self.speaker.say(reply)
        return True

    # ------------------------------------------------------------------ voice
    def run_voice(self):
        listener = Listener(device_index=self.mic_index)
        self.speaker.say(f"{self.s['assistant_name']} online.")
        while self.running:
            if self._handle_typed(listener):
                continue
            if self.talk_requested.is_set():
                self.talk_requested.clear()
                if self.mode != "text":
                    self._start_listening_for_command()
            mic_allowed = not self.muted or self.state.awaiting_command
            if not mic_allowed:
                listener.close()
                idle = {"push_to_talk": "push_to_talk", "text": "text"}.get(self.mode, "muted")
                self._show(idle)
                self.talk_requested.wait(0.3)
                continue
            self._show("listening" if self.state.active else "standby")
            try:
                heard = listener.listen(timeout=1)
            except Exception as exc:  # microphone unplugged / driver hiccup - reopen it
                log.error("Microphone error: %r", exc)
                self.last_error = f"{dt.datetime.now():%H:%M} microphone: {exc!r}"[:300]
                self._show("error", "Microphone problem - retrying")
                listener.close()
                time.sleep(3)
                continue
            if heard:
                self.process(heard, listener)
        listener.close()

    def _handle_typed(self, listener) -> bool:
        try:
            text = self.typed.get_nowait()
        except queue.Empty:
            return False
        if conv.is_goodbye(text):
            self.speaker.say("Goodbye.")
            self.running = False
            return True
        reply = self.think(text)
        if reply:
            self.speak(reply, listener, barge_in=False)
        return True

    def _start_listening_for_command(self):
        self.state.heard_wake_word()
        self._show("listening", "Listening...")
        if self.s["listen_chime"]:
            chime()

    def process(self, heard: str, listener: Listener):
        verdict = conv.classify(heard, self.wake_words, self.state.awaiting_command, self.state.in_follow_up, self.mode)
        log.debug("heard %r -> %s", heard, verdict)
        if verdict.kind == conv.IGNORE:
            return
        if self.s["log_transcripts"]:
            log.info("(heard: %s)", heard)
        if verdict.kind == conv.GOODBYE:
            self.speaker.say("Goodbye.")
            self.running = False
            return
        if verdict.kind == conv.STOP:
            self.speaker.stop()
            self.state.end()
            return
        if verdict.kind == conv.WAKE_ONLY:
            self._start_listening_for_command()
            return
        self.state.consumed_command()
        reply = self.think(verdict.command, maybe=verdict.kind == conv.MAYBE)
        if reply is None:
            return
        self.speak(reply, listener)

    def speak(self, reply: str, listener: Listener, barge_in: bool = True):
        """Say the reply. With barge-in on, keep listening so the user can cut in."""
        if self.hud:
            self.hud.set_reply(reply)
        self.speaker.say(reply, wait=False)
        interruption = None
        if barge_in and self.s["barge_in"] and not self.muted:
            time.sleep(0.15)
            while self.speaker.speaking and not self.muted:
                try:
                    heard = listener.listen(timeout=0.5, phrase_limit=8)
                except Exception:
                    break
                if not heard:
                    continue
                interruption = conv.detect_interruption(heard, self.speaker.current_text or reply, self.wake_words)
                if interruption:
                    log.info("(interrupted: %s)", heard)
                    self.speaker.stop()
                    break
                log.debug("ignored while speaking (echo?): %r", heard)
        self.speaker.wait()
        self.state.answered()
        if interruption and interruption.kind == conv.DIRECT:
            self.state.consumed_command()
            follow = self.think(interruption.command)
            if follow:
                self.speak(follow, listener)


def open_folder(path):
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)
    else:
        import platform_support

        platform_support.open_path(str(path))


def open_setup(restart_after: bool = False, assistant=None):
    """Open the setup wizard in its own process. JARVIS restarts afterwards so new settings apply."""
    import subprocess

    if paths.FROZEN:
        cmd = [sys.executable, "--setup"]
    else:
        cmd = [sys.executable, str(paths.APP_DIR / "jarvis_app.py"), "--setup"]
    if restart_after:
        cmd.append("--restart-jarvis")
    subprocess.Popen(cmd)
    if restart_after and assistant:
        assistant.quit()


SHOW_REQUEST = settings_mod.DATA_DIR / "show-panel.request"  # written by a second launch, read by the HUD


def claim_single_instance() -> bool:
    """False if another JARVIS is already running (so startup + a manual launch don't make two)."""
    if sys.platform == "win32":
        import ctypes

        global _instance_mutex
        _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\JARVIS_voice_assistant")
        return ctypes.windll.kernel32.GetLastError() != 183  # 183 = ERROR_ALREADY_EXISTS
    import fcntl

    global _lock_file
    settings_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _lock_file = open(settings_mod.DATA_DIR / "jarvis.lock", "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def retry(what: str, make, attempts: int = 30, delay: float = 10):
    """At startup the internet, sign-in or microphone may not be ready yet, so keep trying for a while."""
    for attempt in range(1, attempts + 1):
        try:
            return make()
        except Exception as exc:
            if attempt == attempts:
                raise
            log.warning("%s not ready (%r); retrying in %.0fs", what, exc, delay)
            time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description="JARVIS voice assistant")
    parser.add_argument("--text", action="store_true", help="type commands instead of speaking")
    parser.add_argument("--no-speech", action="store_true", help="text mode: print replies without speaking them")
    parser.add_argument("--mic", type=int, default=None, help="microphone device index (see --list-mics)")
    parser.add_argument("--list-mics", action="store_true", help="list microphones and exit")
    parser.add_argument("--backend", choices=["auto", "pro", "api", "online", "ollama"], default=None,
                        help="pro = Claude plan via Claude Code; api = ANTHROPIC_API_KEY; ollama = local model")
    parser.add_argument("--mode", choices=list(settings_mod.LISTEN_MODES), default=None,
                        help="how JARVIS decides you're talking to it (overrides settings)")
    parser.add_argument("--log", action="store_true", help="write output to jarvis.log (used when started with Windows)")
    parser.add_argument("--verbose", action="store_true", help="more detailed logging")
    parser.add_argument("--restarted", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if paths.FROZEN and not args.text:
        args.log = True  # the installed app has no console window
    jarvis_log.setup(to_file=args.log, verbose=args.verbose)
    if args.log:
        log.info("===== JARVIS starting =====")

    if args.list_mics:
        for i, name in enumerate(list_microphones()):
            print(i, name)
        return

    deadline = time.monotonic() + (15 if "--restarted" in sys.argv else 0)
    while not claim_single_instance():
        if time.monotonic() >= deadline:
            # Opened again (Start menu / search / double-click): ask the running JARVIS to show its panel.
            log.info("JARVIS is already running - asking it to show its panel.")
            try:
                settings_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
                SHOW_REQUEST.write_text(str(time.time()), encoding="utf-8")
            except OSError as exc:
                log.warning("Couldn't reach the running JARVIS: %r", exc)
            return
        time.sleep(0.5)

    s = settings_mod.load()
    if args.mode:
        s["listen_mode"] = args.mode
    tools.init(s)
    credentials.load_into_environment()
    if args.mic is None and s["microphone_name"]:
        names = list_microphones()
        args.mic = next((i for i, n in enumerate(names) if n == s["microphone_name"]), None)
        if args.mic is None:
            log.warning("Microphone %r not found - using the default one.", s["microphone_name"])

    speaker = Speaker.from_settings(s["voice"])
    if args.no_speech:
        speaker.say = lambda text, wait=True: print(f"JARVIS: {text}")
    tools.announce = lambda text: speaker.say(text, wait=False)
    tools.start_reminder_service()

    backend = brains.choose_backend(s, args.backend)
    log.info("AI: %s. Starting up...", {"pro": "your Claude plan via Claude Code", "api": "the Claude API",
                                        "online": f"{s['online']['provider']} {s['online']['model']}",
                                        "ollama": f"local model {s['ollama_model']}"}[backend])
    brain = brains.make_brain(s, backend, retry=retry)
    assistant = Assistant(s, brain, speaker, args.mic)
    if hasattr(brain, "on_backend_change"):
        brain.on_backend_change = lambda name: assistant._show(assistant._hud_state or "standby", f"AI: {name}")

    hud = None
    if not args.text:
        if s["hud"]:
            from hud import Hud

            menu = {
                "Settings...": lambda: open_setup(restart_after=True, assistant=assistant),
                "Open my JARVIS data folder": lambda: open_folder(settings_mod.DATA_DIR),
                "Quit JARVIS": assistant.quit,
            }
            hud = Hud(assistant.toggle_mute, assistant.stop_speaking, assistant.talk, s["hotkeys"],
                      on_text=assistant.submit_text, menu=menu, show_typing=s["listen_mode"] == "text",
                      show_request=SHOW_REQUEST)
            assistant.attach_hud(hud)
        if s["hotkeys"]["enabled"]:
            from hud import start_hotkeys

            hk = s["hotkeys"]
            bindings = {
                "mute": (hk["mute"], assistant.toggle_mute),
                "stop": (hk["stop"], assistant.stop_speaking),
                "talk": (hk["talk"], assistant.talk),
            }
            if hud is not None and hud.ok and hk.get("panel"):
                bindings["panel"] = (hk["panel"], hud.toggle_visible)
            registered = start_hotkeys(bindings)
            if registered:
                log.info("Hotkeys: %s", ", ".join(registered))

    try:
        if args.text:
            speaker.say(f"{s['assistant_name']} online.")
            while True:
                try:
                    command = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if command and not assistant.handle_text(command):
                    break
        else:
            assistant._show("starting", f"AI: {getattr(brain, 'name', backend)}")
            retry("microphone", lambda: assistant.run_voice())
    except KeyboardInterrupt:
        pass
    finally:
        if hud:
            hud.close()
        brain.close()
    log.info("JARVIS offline.")


if __name__ == "__main__":
    sys.exit(main())
