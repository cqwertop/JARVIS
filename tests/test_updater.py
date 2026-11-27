"""Update logic: which GitHub release to offer, and checksum checking of the download."""
import hashlib
import tempfile
import unittest
from pathlib import Path

import updater


def release(tag, prerelease=False, draft=False, assets=("msix",)):
    files = []
    for kind in assets:
        name = {"msix": f"KAIRO-{tag.lstrip('v')}.msixbundle", "installer": f"KAIRO-Setup-{tag.lstrip('v')}.exe",
                "cer": "KAIRO.cer"}[kind]
        files.append({"name": name, "browser_download_url": f"https://example.invalid/{name}", "size": 10,
                      "digest": "sha256:" + "ab" * 32})
    return {"tag_name": tag, "name": tag, "prerelease": prerelease, "draft": draft, "assets": files,
            "html_url": f"https://example.invalid/{tag}", "body": "notes"}


class Versions(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updater.parse_version("v0.10.0")[:3], (0, 10, 0))
        self.assertEqual(updater.parse_version("0.10.0-beta.2"), (0, 10, 0, 2))
        self.assertEqual(updater.parse_version("0.10.0b2"), (0, 10, 0, 2))
        self.assertIsNone(updater.parse_version("latest"))

    def test_beta_sorts_before_final(self):
        self.assertLess(updater.parse_version("0.10.0-beta.9"), updater.parse_version("0.10.0"))
        self.assertLess(updater.parse_version("0.9.1"), updater.parse_version("0.10.0-beta.1"))
        self.assertLess(updater.parse_version("0.10.0-beta.2"), updater.parse_version("0.10.0-beta.10"))


class PickUpdate(unittest.TestCase):
    RELEASES = [release("v0.10.0-beta.2", prerelease=True), release("v0.10.0-beta.1", prerelease=True),
                release("v0.9.1")]

    def test_stable_user_is_not_offered_betas(self):
        self.assertIsNone(updater.pick_update(self.RELEASES, current="0.9.1", kind="msix"))

    def test_beta_user_gets_newest_beta(self):
        r = updater.pick_update(self.RELEASES, current="0.10.0-beta.1", kind="msix")
        self.assertEqual(r.version, "0.10.0-beta.2")
        self.assertEqual(r.asset_name, "KAIRO-0.10.0-beta.2.msixbundle")
        self.assertEqual(r.sha256, "ab" * 32)

    def test_opt_in_to_betas(self):
        r = updater.pick_update(self.RELEASES, current="0.9.1", include_beta=True, kind="msix")
        self.assertEqual(r.version, "0.10.0-beta.2")

    def test_final_beats_its_betas(self):
        r = updater.pick_update(self.RELEASES + [release("v0.10.0")], current="0.10.0-beta.2", kind="msix")
        self.assertEqual(r.version, "0.10.0")

    def test_up_to_date_and_drafts(self):
        self.assertIsNone(updater.pick_update([release("v0.9.1"), release("v1.0.0", draft=True)],
                                              current="0.9.1", kind="msix"))

    def test_needs_a_file_for_this_install(self):
        only_msix = [release("v1.0.0")]
        self.assertIsNone(updater.pick_update(only_msix, current="0.9.1", kind="installer"))
        self.assertEqual(updater.pick_update([release("v1.0.0", assets=("installer", "cer"))], current="0.9.1",
                                             kind="installer").asset_name, "KAIRO-Setup-1.0.0.exe")
        # Source installs are pointed at the release page, so a file isn't required.
        self.assertEqual(updater.pick_update(only_msix, current="0.9.1", kind="source").version, "1.0.0")


class PlatformReleases(unittest.TestCase):
    """macOS and Linux builds live in their own releases, tagged ...-macos / ...-linux."""

    def _rel(self, tag, names):
        r = release(tag, prerelease=True, assets=())
        r["assets"] = [{"name": n, "browser_download_url": f"https://example.invalid/{n}", "size": 5,
                        "digest": "sha256:" + "cd" * 32} for n in names]
        return r

    def setUp(self):
        self.releases = [
            self._rel("v0.10.0-beta.2-macos", ["KAIRO-0.10.0-beta.2-macOS-arm64.dmg",
                                               "KAIRO-0.10.0-beta.2-macOS-x86_64.dmg"]),
            self._rel("v0.10.0-beta.2-linux", ["kairo_0.10.0-beta.2_amd64.deb"]),
            release("v0.10.0-beta.1", prerelease=True),
        ]

    def test_tag_parsing(self):
        self.assertEqual(updater.tag_platform("v0.10.0-beta.2-macos"), "macos")
        self.assertIsNone(updater.tag_platform("v0.10.0-beta.2"))
        self.assertEqual(updater.parse_version("v0.10.0-beta.2-linux"), (0, 10, 0, 2))

    def test_windows_ignores_other_platforms(self):
        self.assertIsNone(updater.pick_update(self.releases, current="0.10.0-beta.1", kind="msix"))

    def test_mac_gets_its_own_architecture(self):
        from unittest import mock

        with mock.patch("platform.machine", return_value="arm64"):
            r = updater.pick_update(self.releases, current="0.10.0-beta.1", kind="macos")
        self.assertEqual((r.version, r.asset_name), ("0.10.0-beta.2", "KAIRO-0.10.0-beta.2-macOS-arm64.dmg"))
        with mock.patch("platform.machine", return_value="x86_64"):
            r = updater.pick_update(self.releases, current="0.10.0-beta.1", kind="macos")
        self.assertEqual(r.asset_name, "KAIRO-0.10.0-beta.2-macOS-x86_64.dmg")

    def test_linux_gets_the_release_page(self):
        r = updater.pick_update(self.releases, current="0.10.0-beta.1", kind="linux")
        self.assertEqual(r.version, "0.10.0-beta.2")
        self.assertIn("linux", r.page_url)


class Download(unittest.TestCase):
    def _release(self, src: Path, sha: str | None):
        return updater.Release(version="1.0.0", name="1.0.0", page_url="", notes="", prerelease=False,
                               asset_name="KAIRO-1.0.0.msixbundle", asset_url=src.as_uri(),
                               asset_size=src.stat().st_size, sha256=sha)

    def test_good_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.bin"
            src.write_bytes(b"package bytes" * 1000)
            seen = []
            out = updater.download(self._release(src, hashlib.sha256(src.read_bytes()).hexdigest()),
                                   progress=lambda d, t: seen.append((d, t)), folder=Path(tmp) / "dl")
            self.assertEqual(out.read_bytes(), src.read_bytes())
            self.assertEqual(seen[-1][0], src.stat().st_size)

    def test_bad_checksum_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.bin"
            src.write_bytes(b"tampered")
            with self.assertRaises(updater.UpdateError):
                updater.download(self._release(src, "00" * 32), folder=Path(tmp) / "dl")
            self.assertEqual(list((Path(tmp) / "dl").iterdir()), [])

    def test_missing_checksum_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.bin"
            src.write_bytes(b"x")
            with self.assertRaises(updater.UpdateError):
                updater.download(self._release(src, None), folder=Path(tmp) / "dl")


if __name__ == "__main__":
    unittest.main()
