import unittest

import conversation as c

WAKE = ["kairo", "cairo", "kyro", "kiro", "kairos", "chiro"]


def classify(text, awaiting=False, follow=False, mode="conversation"):
    return c.classify(text, WAKE, awaiting, follow, mode)


class ClassifyTests(unittest.TestCase):
    def test_name_first_is_direct(self):
        self.assertEqual(classify("Kairo open Discord"), c.Verdict(c.DIRECT, "open Discord"))
        self.assertEqual(classify("hey Kairo, play I wonder by Kanye West"), c.Verdict(c.DIRECT, "play I wonder by Kanye West"))
        self.assertEqual(classify("okay Cairo what's the weather"), c.Verdict(c.DIRECT, "what's the weather"))

    def test_name_alone_waits_for_command(self):
        self.assertEqual(classify("hey Kairo").kind, c.WAKE_ONLY)
        self.assertEqual(classify("Kairo").kind, c.WAKE_ONLY)

    def test_command_after_name_alone_is_direct(self):
        # The old version lost these: "hey Kairo" ... pause ... "open Discord"
        self.assertEqual(classify("open Discord", awaiting=True), c.Verdict(c.DIRECT, "open Discord"))

    def test_background_mentions_are_not_direct(self):
        # Real false triggers from kairo.log
        for text in ["Amazon Kairo", "Ray Kairo", "11 Kairo", "are you just making Kairo do it bro",
                     "yeah I built Kairo", "what do you like it to be called Kairo"]:
            self.assertEqual(classify(text).kind, c.MAYBE, text)

    def test_unaddressed_speech_ignored_in_standby(self):
        self.assertEqual(classify("dinner is ready").kind, c.IGNORE)

    def test_follow_up_without_name(self):
        v = classify("actually open my robotics project", follow=True)
        self.assertEqual(v, c.Verdict(c.MAYBE, "actually open my robotics project"))

    def test_wake_word_mode_requires_name(self):
        self.assertEqual(classify("open chrome", follow=True, mode="wake_word").kind, c.IGNORE)

    def test_always_mode(self):
        self.assertEqual(classify("open chrome", mode="always").kind, c.MAYBE)

    def test_push_to_talk_is_direct(self):
        self.assertEqual(classify("open chrome", mode="push_to_talk").kind, c.DIRECT)

    def test_stop_and_goodbye(self):
        self.assertEqual(classify("stop", follow=True).kind, c.STOP)
        self.assertEqual(classify("Kairo stop").kind, c.STOP)
        self.assertEqual(classify("okay that's all thanks", follow=True).kind, c.STOP)
        self.assertEqual(classify("goodbye Kairo").kind, c.GOODBYE)
        # Not a goodbye: long sentence that happens to contain "exit"
        self.assertNotEqual(classify("Kairo how do I exit vim without losing my changes").kind, c.GOODBYE)
        # "stop" in standby without the name is just background
        self.assertEqual(classify("stop").kind, c.IGNORE)

    def test_stop_inside_request_is_not_stop(self):
        self.assertEqual(classify("Kairo how do I stop my code from crashing").kind, c.DIRECT)


class EchoAndInterruptTests(unittest.TestCase):
    SPOKEN = "The weather in London is twelve degrees and cloudy with a chance of rain this afternoon"

    def test_echo(self):
        self.assertTrue(c.looks_like_echo("weather in London is twelve degrees", self.SPOKEN))
        self.assertTrue(c.looks_like_echo("the weather in London is 12 degrees and cloudy", self.SPOKEN))
        self.assertFalse(c.looks_like_echo("open spotify", self.SPOKEN))

    def test_interruptions(self):
        self.assertEqual(c.detect_interruption("Kairo stop", self.SPOKEN, WAKE).kind, c.STOP)
        self.assertEqual(c.detect_interruption("London is twelve stop degrees", self.SPOKEN, WAKE).kind, c.STOP)
        v = c.detect_interruption("Kairo open Spotify", self.SPOKEN, WAKE)
        self.assertEqual(v, c.Verdict(c.DIRECT, "open spotify"))
        self.assertIsNone(c.detect_interruption("weather in London is twelve degrees", self.SPOKEN, WAKE))
        # KAIRO saying its own name must not count as an interruption
        self.assertIsNone(c.detect_interruption("I'm Kairo your assistant", "I'm Kairo, your assistant", WAKE))


class SilentTests(unittest.TestCase):
    def test_silent(self):
        self.assertTrue(c.is_silent_reply("<silent>"))
        self.assertTrue(c.is_silent_reply(" <SILENT> "))
        self.assertFalse(c.is_silent_reply("Opening Chrome."))
        self.assertIn(c.SILENT_TOKEN, c.maybe_prompt("hello"))


class StateTests(unittest.TestCase):
    def test_windows(self):
        now = [100.0]
        s = c.ConversationState(20, clock=lambda: now[0])
        self.assertFalse(s.active)
        s.heard_wake_word(8)
        self.assertTrue(s.awaiting_command)
        now[0] += 9
        self.assertFalse(s.awaiting_command)
        s.answered()
        self.assertTrue(s.in_follow_up)
        now[0] += 19
        self.assertTrue(s.in_follow_up)
        now[0] += 2
        self.assertFalse(s.in_follow_up)
        s.answered()
        s.end()
        self.assertFalse(s.active)


if __name__ == "__main__":
    unittest.main()
