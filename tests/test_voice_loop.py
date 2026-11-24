"""The voice loop end to end, with a scripted 'microphone', a fake speaker and a fake AI."""

import unittest

import conversation as conv
import main
import settings


class FakeSpeaker:
    def __init__(self, speak_for_listens=0):
        self.said, self.stopped = [], 0
        self.current_text = ""
        self._remaining = 0
        self._speak_for = speak_for_listens  # how many listen() calls the speech "lasts"
        self.on_state = lambda s: None

    @property
    def speaking(self):
        return self._remaining > 0

    def say(self, text, wait=True):
        self.said.append(text)
        self.current_text = text
        self._remaining = 0 if wait else self._speak_for

    def tick(self):
        self._remaining = max(0, self._remaining - 1)

    def stop(self):
        self.stopped += 1
        self._remaining = 0

    def wait(self, timeout=None):
        self._remaining = 0


class FakeListener:
    def __init__(self, speaker, lines):
        self.speaker, self.lines = speaker, list(lines)

    def listen(self, timeout=1, phrase_limit=15):
        self.speaker.tick()
        return self.lines.pop(0) if self.lines else None


class FakeBrain:
    def __init__(self, silent_for=()):
        self.asked, self.silent_for, self.name = [], silent_for, "fake"

    def ask(self, text):
        self.asked.append(text)
        if any(s in text for s in self.silent_for):
            return conv.SILENT_TOKEN
        return f"reply {len(self.asked)}"


def make(speak_for=0, silent_for=(), **overrides):
    s = settings._merge(settings.DEFAULTS, overrides)
    sp = FakeSpeaker(speak_for)
    brain = FakeBrain(silent_for)
    a = main.Assistant(s, brain, sp)
    a._write_status = lambda *args, **kw: None  # don't touch data/status.json
    return a, sp, brain


def feed(a, sp, lines):
    listener = FakeListener(sp, lines)
    while listener.lines and a.running:
        heard = listener.listen()
        if heard:
            a.process(heard, listener)
    return listener


class VoiceLoopTests(unittest.TestCase):
    def test_conversation_without_repeating_name(self):
        a, sp, brain = make(listen_chime=False)
        feed(a, sp, ["Jarvis open VS Code", "actually open my robotics project"])
        self.assertEqual(brain.asked[0], "open VS Code")
        self.assertIn("actually open my robotics project", brain.asked[1])  # follow-up reached the AI
        self.assertEqual(sp.said, ["reply 1", "reply 2"])

    def test_background_follow_up_stays_silent(self):
        a, sp, brain = make(silent_for=("pass the salt",), listen_chime=False)
        feed(a, sp, ["Jarvis what's the time", "mom can you pass the salt"])
        self.assertEqual(sp.said, ["reply 1"])

    def test_standby_ignores_unaddressed_speech(self):
        a, sp, brain = make(listen_chime=False)
        feed(a, sp, ["is dinner ready", "who left the door open"])
        self.assertEqual(brain.asked, [])

    def test_name_then_pause_then_command(self):
        a, sp, brain = make(listen_chime=False)
        feed(a, sp, ["hey Jarvis", "open Discord"])
        self.assertEqual(brain.asked, ["open Discord"])

    def test_barge_in_with_new_command(self):
        a, sp, brain = make(speak_for=5, listen_chime=False)
        feed(a, sp, ["Jarvis tell me a long story", "Jarvis open Spotify"])
        self.assertEqual(sp.stopped, 1)
        self.assertEqual(brain.asked, ["tell me a long story", "open spotify"])

    def test_echo_does_not_interrupt(self):
        a, sp, brain = make(speak_for=3, listen_chime=False)
        feed(a, sp, ["Jarvis say something", "reply 1"])  # the mic hearing JARVIS's own words
        self.assertEqual(sp.stopped, 0)
        self.assertEqual(len(brain.asked), 1)

    def test_stop_while_speaking_keeps_conversation(self):
        a, sp, brain = make(speak_for=5, listen_chime=False)
        feed(a, sp, ["Jarvis tell me a story", "stop", "what about tomorrow"])
        self.assertEqual(sp.stopped, 1)
        self.assertIn("what about tomorrow", brain.asked[-1])

    def test_goodbye(self):
        a, sp, brain = make(listen_chime=False)
        feed(a, sp, ["goodbye Jarvis", "Jarvis open chrome"])
        self.assertFalse(a.running)
        self.assertEqual(brain.asked, [])

    def test_mute_toggle(self):
        a, sp, brain = make(listen_chime=False)
        a.toggle_mute()
        self.assertTrue(a.muted)
        a.toggle_mute()
        self.assertFalse(a.muted)


if __name__ == "__main__":
    unittest.main()
