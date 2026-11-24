"""Memory, tasks, settings and reminders - all against temporary files, never the real data/ folder."""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import memory
import settings
import tasks


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = memory.MemoryStore(Path(self.dir.name) / "memory.json", embedder=None)

    def tearDown(self):
        self.dir.cleanup()

    def test_add_search_delete_persist(self):
        a, new = self.store.add("The user's robotics project uses an Arduino Mega and two servos", "project")
        self.assertTrue(new)
        self.store.add("The user prefers metric units", "preference")
        self.assertEqual(self.store.search("robotics arduino")[0]["id"], a["id"])
        self.assertEqual(self.store.search("pizza toppings"), [])
        reloaded = memory.MemoryStore(self.store.path, embedder=None)
        self.assertEqual(len(reloaded.all()), 2)
        self.assertEqual(len(reloaded.delete([a["id"]])), 1)
        self.assertEqual([i["text"] for i in memory.MemoryStore(self.store.path).all()], ["The user prefers metric units"])

    def test_duplicates_update_instead_of_adding(self):
        self.store.add("The user prefers metric units", "preference")
        _, new = self.store.add("The user prefers metric units.", "preference")
        self.assertFalse(new)
        self.assertEqual(len(self.store.all()), 1)

    def test_preferences_summary_and_empty_query(self):
        self.store.add("Call the user by their first name", "preference")
        self.store.add("Mars has two moons", "fact")
        self.assertIn("first name", self.store.preferences_summary())
        self.assertNotIn("Mars", self.store.preferences_summary())
        self.assertEqual(len(self.store.search("")), 2)

    def test_corrupt_file_is_kept_not_lost(self):
        path = Path(self.dir.name) / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        store = memory.MemoryStore(path)
        self.assertEqual(store.all(), [])
        self.assertTrue(path.with_suffix(".corrupt.json").exists())

    def test_unavailable_embedder_falls_back_to_keywords(self):
        store = memory.MemoryStore(Path(self.dir.name) / "m2.json", memory.Embedder("http://127.0.0.1:9", "none", timeout=0.5))
        store.add("The user's chemistry test is on Friday", "school")
        self.assertEqual(len(store.search("chemistry test")), 1)


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = tasks.TaskStore(Path(self.dir.name) / "tasks.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_lifecycle(self):
        a = self.store.add("Chapter 5 worksheet", "2026-12-01", "assignment", "Chemistry", 1)
        b = self.store.add("Robot arm wiring", "", "project", "Robotics")
        self.assertEqual(a["due"], "2026-12-01T23:59")
        self.assertEqual([i["id"] for i in self.store.open_items()], [a["id"], b["id"]])
        self.assertEqual(len(self.store.open_items(subject="chem")), 1)
        self.store.set_done(a["id"])
        self.assertEqual([i["id"] for i in self.store.open_items()], [b["id"]])
        self.assertIsNotNone(self.store.delete(b["id"]))
        self.assertEqual(len(tasks.TaskStore(self.store.path).items), 1)

    def test_bad_due_date(self):
        with self.assertRaises(ValueError):
            self.store.add("x", "next friday")

    def test_describe_due(self):
        now = dt.datetime(2026, 11, 23, 12, 0)
        self.assertTrue(tasks.describe_due(dt.datetime(2026, 11, 22, 23, 59), now).startswith("OVERDUE"))
        self.assertEqual(tasks.describe_due(dt.datetime(2026, 11, 23, 23, 59), now), "due today")
        self.assertEqual(tasks.describe_due(dt.datetime(2026, 11, 24, 23, 59), now), "due tomorrow")
        self.assertIn("3:30 PM", tasks.describe_due(dt.datetime(2026, 11, 24, 15, 30), now))
        text = self.store.format([self.store.add("Essay", "2026-11-20", "assignment", "English")], now)
        self.assertIn("OVERDUE", text)
        self.assertIn("[English]", text)


class SettingsTests(unittest.TestCase):
    def test_defaults_and_merge(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            s = settings.load(path)
            self.assertEqual(s["listen_mode"], "conversation")
            self.assertTrue(path.exists())  # starter file created
            path.write_text(json.dumps({"follow_up_seconds": 5, "voice": {"rate": "+20%"}, "_note": "x"}))
            s = settings.load(path)
            self.assertEqual(s["follow_up_seconds"], 5)
            self.assertEqual(s["voice"]["rate"], "+20%")
            self.assertEqual(s["voice"]["neural_voice"], settings.DEFAULTS["voice"]["neural_voice"])
            self.assertNotIn("_note", s)

    def test_broken_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            path.write_text("{oops")
            self.assertEqual(settings.load(path)["listen_mode"], "conversation")
            path.write_text(json.dumps({"listen_mode": "telepathy"}))
            self.assertEqual(settings.load(path)["listen_mode"], "conversation")


class ToolTests(unittest.TestCase):
    def setUp(self):
        import tools

        self.tools = tools
        self.dir = tempfile.TemporaryDirectory()
        self._orig = (tools.REMINDERS_FILE, tools.memory_store, tools.task_store)
        tools.REMINDERS_FILE = Path(self.dir.name) / "reminders.json"
        tools.memory_store = memory.MemoryStore(Path(self.dir.name) / "memory.json")
        tools.task_store = tasks.TaskStore(Path(self.dir.name) / "tasks.json")

    def tearDown(self):
        self.tools.REMINDERS_FILE, self.tools.memory_store, self.tools.task_store = self._orig
        self.tools._reminders.clear()
        self.dir.cleanup()

    def test_reminder_cancel(self):
        t = self.tools
        t.set_reminder.call({"message": "take the pizza out", "minutes_from_now": 30})
        t.set_reminder.call({"message": "call grandma", "minutes_from_now": 60})
        self.assertIn("Cancelled 1", t.cancel_reminders.call({"contains": "pizza"}))
        self.assertIn("grandma", t.list_reminders.call({}))
        self.assertIn("Cancelled 1", t.cancel_reminders.call({}))
        self.assertEqual(t.list_reminders.call({}), "No upcoming reminders.")

    def test_memory_and_task_tools(self):
        t = self.tools
        self.assertIn("Remembered #1", t.remember.call({"text": "The user likes lofi music", "category": "preference"}))
        self.assertIn("lofi", t.recall.call({"query": "music"}))
        self.assertIn("lofi", t.list_all_memories.call({}))
        self.assertIn("Deleted", t.forget.call({"memory_ids": [1]}))
        self.assertEqual(t.list_all_memories.call({}), "Memory is empty.")
        self.assertIn("Physics", t.add_task.call({"title": "Lab report", "due": "2030-01-05", "kind": "assignment", "subject": "Physics"}))
        self.assertIn("Lab report", t.list_tasks.call({}))
        self.assertIn("Marked done", t.complete_task.call({"task_id": 1}))
        self.assertEqual(t.list_tasks.call({}), "No open tasks.")

    def test_close_application_refuses_tiny_names(self):
        self.assertIn("too short", self.tools.close_application.call({"name": "e"}))

    def test_all_tools_have_schemas(self):
        names = [t.name for t in self.tools.ALL_TOOLS]
        self.assertEqual(len(names), len(set(names)))
        for t in self.tools.ALL_TOOLS:
            self.assertTrue(t.description)
            self.assertEqual(t.input_schema["type"], "object")


if __name__ == "__main__":
    unittest.main()
