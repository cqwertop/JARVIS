"""Moving users' data and keys over from the app's old name (JARVIS) to KAIRO."""
import sys
import tempfile
import types
import unittest
from pathlib import Path

import credentials
import paths


class DataFolderMove(unittest.TestCase):
    def test_old_folder_is_moved(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new = Path(tmp) / "JARVIS", Path(tmp) / "KAIRO"
            (old / "data").mkdir(parents=True)
            (old / "data" / "settings.json").write_text("{}")
            self.assertEqual(paths._moved_from_old_name(old, new), new)
            self.assertTrue((new / "data" / "settings.json").exists())
            self.assertFalse(old.exists())

    def test_existing_new_folder_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new = Path(tmp) / "JARVIS", Path(tmp) / "KAIRO"
            old.mkdir()
            new.mkdir()
            self.assertEqual(paths._moved_from_old_name(old, new), new)
            self.assertTrue(old.exists())  # left alone

    def test_fresh_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            new = Path(tmp) / "KAIRO"
            self.assertEqual(paths._moved_from_old_name(Path(tmp) / "JARVIS", new), new)


class KeyMove(unittest.TestCase):
    def setUp(self):
        self.store = {}
        fake = types.ModuleType("keyring")
        fake.get_password = lambda service, account: self.store.get((service, account))
        fake.set_password = lambda service, account, secret: self.store.__setitem__((service, account), secret)
        fake.delete_password = lambda service, account: self.store.pop((service, account))
        self._real = sys.modules.get("keyring")
        sys.modules["keyring"] = fake

    def tearDown(self):
        if self._real is not None:
            sys.modules["keyring"] = self._real
        else:
            sys.modules.pop("keyring", None)

    def test_key_under_old_name_is_moved(self):
        self.store[("JARVIS", "openai_api_key")] = "sk-old"
        self.assertEqual(credentials.get("openai_api_key"), "sk-old")
        self.assertEqual(self.store, {("KAIRO", "openai_api_key"): "sk-old"})

    def test_new_name_preferred(self):
        self.store[("JARVIS", "openai_api_key")] = "sk-old"
        self.store[("KAIRO", "openai_api_key")] = "sk-new"
        self.assertEqual(credentials.get("openai_api_key"), "sk-new")

    def test_missing_key(self):
        self.assertIsNone(credentials.get("openai_api_key"))


if __name__ == "__main__":
    unittest.main()
