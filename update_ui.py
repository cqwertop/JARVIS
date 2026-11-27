"""The "Check for updates" menu item and the start-up update notice (see updater.py for the logic).

Network work runs on a background thread; every window is opened on the panel's own thread via hud.call_soon.
"""

import logging
import threading
import webbrowser

import updater
from version import __version__

log = logging.getLogger("kairo.update_ui")
TITLE = "KAIRO update"


def _mb():
    from tkinter import messagebox

    return messagebox


def _what_changed(notes: str, limit: int = 700) -> str:
    text = notes.replace("\r\n", "\n").strip()
    if len(text) > limit:
        text = text[:limit].rsplit("\n", 1)[0] + "\n..."
    return text


class UpdateUI:
    def __init__(self, hud, assistant, include_beta: bool | None = None):
        self.hud = hud
        self.assistant = assistant
        self.include_beta = include_beta
        self._busy = threading.Lock()

    # ------------------------------------------------------------------ entry points

    def check_now(self):
        """Menu item: check, then say what was found (including 'you're up to date')."""
        threading.Thread(target=self._check, args=(True,), daemon=True, name="update-check-now").start()

    def announce(self, release: updater.Release):
        """Background checker found a new version: show it on the panel without interrupting."""
        label = "beta " if release.prerelease else ""
        self.assistant._show(self.assistant._hud_state or "standby",
                             f"Update {label}{release.version}: right-click > Check for updates")

    # ------------------------------------------------------------------ steps

    def _status(self, text: str):
        self.assistant._show(self.assistant._hud_state or "standby", text)

    def _check(self, manual: bool):
        if not self._busy.acquire(blocking=False):
            return  # a check or download is already running
        try:
            self._status("Checking for updates...")
            try:
                release = updater.check(self.include_beta)
            except updater.UpdateError as exc:
                self._status("")
                self.hud.call_soon(lambda: _mb().showerror(TITLE, str(exc)))
                return
            self._status("")
            if release is None:
                if manual:
                    self.hud.call_soon(lambda: _mb().showinfo(
                        TITLE, f"You have the newest version of KAIRO ({__version__})."))
                return
            self.hud.call_soon(lambda: self._offer(release))
        finally:
            self._busy.release()

    def _offer(self, release: updater.Release):
        kind = updater.install_kind()
        beta = " (beta)" if release.prerelease else ""
        changes = _what_changed(release.notes)
        intro = f"KAIRO {release.version}{beta} is available. You have {__version__}."
        if kind not in updater.NEEDS_FILE or not release.asset_url:
            if _mb().askyesno(TITLE, f"{intro}\n\nOpen the release page to get it?"):
                webbrowser.open(release.page_url)
            return
        size = f" ({release.asset_size / 1_048_576:.0f} MB)" if release.asset_size else ""
        question = (f"{intro}\n\n" + (f"What's new:\n{changes}\n\n" if changes else "") +
                    f"Download{size} and install it now?\n"
                    + ("KAIRO closes; drag the new KAIRO into Applications to replace the old one."
                       if kind == "macos" else "KAIRO closes so Windows can update it.")
                    + " Your settings and memories are kept.")
        if _mb().askyesno(TITLE, question):
            threading.Thread(target=self._install, args=(release,), daemon=True, name="update-download").start()

    def _install(self, release: updater.Release):
        if not self._busy.acquire(blocking=False):
            return
        try:
            last = {"pct": -1}

            def progress(done: int, total: int):
                pct = int(done * 100 / total) if total else 0
                if pct != last["pct"] and pct % 5 == 0:
                    last["pct"] = pct
                    self._status(f"Downloading update... {pct}%")

            try:
                path = updater.download(release, progress)
            except updater.UpdateError as exc:
                self._status("")
                self.hud.call_soon(lambda: _mb().showerror(TITLE, str(exc)))
                return
            self._status("Opening the update...")
            log.info("Installing update %s from %s", release.version, path)
            try:
                updater.launch(path)
            except OSError as exc:
                self.hud.call_soon(lambda: _mb().showerror(
                    TITLE, f"Couldn't open the update ({exc}).\nIt was saved here:\n{path}"))
                return
            self.assistant.quit()  # let Windows replace KAIRO's files
        finally:
            self._busy.release()
