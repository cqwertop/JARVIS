"""A small always-on-top status panel (the visible "is JARVIS listening?" indicator) plus global hotkeys.

The panel shows what JARVIS is doing and has buttons to mute the microphone, stop JARVIS talking, and
start talking without saying its name. Drag it anywhere; right-click it to hide it until JARVIS restarts.
Runs on its own thread; other threads call set_state(), which is thread-safe.
"""

import logging
import math
import queue
import sys
import threading

log = logging.getLogger("jarvis.hud")

# state -> (label, colour)
STATES = {
    "starting": ("STARTING", "#7f8c9a"),
    "standby": ("STANDBY", "#2a9fd6"),  # mic on, waiting for "Jarvis"
    "listening": ("LISTENING", "#29e0ff"),  # in a conversation - no name needed
    "thinking": ("THINKING", "#ffb347"),
    "speaking": ("SPEAKING", "#5ad1ff"),
    "muted": ("MIC OFF", "#ff5a5a"),
    "push_to_talk": ("PRESS TALK", "#7f8c9a"),
    "error": ("PROBLEM", "#ff5a5a"),
}
BG, FG, DIM = "#0b1520", "#d8f6ff", "#6f8a99"


class Hud:
    def __init__(self, on_mute, on_stop, on_talk, hotkeys: dict | None = None):
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._callbacks = {"mute": on_mute, "stop": on_stop, "talk": on_talk}
        self._hotkeys = hotkeys or {}
        self._state = "starting"
        self._phase = 0.0
        self.ok = False
        self._thread = threading.Thread(target=self._run, daemon=True, name="hud")
        self._thread.start()

    def set_state(self, state: str, detail: str | None = None):
        self._q.put(("state", state, detail))

    def set_muted(self, muted: bool):
        self._q.put(("muted", muted, None))

    def close(self):
        self._q.put(("quit", None, None))

    # ------------------------------------------------------------------ tk thread
    def _run(self):
        try:
            import tkinter as tk
        except Exception as exc:
            log.warning("On-screen indicator unavailable: %r", exc)
            return
        try:
            root = tk.Tk()
        except Exception as exc:  # no display (e.g. headless Linux)
            log.warning("On-screen indicator unavailable: %r", exc)
            return
        self.ok = True
        self._tk = tk
        root.title("JARVIS")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-alpha", 0.93)
        except tk.TclError:
            pass
        root.configure(bg=BG, highlightthickness=1, highlightbackground="#1d3a4d")
        # Layout managers (not fixed pixel positions) so the panel fits any display scaling.
        self._canvas = tk.Canvas(root, width=56, height=56, bg=BG, highlightthickness=0)
        self._canvas.grid(row=0, column=0, rowspan=3, padx=(8, 6), pady=8)
        top = tk.Frame(root, bg=BG)
        top.grid(row=0, column=1, sticky="w", padx=(0, 10), pady=(6, 0))
        self._title = tk.Label(top, text="JARVIS", fg=FG, bg=BG, font=("Segoe UI Semibold", 11))
        self._title.pack(side="left")
        self._status = tk.Label(top, text="STARTING", fg=DIM, bg=BG, font=("Consolas", 9, "bold"))
        self._status.pack(side="left", padx=(8, 0))
        self._detail = tk.Label(root, text="", fg=DIM, bg=BG, font=("Segoe UI", 8), anchor="w", width=34)
        self._detail.grid(row=1, column=1, sticky="w", padx=(0, 10))
        buttons = tk.Frame(root, bg=BG)
        buttons.grid(row=2, column=1, sticky="w", pady=(2, 8))

        def button(text, key, tip, width=6):
            b = tk.Label(buttons, text=text, fg=FG, bg="#12283a", font=("Segoe UI", 8, "bold"), width=width,
                         pady=2, cursor="hand2")
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e: self._fire(key))
            b.bind("<Enter>", lambda e: (b.configure(bg="#1d4460"), self._detail.configure(text=tip)))
            b.bind("<Leave>", lambda e: b.configure(bg="#12283a"))
            return b

        keys = self._hotkeys

        def tip(text, name):
            return f"{text} ({keys[name]})" if keys.get(name) else text

        self._mute_btn = button("MUTE", "mute", tip("Turn the microphone off/on", "mute"), width=8)
        button("STOP", "stop", tip("Stop JARVIS talking", "stop"))
        button("TALK", "talk", tip("Talk without saying the name", "talk"))
        root.update_idletasks()
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        root.geometry(f"+{root.winfo_screenwidth() - w - 24}+{root.winfo_screenheight() - h - 72}")

        drag = {}
        for widget in (root, self._canvas, self._title, self._status, self._detail):
            widget.bind("<ButtonPress-1>", lambda e: drag.update(x=e.x_root - root.winfo_x(), y=e.y_root - root.winfo_y()))
            widget.bind("<B1-Motion>", lambda e: root.geometry(f"+{e.x_root - drag['x']}+{e.y_root - drag['y']}"))
            widget.bind("<Button-3>", lambda e: root.withdraw())
        self._root = root
        self._draw()
        root.after(100, self._poll)
        root.mainloop()

    def _fire(self, key):
        try:
            self._callbacks[key]()
        except Exception as exc:
            log.error("HUD %s button failed: %r", key, exc)

    def _poll(self):
        try:
            while True:
                kind, value, detail = self._q.get_nowait()
                if kind == "quit":
                    self._root.destroy()
                    return
                if kind == "muted":
                    self._mute_btn.configure(text="UNMUTE" if value else "MUTE")
                if kind == "state" and value in STATES:
                    self._state = value
                    label, colour = STATES[value]
                    self._status.configure(text=label, fg=colour)
                    if detail is not None:
                        self._detail.configure(text=detail[:60])
        except queue.Empty:
            pass
        self._draw()
        # Animate only while something is happening; otherwise redraw rarely to save CPU.
        busy = self._state in ("listening", "thinking", "speaking")
        self._root.after(60 if busy else 400, self._poll)

    def _draw(self):
        c = self._canvas
        c.delete("all")
        _, colour = STATES.get(self._state, STATES["standby"])
        self._phase += 0.25
        busy = self._state in ("listening", "thinking", "speaking")
        pulse = (math.sin(self._phase) + 1) / 2 if busy else 0.3
        cx = cy = 28
        c.create_oval(4, 4, 52, 52, outline="#1d3a4d", width=2)
        r = 14 + 8 * pulse
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=colour, width=2)
        if self._state == "thinking":
            start = (self._phase * 40) % 360
            c.create_arc(6, 6, 50, 50, start=start, extent=90, style="arc", outline=colour, width=3)
        c.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill=colour, outline="")
        if self._state == "muted":
            c.create_line(12, 44, 44, 12, fill=colour, width=3)


# --------------------------------------------------------------------------- global hotkeys (Windows)

_MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}


def parse_hotkey(text: str) -> tuple[int, int]:
    """'ctrl+alt+m' -> (modifiers, virtual-key code)."""
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    if not parts:
        raise ValueError("empty hotkey")
    mods = 0
    for p in parts[:-1]:
        if p not in _MODS:
            raise ValueError(f"unknown modifier {p!r}")
        mods |= _MODS[p]
    key = parts[-1]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    elif key in ("space", "pause"):
        vk = {"space": 0x20, "pause": 0x13}[key]
    else:
        raise ValueError(f"unknown key {key!r}")
    return mods | 0x4000, vk  # 0x4000 = MOD_NOREPEAT


def start_hotkeys(bindings: dict[str, tuple[str, callable]]) -> list[str]:
    """bindings: name -> (hotkey text, callback). Returns a description of the hotkeys that registered."""
    if sys.platform != "win32":
        log.info("Global hotkeys are only implemented on Windows so far.")
        return []
    import ctypes
    from ctypes import wintypes

    registered: list[str] = []
    ready = threading.Event()

    def loop():
        user32 = ctypes.windll.user32
        actions = {}
        for i, (name, (text, cb)) in enumerate(bindings.items(), start=1):
            try:
                mods, vk = parse_hotkey(text)
            except ValueError as exc:
                log.error("Hotkey %s=%r is invalid: %s", name, text, exc)
                continue
            if user32.RegisterHotKey(None, i, mods, vk):
                actions[i] = cb
                registered.append(f"{name}: {text}")
            else:
                log.warning("Hotkey %s (%s) is already used by another program.", name, text)
        ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312 and msg.wParam in actions:  # WM_HOTKEY
                try:
                    actions[msg.wParam]()
                except Exception as exc:
                    log.error("Hotkey action failed: %r", exc)

    threading.Thread(target=loop, daemon=True, name="hotkeys").start()
    ready.wait(3)
    return registered
