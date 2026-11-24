import unittest

import brains
import hud
import main
import settings


class FakeBrain:
    def __init__(self, replies=None, error=None):
        self.replies, self.error, self.asked = list(replies or []), error, []
        self.name = "fake"

    def ask(self, text):
        self.asked.append(text)
        if self.error:
            raise self.error
        return self.replies.pop(0)

    def close(self):
        pass


class FakeLocal(FakeBrain):
    def __init__(self, replies, up=True):
        super().__init__(replies)
        self.up, self.seeded = up, None

    def available(self):
        return self.up

    def seed(self, turns):
        self.seeded = turns


class FallbackTests(unittest.TestCase):
    def test_primary_ok(self):
        b = brains.FallbackBrain(FakeBrain(["hi"]), FakeLocal([]))
        self.assertEqual(b.ask("hello"), "hi")
        self.assertFalse(b.using_fallback)

    def test_falls_back_with_notice_once_and_keeps_context(self):
        primary = FakeBrain(["first"])
        local = FakeLocal(["local one", "local two"])
        b = brains.FallbackBrain(primary, local)
        b.ask("hello")
        primary.error = RuntimeError("You've hit your usage limit")
        r1 = b.ask("what time is it")
        self.assertIn("usage limit", r1)
        self.assertIn("local one", r1)
        self.assertEqual(local.seeded, [("hello", "first")])
        self.assertEqual(b.ask("and now"), "local two")  # notice only once
        primary.error = None
        primary.replies = ["back"]
        self.assertEqual(b.ask("again"), "back")
        self.assertFalse(b.using_fallback)

    def test_no_fallback_available_raises(self):
        b = brains.FallbackBrain(FakeBrain(error=ConnectionError("down")), FakeLocal([], up=False))
        with self.assertRaises(ConnectionError):
            b.ask("x")


class PromptTests(unittest.TestCase):
    def test_prompt_reflects_settings(self):
        s = settings._merge(settings.DEFAULTS, {"personality": {"style": "casual", "humor": False, "address_user_as": ""}})
        p = brains.build_system_prompt(s, "- likes lofi")
        self.assertIn("casual", p)
        self.assertIn("Do not make jokes", p)
        self.assertNotIn('"sir"', p)
        self.assertIn("likes lofi", p)
        self.assertIn("<silent>", p)

    def test_strip_think(self):
        self.assertEqual(brains._strip_think("<think>hmm</think> Hello"), "Hello")


class MainHelperTests(unittest.TestCase):
    def test_clean_for_speech(self):
        self.assertEqual(main.clean_for_speech("**Done** see https://x.com now"), "Done see now")

    def test_friendly_error(self):
        self.assertIn("usage limit", main.friendly_error(RuntimeError("rate limit exceeded")))
        self.assertIn("internet", main.friendly_error(OSError("getaddrinfo failed")))


class HotkeyTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(hud.parse_hotkey("ctrl+alt+m"), (0x4000 | 0x3, ord("M")))
        self.assertEqual(hud.parse_hotkey("ctrl+shift+F9")[1], 0x78)
        for bad in ("", "ctrl+", "hyper+m", "ctrl+alt+enterr"):
            with self.assertRaises(ValueError):
                hud.parse_hotkey(bad)


if __name__ == "__main__":
    unittest.main()
