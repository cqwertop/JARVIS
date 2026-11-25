"""KAIRO Setup - the step-by-step wizard that runs the first time KAIRO starts (and from Settings later).

It checks the computer, lets you choose how KAIRO thinks (Claude online, or a free local model with Ollama),
tests your microphone and speakers, and saves everything. Nothing is downloaded or changed until you press
the button on the last step. Visual design and plain-language wording started in the original installer
session; this version runs inside the packaged app on Windows, macOS and Linux.

    KAIRO --setup            open the wizard
    python kairo_app.py --setup
"""

import queue
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter import font as tkfont

import checks
import paths
import providers
import steps
from steps import StepError

BG, PANEL, EDGE = "#07111c", "#0d1d2e", "#1b3a55"
CYAN, GOLD, GREEN, RED = "#3ee0ff", "#f0b429", "#3dd68c", "#ff5c6c"
TEXT, MUTED = "#e6f4ff", "#8aa6bf"
UI = {"win32": "Segoe UI", "darwin": "Helvetica Neue"}.get(sys.platform, "DejaVu Sans")
MONO = {"win32": "Consolas", "darwin": "Menlo"}.get(sys.platform, "DejaVu Sans Mono")

ANTHROPIC_CONSOLE = "https://console.anthropic.com/settings/keys"
CLAUDE_CODE_PAGE = "https://claude.com/claude-code"
# Using a Claude Pro/Max plan through Claude Code is for the plan owner's own use. Anthropic doesn't allow apps
# given to other people to run on someone's plan sign-in, so the packaged installer only offers API keys.
PLAN_OPTION = not paths.FROZEN
OLLAMA_DOWNLOAD = "https://ollama.com/download"

ENGINES = [
    {"key": "online", "title": "Online AI service", "badge": "Smartest",
     "text": "Connect KAIRO to Claude, ChatGPT (OpenAI), Google Gemini or another online AI. Your computer doesn't "
             "need to run the AI itself. Needs an API key from that company.", "available": True},
    {"key": "ollama", "title": "Ollama (on this computer)", "badge": "Free & private",
     "text": "Run an AI model directly on your computer. You don't need an API key, and it works offline. "
             "Slower on computers without a strong graphics card.", "available": True},
    {"key": "llamacpp", "title": "llama.cpp", "badge": "",
     "text": "Run an AI model directly on your computer using a lightweight local engine.", "available": False},
    {"key": "transformers", "title": "Hugging Face Transformers", "badge": "",
     "text": "Run AI models with the Transformers library. Needs a lot of memory and storage.", "available": False},
]

LISTEN_MODES = [
    ("conversation", "Say \"Kairo\" once, then just talk",
     "Recommended. After it answers you can keep talking without the name. It goes back to waiting after 20 "
     "quiet seconds. The microphone stays on, but only words after \"Kairo\" are acted on."),
    ("wake_word", "Say \"Kairo\" every time", "KAIRO only reacts to sentences that include its name."),
    ("push_to_talk", "Press a button to talk",
     "The microphone is off until you press TALK on the panel" + (" or Ctrl+Alt+J." if sys.platform == "win32" else ".")),
    ("text", "Type only - no microphone", "The microphone is never used. Type to KAIRO in its panel."),
]


class Wizard(tk.Tk):
    SCREENS = ["welcome", "check", "engine", "brain", "voice", "extras", "install", "done"]

    def __init__(self, restart_kairo_on_close: bool = False):
        super().__init__()
        self.restart_kairo_on_close = restart_kairo_on_close
        self.title("KAIRO Setup")
        self.configure(bg=BG)
        self.geometry("820x660")
        self.minsize(680, 580)
        self.option_add("*Font", (UI, 10))
        self.title_font = tkfont.Font(family=UI, size=20, weight="bold")
        self.big_font = tkfont.Font(family=UI, size=12)
        self.mono_font = tkfont.Font(family=MONO, size=9)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("J.Horizontal.TProgressbar", troughcolor=PANEL, background=CYAN, bordercolor=EDGE,
                        lightcolor=CYAN, darkcolor=CYAN)
        style.configure("J.TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=CYAN)

        existing = steps.current_settings()
        defaults = steps.settings_mod.DEFAULTS
        self.report: checks.SystemReport | None = None
        backend = existing.get("backend")
        online = existing.get("online", {})
        self.engine = "ollama" if backend == "ollama" else "online"
        self.provider = online.get("provider") if backend == "online" and online.get("provider") else "anthropic"
        self.claude_mode = "plan" if backend == "pro" and PLAN_OPTION else "api"
        self.base_url = online.get("base_url", "")
        self.model = online.get("model", "") if backend == "online" else existing.get("claude_model_api", "")
        self.models: list[str] = []
        self.key_checked_for: str | None = None
        self.api_key = ""
        self.ollama_model = existing.get("ollama_model", "qwen3:4b")
        self.want_embeddings = True
        self.mic_name = existing.get("microphone_name", "")
        self.voice = existing.get("voice", {}).get("neural_voice", defaults["voice"]["neural_voice"])
        self.listen_mode = existing.get("listen_mode", "conversation")
        self.start_at_login = steps.start_at_login_enabled() if existing.get("setup_complete") else True
        self.show_panel = existing.get("hud", True)
        self.done_steps: set[str] = set()
        self.cancel_flag = threading.Event()
        self.worker: threading.Thread | None = None
        self.events: queue.Queue = queue.Queue()
        self.current = "welcome"
        self.finished_ok = False

        # Header and footer are packed first so the Back/Next buttons always stay visible; the middle scrolls
        # when a page is taller than the window (small screens, large text settings).
        self.header = tk.Frame(self, bg=BG)
        self.header.pack(side="top", fill="x", padx=24, pady=(18, 4))
        self.footer = tk.Frame(self, bg=BG)
        self.footer.pack(side="bottom", fill="x", padx=24, pady=(8, 18))
        middle = tk.Frame(self, bg=BG)
        middle.pack(side="top", fill="both", expand=True, padx=(24, 8))
        self._canvas = tk.Canvas(middle, bg=BG, highlightthickness=0)
        self._scrollbar = tk.Scrollbar(middle, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self._canvas, bg=BG)
        self._body_window = self._canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self._update_scroll())
        self._canvas.bind("<Configure>", lambda e: (self._canvas.itemconfigure(self._body_window, width=e.width),
                                                    self._update_scroll()))
        self.bind_all("<MouseWheel>", self._on_wheel)
        self.bind_all("<Button-4>", lambda e: self._canvas.yview_scroll(-2, "units"))
        self.bind_all("<Button-5>", lambda e: self._canvas.yview_scroll(2, "units"))
        self.bind("<Escape>", lambda e: self.confirm_cancel())
        self.protocol("WM_DELETE_WINDOW", self.confirm_cancel)
        self.after(100, self._poll_events)
        self.show("welcome")

    # ------------------------------------------------------------------ helpers
    def _update_scroll(self):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        overflow = self.body.winfo_reqheight() > self._canvas.winfo_height() + 2
        if overflow and not self._scrollbar.winfo_ismapped():
            self._scrollbar.pack(side="right", fill="y")
        elif not overflow and self._scrollbar.winfo_ismapped():
            self._scrollbar.pack_forget()

    def _on_wheel(self, event):
        if self.body.winfo_reqheight() > self._canvas.winfo_height():
            step = -1 * (event.delta // 120 if sys.platform == "win32" else event.delta)
            self._canvas.yview_scroll(step, "units")

    def show(self, name: str):
        self.current = name
        for frame in (self.header, self.body, self.footer):
            for child in frame.winfo_children():
                child.destroy()
        self.unbind("<Return>")
        self._canvas.yview_moveto(0)
        self._draw_header()
        getattr(self, f"screen_{name}")()

    def _draw_header(self):
        tk.Label(self.header, text="J . A . R . V . I . S", bg=BG, fg=CYAN, font=(UI, 11, "bold")).pack(side="left")
        idx = self.SCREENS.index(self.current)
        dots = tk.Frame(self.header, bg=BG)
        dots.pack(side="right")
        tk.Label(dots, text=f"Step {idx + 1} of {len(self.SCREENS)}  ", bg=BG, fg=MUTED).pack(side="left")
        for i, _ in enumerate(self.SCREENS):
            tk.Label(dots, text="●", fg=CYAN if i <= idx else EDGE, bg=BG, font=(UI, 11)).pack(side="left", padx=1)

    def _button(self, parent, text, command, primary=False, side="right", enabled=True):
        btn = tk.Button(parent, text=text, command=command, bg=CYAN if primary else PANEL, fg=BG if primary else TEXT,
                        activebackground=CYAN, activeforeground=BG, relief="flat", padx=18, pady=7, cursor="hand2",
                        highlightthickness=1, highlightbackground=EDGE, bd=0, font=(UI, 10, "bold" if primary else "normal"))
        btn.pack(side=side, padx=(8, 0) if side == "right" else (0, 8))
        if not enabled:
            self._enable(btn, False, primary)
        return btn

    @staticmethod
    def _enable(btn, enabled: bool, primary: bool = True):
        try:
            if enabled:
                btn.configure(state="normal", bg=CYAN if primary else PANEL, fg=BG if primary else TEXT)
            else:
                btn.configure(state="disabled", bg=EDGE, fg=MUTED)
        except tk.TclError:
            pass

    def _nav(self, back=None, nxt=None, next_text="Next", next_enabled=True):
        if back:
            self._button(self.footer, "Back", back, side="left")
        btn = None
        if nxt:
            btn = self._button(self.footer, next_text, nxt, primary=True, enabled=next_enabled)
            self.bind("<Return>", lambda e: nxt() if str(btn["state"]) == "normal" else None)
            btn.focus_set()
        return btn

    def _title(self, title, subtitle=""):
        tk.Label(self.body, text=title, bg=BG, fg=TEXT, font=self.title_font, anchor="w", justify="left",
                 wraplength=740).pack(fill="x", pady=(6, 2))
        if subtitle:
            tk.Label(self.body, text=subtitle, bg=BG, fg=MUTED, font=self.big_font, anchor="w", justify="left",
                     wraplength=740).pack(fill="x", pady=(0, 10))

    def _text(self, parent, text, fg=MUTED, **pack):
        lbl = tk.Label(parent, text=text, bg=parent["bg"], fg=fg, wraplength=720, justify="left", anchor="w")
        lbl.pack(fill="x", **(pack or {"pady": (4, 0)}))
        return lbl

    def _radio(self, parent, text, var, value, sub="", command=None, enabled=True):
        row = tk.Frame(parent, bg=parent["bg"])
        row.pack(fill="x", pady=3, anchor="w")
        rb = tk.Radiobutton(row, text=text, variable=var, value=value, bg=parent["bg"], fg=TEXT, selectcolor=BG,
                            activebackground=parent["bg"], activeforeground=CYAN, anchor="w", font=(UI, 10, "bold"),
                            command=command, state="normal" if enabled else "disabled", disabledforeground=MUTED)
        rb.pack(fill="x", anchor="w")
        if sub:
            tk.Label(row, text=sub, bg=parent["bg"], fg=MUTED, wraplength=680, justify="left",
                     anchor="w").pack(fill="x", padx=(26, 0))
        return rb

    def _check(self, parent, text, var, sub=""):
        cb = tk.Checkbutton(parent, text=text, variable=var, bg=parent["bg"], fg=TEXT, selectcolor=BG,
                            activebackground=parent["bg"], activeforeground=CYAN, anchor="w", font=(UI, 10, "bold"))
        cb.pack(fill="x", anchor="w", pady=(6, 0))
        if sub:
            tk.Label(parent, text=sub, bg=parent["bg"], fg=MUTED, wraplength=680, justify="left",
                     anchor="w").pack(fill="x", padx=(26, 0))
        return cb

    def _card(self, parent, **grid):
        card = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=EDGE)
        if grid:
            card.grid(**grid)
        else:
            card.pack(fill="x", pady=6)
        return card

    def confirm_cancel(self):
        busy = self.worker is not None and self.worker.is_alive()
        if self.current == "done":
            self._close()
            return
        msg = ("Setup is still working. Stop after the current step and close?" if busy
               else "Close KAIRO Setup? Your choices so far won't be saved, and you can run setup again any time.")
        if messagebox.askyesno("Close setup?", msg, parent=self):
            self.cancel_flag.set()
            self._close()

    def _close(self):
        if self.restart_kairo_on_close and steps.current_settings().get("setup_complete"):
            steps.launch_kairo(["--restarted"])
        self.destroy()

    # ------------------------------------------------------------------ 1. welcome
    def screen_welcome(self):
        art = tk.Canvas(self.body, height=150, bg=BG, highlightthickness=0)
        art.pack(fill="x", pady=(6, 0))
        art.bind("<Configure>", lambda e: self._draw_logo(art, e.width))
        self._title("Welcome to KAIRO!",
                    "Let's get your personal AI assistant ready. Don't worry if you've never set up anything like "
                    "this before. We'll handle the technical stuff.")
        self._text(self.body, "This takes about 3 minutes. If you choose a local AI model, downloading it adds "
                   "10 to 30 minutes, depending on your internet speed.")
        self._text(self.body, "Nothing is downloaded or changed until the last step, and you can go back at any time.")
        self._nav(nxt=lambda: self.show("check"), next_text="Start")

    def _draw_logo(self, canvas, width):
        canvas.delete("all")
        cx, cy = width / 2, 75
        for r, color in ((70, EDGE), (52, "#15405e"), (34, CYAN)):
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=3)
        canvas.create_oval(cx - 18, cy - 18, cx + 18, cy + 18, fill=CYAN, outline="")
        canvas.create_text(cx, cy, text="J", fill=BG, font=(UI, 20, "bold"))

    # ------------------------------------------------------------------ 2. system check
    def screen_check(self):
        self._title("Checking your computer", "This takes a few seconds. Nothing is changed.")
        self.check_label = tk.Label(self.body, text="Looking at your computer...", bg=BG, fg=CYAN, font=self.big_font,
                                    anchor="w", justify="left", wraplength=720)
        self.check_label.pack(fill="x", pady=(6, 6))
        self.check_rows = tk.Frame(self.body, bg=BG)
        self.check_rows.pack(fill="both", expand=True)
        self.check_next = self._nav(back=lambda: self.show("welcome"), nxt=lambda: self.show("engine"),
                                    next_enabled=False)
        self._button(self.footer, "Check again", self._run_check, side="left")
        self._run_check()

    def _run_check(self):
        self._enable(self.check_next, False)
        for child in self.check_rows.winfo_children():
            child.destroy()
        self.check_label.configure(text="Looking at your computer...", fg=CYAN)
        threading.Thread(target=lambda: self.events.put(("check", checks.check_system(paths.DATA_DIR))),
                         daemon=True).start()

    def _show_check_results(self, report: checks.SystemReport):
        self.report = report
        for child in self.check_rows.winfo_children():
            child.destroy()
        self.check_label.configure(text=checks.describe_results(report), fg=GREEN if not report.problems else GOLD)
        rows = [("ok", line) for line in report.good_news] + [("warn", line) for line in report.problems]
        rows.append(("info", f"Graphics card: {report.gpu_name}." if report.gpu_name else
                     "Graphics card: not detected. That's fine - KAIRO works without one."))
        if report.ollama_found:
            rows.append(("info", "Ollama is installed" + (" and running." if report.ollama_running else " (not running right now).")))
        if report.claude_code_found:
            rows.append(("info", "Claude Code is installed."))
        for kind, text in rows:
            mark, color = {"ok": ("✔", GREEN), "warn": ("⚠", GOLD), "info": ("○", MUTED)}[kind]
            line = tk.Frame(self.check_rows, bg=BG)
            line.pack(fill="x", pady=2)
            tk.Label(line, text=mark, fg=color, bg=BG, width=2, font=(UI, 11)).pack(side="left", anchor="n")
            tk.Label(line, text=text, fg=TEXT, bg=BG, wraplength=680, justify="left", anchor="w").pack(side="left", fill="x")
        fixes = tk.Frame(self.check_rows, bg=BG)
        fixes.pack(fill="x", pady=(8, 0))
        if not report.internet and sys.platform == "win32":
            self._button(fixes, "Open network settings", lambda: webbrowser.open("ms-settings:network"), side="left")
        if not report.microphones and sys.platform == "win32":
            self._button(fixes, "Open microphone settings", lambda: webbrowser.open("ms-settings:privacy-microphone"),
                         side="left")
        self._enable(self.check_next, report.ram_gb >= checks.MIN_RAM_GB and report.disk_free_gb >= checks.MIN_FREE_DISK_GB)

    # ------------------------------------------------------------------ 3. engine
    def screen_engine(self):
        self._title("How should KAIRO think?", "Pick one. You can change this later from KAIRO's Settings.")
        grid = tk.Frame(self.body, bg=BG)
        grid.pack(fill="both", expand=True)
        self.engine_var = tk.StringVar(value=self.engine)
        self.engine_cards = {}
        for i, eng in enumerate(ENGINES):
            card = self._card(grid, row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            grid.grid_columnconfigure(i % 2, weight=1, uniform="c")
            grid.grid_rowconfigure(i // 2, weight=1)
            head = tk.Frame(card, bg=PANEL)
            head.pack(fill="x", padx=12, pady=(10, 2))
            tk.Label(head, text=f"{chr(65 + i)}   {eng['title']}", bg=PANEL, fg=TEXT, font=(UI, 12, "bold"),
                     anchor="w").pack(fill="x")
            if eng["badge"]:
                tk.Label(head, text=eng["badge"].upper(), bg=PANEL, fg=GOLD, font=(UI, 8, "bold"),
                         anchor="w").pack(fill="x", padx=(22, 0))
            tk.Label(card, text=eng["text"], bg=PANEL, fg=MUTED, wraplength=330, justify="left", anchor="w").pack(fill="x", padx=12)
            if eng["available"]:
                rb = tk.Radiobutton(card, text="Choose this", value=eng["key"], variable=self.engine_var, bg=PANEL,
                                    fg=CYAN, selectcolor=BG, activebackground=PANEL, command=self._paint_engine_cards)
                rb.pack(anchor="w", padx=10, pady=8)
                for w in (card, head):
                    w.bind("<Button-1>", lambda e, k=eng["key"]: (self.engine_var.set(k), self._paint_engine_cards()))
            else:
                tk.Label(card, text="Coming in a later version", bg=PANEL, fg=GOLD).pack(anchor="w", padx=12, pady=8)
            self.engine_cards[eng["key"]] = card
        self._paint_engine_cards()
        self._text(self.body, "Online services may charge for use. Local models are free but need a strong computer "
                   "to be fast.")
        self._nav(back=lambda: self.show("check"), nxt=self._engine_next)

    def _paint_engine_cards(self):
        for key, card in self.engine_cards.items():
            card.configure(highlightbackground=CYAN if self.engine_var.get() == key else EDGE,
                           highlightthickness=2 if self.engine_var.get() == key else 1)

    def _engine_next(self):
        self.engine = self.engine_var.get()
        self.show("brain")

    # ------------------------------------------------------------------ 4. the chosen brain
    def screen_brain(self):
        if self.engine == "online":
            self._screen_online()
        else:
            self._screen_ollama()

    # Online providers ------------------------------------------------------------------------------
    def _screen_online(self):
        self._title("Which online AI do you have a key for?",
                    "Choose the company where you got (or will get) your API key. You can change this later.")
        grid = tk.Frame(self.body, bg=BG)
        grid.pack(fill="x")
        self.provider_var = tk.StringVar(value=self.provider)
        self.provider_cards = {}
        for i, (pid, info) in enumerate(providers.PROVIDERS.items()):
            card = self._card(grid, row=i // 3, column=i % 3, sticky="nsew", padx=4, pady=4)
            grid.grid_columnconfigure(i % 3, weight=1, uniform="p")
            rb = tk.Radiobutton(card, text=info["label"], value=pid, variable=self.provider_var, bg=PANEL, fg=TEXT,
                                selectcolor=BG, activebackground=PANEL, font=(UI, 10, "bold"), anchor="w",
                                command=self._refresh_provider)
            rb.pack(fill="x", padx=8, pady=(6, 0))
            tk.Label(card, text=info["blurb"], bg=PANEL, fg=MUTED, wraplength=220, justify="left", anchor="w",
                     font=(UI, 8)).pack(fill="x", padx=10, pady=(0, 6))
            card.bind("<Button-1>", lambda e, p=pid: (self.provider_var.set(p), self._refresh_provider()))
            self.provider_cards[pid] = card
        self._text(self.body, "API keys are separate from chat subscriptions like ChatGPT Plus or Claude Pro, and "
                   "companies usually charge for API use. KAIRO shows you which models your key can use.", fg=MUTED)
        self.provider_box = tk.Frame(self.body, bg=BG)
        self.provider_box.pack(fill="x", pady=(6, 0))
        self.online_next = self._nav(back=lambda: self.show("engine"), nxt=self._online_next)
        self._refresh_provider()

    def _refresh_provider(self):
        new = self.provider_var.get()
        if new != self.provider:
            self.provider, self.models, self.model, self.key_checked_for, self.api_key = new, [], "", None, ""
        for pid, card in self.provider_cards.items():
            card.configure(highlightbackground=CYAN if pid == self.provider else EDGE,
                           highlightthickness=2 if pid == self.provider else 1)
        for child in self.provider_box.winfo_children():
            child.destroy()
        info = providers.PROVIDERS[self.provider]
        self.plan_var = tk.StringVar(value=self.claude_mode)
        if self.provider == "anthropic" and PLAN_OPTION:
            modes = tk.Frame(self.provider_box, bg=BG)
            modes.pack(fill="x")
            self._radio(modes, "I have an API key from the Anthropic Console", self.plan_var, "api",
                        command=self._refresh_provider)
            self._radio(modes, "Use my Claude Pro/Max plan through Claude Code instead (personal use)", self.plan_var,
                        "plan", "No key needed. Uses your plan's usage limits. Needs Claude Code installed and signed "
                        "in on this computer. Anthropic doesn't allow sharing a plan sign-in with other people's apps.",
                        command=self._refresh_provider)
            self.claude_mode = self.plan_var.get()
            if self.claude_mode == "plan":
                found = self.report.claude_code_found if self.report else False
                box = self._card(self.provider_box)
                tk.Label(box, text="✔ Claude Code is installed." if found else "⚠ Claude Code isn't installed yet.",
                         bg=PANEL, fg=GREEN if found else GOLD, font=(UI, 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(8, 2))
                row = tk.Frame(box, bg=PANEL)
                row.pack(fill="x", padx=12, pady=8)
                self._button(row, "How to install Claude Code", lambda: webbrowser.open(CLAUDE_CODE_PAGE), side="left")
                return

        box = self._card(self.provider_box)
        heading = "How to connect another service" if self.provider == "custom" else f"How to get a {info['label']} key"
        tk.Label(box, text=heading, bg=PANEL, fg=CYAN, font=(UI, 11, "bold"),
                 anchor="w").pack(fill="x", padx=12, pady=(8, 2))
        if self.provider == "custom":
            how = ("1. Find the service's API address in its documentation. It usually ends in /v1, for example "
                   "https://api.example.com/v1\n2. Create an API key on the service's website.\n"
                   "3. Paste both below and press Check key.")
        else:
            prefix = f" It starts with '{info['key_prefix']}'." if info["key_prefix"] else ""
            how = (f"1. Press the button below. Your browser opens the official {info['site']} page.\n"
                   "2. Sign in, or create an account.\n"
                   "3. Create a new key (any name, like KAIRO) and copy it. Most sites show a key only once.\n"
                   f"4. Come back here, paste it below, and press Check key.{prefix}")
        tk.Label(box, text=how, bg=PANEL, fg=TEXT, justify="left", anchor="w", wraplength=700).pack(fill="x", padx=12)
        if info["key_url"]:
            row = tk.Frame(box, bg=PANEL)
            row.pack(fill="x", padx=12, pady=8)
            self._button(row, f"Open {info['site']}", lambda: webbrowser.open(info["key_url"]), side="left")
        else:
            tk.Label(box, text="", bg=PANEL).pack()

        form = tk.Frame(self.provider_box, bg=BG)
        form.pack(fill="x", pady=(6, 0))
        self.url_entry = None
        if self.provider == "custom":
            tk.Label(form, text="Service address (base URL)", bg=BG, fg=TEXT, anchor="w").pack(fill="x")
            self.url_entry = tk.Entry(form, bg=PANEL, fg=TEXT, insertbackground=CYAN, relief="flat", highlightthickness=1,
                                      highlightbackground=EDGE, highlightcolor=CYAN, font=(MONO, 10))
            self.url_entry.pack(fill="x", ipady=5, pady=(2, 6))
            self.url_entry.insert(0, self.base_url)
        tk.Label(form, text="Paste your key here", bg=BG, fg=TEXT, anchor="w").pack(fill="x")
        row = tk.Frame(form, bg=BG)
        row.pack(fill="x", pady=(2, 0))
        self.key_entry = tk.Entry(row, show="•", bg=PANEL, fg=TEXT, insertbackground=CYAN, relief="flat",
                                  highlightthickness=1, highlightbackground=EDGE, highlightcolor=CYAN, font=(MONO, 11))
        self.key_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.key_entry.insert(0, self.api_key)
        shown = tk.BooleanVar(value=False)
        tk.Checkbutton(row, text="Show", variable=shown, bg=BG, fg=MUTED, selectcolor=BG, activebackground=BG,
                       command=lambda: self.key_entry.configure(show="" if shown.get() else "•")).pack(side="left", padx=6)
        self.check_key_btn = self._button(row, "Check key", self._check_key, side="left")
        stored = steps.credentials.get(providers.credential_name(self.provider))
        self.key_status = tk.Label(form, text=("A key for this service is already saved. Leave the box empty and press "
                                               "Check key to keep using it." if stored else
                                               "Your key goes into this computer's secure password storage, never into "
                                               "a file, and is only sent to " + (info["label"] if self.provider != "custom" else "that service") + "."),
                                   bg=BG, fg=MUTED, anchor="w", wraplength=720, justify="left")
        self.key_status.pack(fill="x", pady=(4, 0))
        self.model_row = tk.Frame(form, bg=BG)
        self.model_row.pack(fill="x", pady=(6, 0))
        self._show_models()
        self.key_entry.focus_set()

    def _show_models(self):
        for child in self.model_row.winfo_children():
            child.destroy()
        if not self.models:
            return
        tk.Label(self.model_row, text="Model to use (the suggested one is a good start)", bg=BG, fg=TEXT,
                 anchor="w").pack(fill="x")
        self.model_var = tk.StringVar(value=self.model or providers.suggest_model(self.provider, self.models))
        ttk.Combobox(self.model_row, textvariable=self.model_var, values=self.models, width=60).pack(anchor="w", pady=2)
        tk.Label(self.model_row, text="Choose a chat model. To control your computer, the model must support "
                 "\"tools\" (most current chat models do). If one doesn't, KAIRO can still talk but not act.",
                 bg=BG, fg=MUTED, anchor="w", wraplength=720, justify="left").pack(fill="x")

    def _key_inputs(self) -> tuple[str, str]:
        key = self.key_entry.get().strip() or steps.credentials.get(providers.credential_name(self.provider)) or ""
        url = (self.url_entry.get().strip() if self.url_entry else "") or providers.PROVIDERS[self.provider].get("base_url", "")
        return key, url

    def _check_key(self):
        key, url = self._key_inputs()
        if not key:
            self.key_status.configure(text="Paste your key first.", fg=GOLD)
            return
        if self.provider == "custom" and not url.startswith(("http://", "https://")):
            self.key_status.configure(text="The service address should start with https://", fg=GOLD)
            return
        self._enable(self.check_key_btn, False, primary=False)
        self.key_status.configure(text="Checking your key... (this is free)", fg=CYAN)
        provider = self.provider

        def run():
            try:
                models = steps.check_key(provider, key, url)
                self.events.put(("key_ok", provider, key, url, models))
            except StepError as exc:
                self.events.put(("key_bad", provider, str(exc)))

        threading.Thread(target=run, daemon=True).start()

    def _online_next(self):
        if self.provider == "anthropic" and self.plan_var.get() == "plan":
            self.claude_mode = "plan"
            if not (self.report and self.report.claude_code_found) and not messagebox.askyesno(
                    "Claude Code not found", "Claude Code isn't installed on this computer yet, so KAIRO won't be "
                    "able to think until it is. Continue anyway?", parent=self):
                return
            self.show("voice")
            return
        self.claude_mode = "api"
        key, url = self._key_inputs()
        if self.key_checked_for != self.provider or not self.models:
            messagebox.showinfo("Check your key first", "Press 'Check key' so KAIRO can make sure the key works "
                                "and see which models you can use.", parent=self)
            return
        self.model = self.model_var.get().strip()
        if not self.model:
            messagebox.showinfo("Choose a model", "Pick a model from the list.", parent=self)
            return
        self.api_key, self.base_url = key, (url if self.provider == "custom" else "")
        self.show("voice")

    def _screen_ollama(self):
        self._title("Choose a local AI model", "These run on your computer. They're free, private and work offline.")
        self.ollama_box = tk.Frame(self.body, bg=BG)
        self.ollama_box.pack(fill="both", expand=True)
        self.ollama_next = self._nav(back=lambda: self.show("engine"), nxt=self._ollama_next, next_enabled=False)
        self._refresh_ollama()

    def _refresh_ollama(self):
        for child in self.ollama_box.winfo_children():
            child.destroy()
        status = steps.ollama_status()
        installed = status["running"] or checks.ollama_path() is not None
        if not installed:
            box = self._card(self.ollama_box)
            tk.Label(box, text="First, install Ollama (free)", bg=PANEL, fg=CYAN, font=(UI, 12, "bold"),
                     anchor="w").pack(fill="x", padx=12, pady=(10, 2))
            tk.Label(box, text="Ollama is the free program that runs AI models on your computer.\n"
                               "1. Press 'Get Ollama'. Your browser opens the official Ollama website.\n"
                               "2. Click Download, then open the file you downloaded and follow its steps.\n"
                               "3. Come back here and press 'Check again'.",
                     bg=PANEL, fg=TEXT, justify="left", anchor="w", wraplength=700).pack(fill="x", padx=12)
            row = tk.Frame(box, bg=PANEL)
            row.pack(fill="x", padx=12, pady=10)
            self._button(row, "Get Ollama", lambda: webbrowser.open(OLLAMA_DOWNLOAD), primary=True, side="left")
            self._button(row, "Check again", self._refresh_ollama, side="left")
            self._enable(self.ollama_next, False)
            return
        if not status["running"]:
            row = tk.Frame(self.ollama_box, bg=BG)
            row.pack(fill="x", pady=(0, 6))
            tk.Label(row, text="⚠ Ollama is installed but not running.", bg=BG, fg=GOLD).pack(side="left")
            self._button(row, "Start Ollama", lambda: (steps.start_ollama(), self._refresh_ollama()), side="left")
        ram = self.report.ram_gb if self.report else 8
        self.model_var = tk.StringVar(value=self.ollama_model)
        catalog = list(steps.OLLAMA_CATALOG)
        known = {m["name"] for m in catalog}
        for name in status["models"]:  # tool-capable models the user already has
            base = name.removesuffix(":latest")
            if base not in known and "embed" not in base and ":cloud" not in base and \
                    "tools" in steps.model_capabilities(name):
                catalog.append({"name": base, "label": base, "size_gb": 0, "about": "Already on this computer."})
        list_box = tk.Frame(self.ollama_box, bg=BG)
        list_box.pack(fill="x")
        for m in catalog[:6]:
            have = steps.has_model(m["name"], status["models"])
            need = checks.ram_needed_gb(m["size_gb"]) if m["size_gb"] else None
            if need is None or ram >= need:
                fit, color = "✔ Fits this computer", GREEN
            elif ram >= m["size_gb"] + 2:
                fit, color = "⚠ May be slow here", GOLD
            else:
                fit, color = "✖ Too big for this computer", RED
            card = self._card(list_box)
            top = tk.Frame(card, bg=PANEL)
            top.pack(fill="x", padx=10, pady=(6, 0))
            tk.Radiobutton(top, text=m["label"], variable=self.model_var, value=m["name"], bg=PANEL, fg=TEXT,
                           selectcolor=BG, activebackground=PANEL, font=(UI, 11, "bold")).pack(side="left")
            tk.Label(top, text=fit, bg=PANEL, fg=color).pack(side="right")
            size = "Already downloaded" if have else f"Download: about {m['size_gb']} GB"
            facts = f"{size}  ·  Memory needed: about {need} GB  ·  Can control your computer: yes" if need else size
            tk.Label(card, text=m["about"] + "\n" + facts, bg=PANEL, fg=MUTED, justify="left", anchor="w",
                     wraplength=700).pack(fill="x", padx=36, pady=(0, 6))
        self.embed_var = tk.BooleanVar(value=self.want_embeddings)
        have_embed = steps.has_model(steps.EMBEDDING_MODEL["name"], status["models"])
        self._check(self.ollama_box, "Also get the memory-search helper" + (" (already downloaded)" if have_embed else
                    f" (about {steps.EMBEDDING_MODEL['size_gb']} GB)"), self.embed_var, steps.EMBEDDING_MODEL["about"])
        self._enable(self.ollama_next, True)

    def _ollama_next(self):
        self.ollama_model = self.model_var.get()
        self.want_embeddings = self.embed_var.get()
        status = steps.ollama_status()
        downloads = []
        for name, wanted in ((self.ollama_model, True), (steps.EMBEDDING_MODEL["name"], self.want_embeddings)):
            if wanted and not steps.has_model(name, status["models"]):
                size = next((m["size_gb"] for m in steps.OLLAMA_CATALOG if m["name"] == name),
                            steps.EMBEDDING_MODEL["size_gb"] if name == steps.EMBEDDING_MODEL["name"] else 0)
                downloads.append(f"{name} (about {size} GB)")
        if downloads and not messagebox.askyesno(
                "Download models?", "On the last step, KAIRO will download:\n\n  " + "\n  ".join(downloads) +
                "\n\nThis can take a while on slow internet. Continue?", parent=self):
            return
        self.show("voice")

    # ------------------------------------------------------------------ 5. voice
    def screen_voice(self):
        self._title("Your voice and KAIRO's voice", "Pick a microphone and test it, then choose how KAIRO sounds.")
        mics = self.report.microphones if self.report else checks.input_microphones()
        mic_card = self._card(self.body)
        tk.Label(mic_card, text="1. Microphone", bg=PANEL, fg=CYAN, font=(UI, 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(8, 2))
        row = tk.Frame(mic_card, bg=PANEL)
        row.pack(fill="x", padx=12, pady=4)
        choices = ["Computer's default microphone"] + mics
        self.mic_var = tk.StringVar(value=self.mic_name if self.mic_name in mics else choices[0])
        ttk.Combobox(row, textvariable=self.mic_var, values=choices, state="readonly", width=46).pack(side="left")
        self.mic_test_btn = self._button(row, "Test microphone", self._test_mic, side="left")
        self.meter = ttk.Progressbar(mic_card, style="J.Horizontal.TProgressbar", maximum=100, length=400)
        self.meter.pack(fill="x", padx=12, pady=(4, 2))
        self.mic_result = tk.Label(mic_card, text="Press Test, then say something like \"Hello KAIRO\". "
                                   "Nothing is recorded or saved.", bg=PANEL, fg=MUTED, anchor="w", wraplength=700,
                                   justify="left")
        self.mic_result.pack(fill="x", padx=12, pady=(0, 8))
        if not mics:
            self.mic_result.configure(text="No microphone found. You can still type to KAIRO (choose 'Type only' next).",
                                      fg=GOLD)
            self._enable(self.mic_test_btn, False, primary=False)

        voice_card = self._card(self.body)
        tk.Label(voice_card, text="2. KAIRO's voice", bg=PANEL, fg=CYAN, font=(UI, 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(8, 2))
        row = tk.Frame(voice_card, bg=PANEL)
        row.pack(fill="x", padx=12, pady=(4, 10))
        labels = {v: label for v, label in steps.VOICES}
        self.voice_var = tk.StringVar(value=labels.get(self.voice, steps.VOICES[0][1]))
        ttk.Combobox(row, textvariable=self.voice_var, values=[label for _, label in steps.VOICES], state="readonly",
                     width=46).pack(side="left")
        self.sample_btn = self._button(row, "Play sample", self._play_sample, side="left")
        tk.Label(voice_card, text="Turn your speakers up a little. The sample needs the internet; without it KAIRO "
                 "uses your computer's built-in voice.", bg=PANEL, fg=MUTED, anchor="w", wraplength=700,
                 justify="left").pack(fill="x", padx=12, pady=(0, 8))

        mode_card = self._card(self.body)
        tk.Label(mode_card, text="3. How do you want to talk to KAIRO?", bg=PANEL, fg=CYAN, font=(UI, 11, "bold"),
                 anchor="w").pack(fill="x", padx=12, pady=(8, 2))
        self.mode_var = tk.StringVar(value=self.listen_mode if mics else "text")
        modes = tk.Frame(mode_card, bg=PANEL)
        modes.pack(fill="x", padx=12, pady=(0, 8))
        for key, title, sub in LISTEN_MODES:
            self._radio(modes, title, self.mode_var, key, sub, enabled=bool(mics) or key == "text")
        self._text(self.body, "Privacy: audio is never saved. Speech is turned into text by Google's free online "
                   "service. A small panel always shows when the microphone is on, and its MUTE button turns it fully off.")
        self._nav(back=lambda: self.show("brain"), nxt=self._voice_next)

    def _selected_mic(self) -> str:
        v = self.mic_var.get()
        return "" if v.startswith("Computer's default") else v

    def _test_mic(self):
        self._enable(self.mic_test_btn, False, primary=False)
        self.mic_result.configure(text="Listening for 5 seconds... say \"Hello KAIRO\".", fg=CYAN)

        def run():
            try:
                peak = steps.mic_level_meter(self._selected_mic(), 5, lambda lvl: self.events.put(("meter", lvl)))
                self.events.put(("mic_done", peak, ""))
            except StepError as exc:
                self.events.put(("mic_done", -1, str(exc)))

        threading.Thread(target=run, daemon=True).start()

    def _play_sample(self):
        voice = next(v for v, label in steps.VOICES if label == self.voice_var.get())
        self._enable(self.sample_btn, False, primary=False)

        def run():
            try:
                steps.speak_sample(voice)
            finally:
                self.events.put(("sample_done",))

        threading.Thread(target=run, daemon=True).start()

    def _voice_next(self):
        self.mic_name = self._selected_mic()
        self.voice = next(v for v, label in steps.VOICES if label == self.voice_var.get())
        self.listen_mode = self.mode_var.get()
        self.show("extras")

    # ------------------------------------------------------------------ 6. extras
    def screen_extras(self):
        self._title("A few last choices")
        self.login_var = tk.BooleanVar(value=self.start_at_login)
        self.panel_var = tk.BooleanVar(value=self.show_panel)
        box = self._card(self.body)
        inner = tk.Frame(box, bg=PANEL)
        inner.pack(fill="x", padx=12, pady=8)
        self._check(inner, "Start KAIRO when I log in", self.login_var,
                    "KAIRO starts quietly in the background, so it's ready when you need it.")
        self._check(inner, "Show the KAIRO status panel", self.panel_var,
                    "A small box in the corner that shows when KAIRO is listening, with Mute and Stop buttons. "
                    "Recommended.")
        feats = self._card(self.body)
        tk.Label(feats, text="What KAIRO can do in this version", bg=PANEL, fg=CYAN, font=(UI, 11, "bold"),
                 anchor="w").pack(fill="x", padx=12, pady=(8, 2))
        included = [
            ("Computer control", "Opens apps and websites, plays music, changes the volume."),
            ("Reminders & notes", "Reminds you at the right time and keeps quick notes."),
            ("Homework & tasks", "Tracks assignments, tests and deadlines."),
            ("Memory", "Remembers what you ask it to, and forgets when you say so."),
            ("System status", "Battery, memory and disk space."),
        ]
        later = "Coming later: calendar, phone connection, browser control, smart home and developer tools."
        for name, text in included:
            line = tk.Frame(feats, bg=PANEL)
            line.pack(fill="x", padx=12)
            tk.Label(line, text="✔", fg=GREEN, bg=PANEL, width=2).pack(side="left")
            tk.Label(line, text=f"{name}: ", fg=TEXT, bg=PANEL, font=(UI, 10, "bold")).pack(side="left")
            tk.Label(line, text=text, fg=MUTED, bg=PANEL, anchor="w").pack(side="left", fill="x")
        tk.Label(feats, text=later, bg=PANEL, fg=MUTED, anchor="w", wraplength=700, justify="left").pack(fill="x", padx=12, pady=(4, 8))
        self._nav(back=lambda: self.show("voice"), nxt=self._extras_next, next_text="Set up KAIRO")

    def _extras_next(self):
        self.start_at_login = self.login_var.get()
        self.show_panel = self.panel_var.get()
        self.done_steps.clear()
        self.show("install")

    # ------------------------------------------------------------------ 7. install
    def _plan(self) -> list[tuple[str, str, bool]]:
        """(key, label, optional)"""
        plan = []
        if self.engine == "online" and self.claude_mode == "api" and self.api_key:
            label = providers.PROVIDERS[self.provider]["label"]
            plan += [("test_key", f"Checking your key with {label}", False), ("store_key", "Saving your key securely", False)]
        if self.engine == "ollama":
            plan.append(("ollama_model", f"Getting the AI model ({self.ollama_model})", False))
            if self.want_embeddings:
                plan.append(("ollama_embed", "Getting the memory-search helper", True))
            plan.append(("ollama_test", "Testing the AI model", False))
        plan += [("settings", "Saving your choices", False), ("login", "Setting up start at login", True),
                 ("verify", "Final check", False)]
        return plan

    def _settings_changes(self) -> dict:
        if self.engine == "ollama":
            backend = "ollama"
        elif self.provider == "anthropic":
            backend = "api" if self.claude_mode == "api" else "pro"
        else:
            backend = "online"
        changes = {"backend": backend, "listen_mode": self.listen_mode, "microphone_name": self.mic_name,
                   "voice": {"neural_voice": self.voice}, "hud": self.show_panel, "start_at_login": self.start_at_login,
                   "setup_complete": True}
        if self.engine == "ollama":
            changes["ollama_model"] = self.ollama_model
        elif backend == "api" and self.model:
            changes["claude_model_api"] = self.model
        elif backend == "online":
            changes["online"] = {"provider": self.provider, "model": self.model, "base_url": self.base_url}
        return changes

    def _step_function(self, key: str):
        log = lambda text: self.events.put(("log", text))  # noqa: E731
        progress = lambda status, done, total: self.events.put(("progress", status, done, total))  # noqa: E731
        return {
            "test_key": lambda: steps.check_key(self.provider, self.api_key, self.base_url, log),
            "store_key": lambda: steps.store_key(self.provider, self.api_key, log),
            "ollama_model": lambda: steps.pull_model(self.ollama_model, progress, self.cancel_flag.is_set, log),
            "ollama_embed": lambda: steps.pull_model(steps.EMBEDDING_MODEL["name"], progress, self.cancel_flag.is_set, log),
            "ollama_test": lambda: steps.test_model(self.ollama_model, log),
            "settings": lambda: steps.save_settings(self._settings_changes(), log),
            "login": lambda: steps.set_start_at_login(self.start_at_login, log),
            "verify": lambda: self._verify(log),
        }[key]

    def _verify(self, log):
        import importlib

        for mod in ("brains", "voice", "tools", "conversation", "memory", "tasks", "hud", "speech_recognition",
                    "edge_tts", "anthropic", "pyaudio"):
            importlib.import_module(mod)
        s = steps.settings_mod.load()
        if not s.get("setup_complete"):
            raise StepError("Your choices weren't saved. Press Retry.")
        log("Everything KAIRO needs is in place.")

    def screen_install(self):
        self._title("Setting up KAIRO", "Each step does real work. If one has a problem, you'll see why and can try again.")
        self.step_rows: dict[str, tk.Label] = {}
        for key, label, optional in self._plan():
            row = tk.Frame(self.body, bg=BG)
            row.pack(fill="x", pady=1)
            mark = tk.Label(row, text="✔" if key in self.done_steps else "○", fg=GREEN if key in self.done_steps else MUTED,
                            bg=BG, width=2, font=(UI, 11))
            mark.pack(side="left")
            tk.Label(row, text=label + ("  (optional)" if optional else ""), fg=TEXT, bg=BG, anchor="w").pack(side="left")
            self.step_rows[key] = mark
        self.progress = ttk.Progressbar(self.body, style="J.Horizontal.TProgressbar", maximum=100)
        self.progress_label = tk.Label(self.body, text="", bg=BG, fg=MUTED, anchor="w")
        self.log_box = tk.Text(self.body, height=7, bg=PANEL, fg=MUTED, relief="flat", font=self.mono_font, wrap="word",
                               highlightthickness=1, highlightbackground=EDGE)
        self.log_box.pack(fill="both", expand=True, pady=(10, 0))
        self.log_box.configure(state="disabled")
        self.status = tk.Label(self.body, text="", bg=BG, fg=CYAN, anchor="w", wraplength=740, justify="left")
        self.status.pack(fill="x", pady=(6, 0))
        self.cancel_btn = self._button(self.footer, "Cancel", self.confirm_cancel, side="left")
        self.back_btn = self._button(self.footer, "Back", lambda: self.show("extras"), side="left", enabled=False)
        self.next_btn = self._button(self.footer, "Next", lambda: self.show("done"), primary=True, enabled=False)
        self.retry_btn = self._button(self.footer, "Retry", self.start_install, primary=False, enabled=False)
        self.skip_btn = self._button(self.footer, "Skip this step", self._skip, primary=False, enabled=False)
        self.failed_step: str | None = None
        self.start_install()

    def start_install(self):
        if self.worker is not None and self.worker.is_alive():
            return
        for b in (self.retry_btn, self.skip_btn, self.next_btn, self.back_btn):
            self._enable(b, False, primary=b is self.next_btn)
        self.status.configure(text="Working on it. Please keep this window open.", fg=CYAN)
        self.cancel_flag.clear()
        pending = [(k, optional) for k, _, optional in self._plan() if k not in self.done_steps]
        self.worker = threading.Thread(target=self._run_steps, args=(pending,), daemon=True)
        self.worker.start()

    def _skip(self):
        if self.failed_step:
            self.done_steps.add(self.failed_step)
            self.events.put(("step", self.failed_step, "skipped", ""))
            self.start_install()

    def _run_steps(self, pending):
        for key, optional in pending:
            if self.cancel_flag.is_set():
                return
            self.events.put(("step", key, "running", ""))
            try:
                self._step_function(key)()
            except StepError as exc:
                self.events.put(("step", key, "failed", str(exc), optional))
                return
            except Exception as exc:  # never crash the wizard
                self.events.put(("step", key, "failed", f"Something unexpected happened ({type(exc).__name__}: {exc}). "
                                 "Press Retry. If it keeps happening, copy the text in the box above and ask for help.",
                                 optional))
                return
            self.events.put(("step", key, "done", ""))
        self.events.put(("finished",))

    def _append_log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ 8. done
    def screen_done(self):
        self.finished_ok = True
        self._title("KAIRO is ready!", "Hello! I'm KAIRO, your personal AI assistant. I'm ready to help.")
        card = self._card(self.body)
        tk.Label(card, text="Try saying", bg=PANEL, fg=CYAN, font=(UI, 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(8, 2))
        if self.listen_mode == "text":
            tips = ["Click TYPE on the KAIRO panel, then type: open the calculator",
                    "What's the weather in London?", "Remind me to stretch in 20 minutes"]
        else:
            tips = ['"Kairo, open the calculator."', '"Kairo, what\'s the weather in London?"  then  "And tomorrow?"',
                    '"Kairo, remind me to stretch in 20 minutes."', '"Kairo, tell me something interesting."']
        for t in tips:
            tk.Label(card, text="•  " + t, bg=PANEL, fg=TEXT, anchor="w").pack(fill="x", padx=12)
        tk.Label(card, text="", bg=PANEL).pack()
        self._text(self.body, "Look for the KAIRO panel in the bottom-right corner of your screen. Right-click it any "
                   "time to change settings or quit. To stop KAIRO talking, say \"stop\" or press STOP.")
        if self.engine == "ollama":
            self._text(self.body, "Local models need a minute to warm up, so the first answer is slow. After that "
                       "they're quicker.", fg=GOLD)
        self._nav(nxt=self._start_kairo, next_text="Start KAIRO")
        self._button(self.footer, "Close", self._close_without_start, side="left")

    def _close_without_start(self):
        self.restart_kairo_on_close = False
        self.destroy()

    def _start_kairo(self):
        steps.launch_kairo(["--restarted"])
        self.restart_kairo_on_close = False
        self.destroy()

    # ------------------------------------------------------------------ events from worker threads
    def _poll_events(self):
        try:
            while True:
                self._handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        except tk.TclError:
            pass  # the screen changed while an event was being shown
        self.after(80, self._poll_events)

    def _handle_event(self, ev):
        kind = ev[0]
        if kind == "check" and self.current == "check":
            self._show_check_results(ev[1])
        elif kind == "meter" and self.current == "voice":
            self.meter["value"] = ev[1] * 100
        elif kind == "mic_done" and self.current == "voice":
            peak, err = ev[1], ev[2]
            self.meter["value"] = 0
            self._enable(self.mic_test_btn, True, primary=False)
            if err:
                self.mic_result.configure(text=err, fg=RED)
            elif peak > 0.15:
                self.mic_result.configure(text="✔ KAIRO can hear you clearly.", fg=GREEN)
            elif peak > 0.04:
                self.mic_result.configure(text="⚠ KAIRO can hear you, but quietly. Move closer or turn the microphone "
                                          "volume up in your sound settings.", fg=GOLD)
            else:
                self.mic_result.configure(text="✖ KAIRO didn't hear anything. Check that the right microphone is "
                                          "selected and isn't muted, then test again.", fg=RED)
        elif kind == "sample_done" and self.current == "voice":
            self._enable(self.sample_btn, True, primary=False)
        elif kind in ("key_ok", "key_bad") and self.current == "brain" and ev[1] == self.provider:
            self._enable(self.check_key_btn, True, primary=False)
            if kind == "key_bad":
                self.key_status.configure(text="✖ " + ev[2], fg=RED)
                return
            _, _, key, url, models = ev
            self.key_checked_for, self.api_key, self.models = self.provider, key, models
            self.base_url = url if self.provider == "custom" else ""
            self.key_status.configure(text=f"✔ The key works. It can use {len(models)} models.", fg=GREEN)
            self._show_models()
        elif self.current != "install":
            return
        elif kind == "log":
            self._append_log(ev[1])
        elif kind == "progress":
            _, status, done, total = ev
            if total:
                if not self.progress.winfo_ismapped():
                    self.progress.pack(fill="x", pady=(8, 0), before=self.log_box)
                    self.progress_label.pack(fill="x", before=self.log_box)
                self.progress["value"] = done * 100 / total
                self.progress_label.configure(text=f"{done / 1e9:.2f} GB of {total / 1e9:.2f} GB downloaded")
        elif kind == "step":
            key, state, msg = ev[1], ev[2], ev[3]
            mark = self.step_rows.get(key)
            if state in ("done", "skipped"):
                self.done_steps.add(key)
                self.progress.pack_forget()
                self.progress_label.pack_forget()
            if mark is not None:
                icon, color = {"running": ("◔", CYAN), "done": ("✔", GREEN), "failed": ("✖", RED),
                               "skipped": ("–", MUTED)}[state]
                mark.configure(text=icon, fg=color)
            if state == "failed":
                self.failed_step = key
                self.status.configure(text=msg, fg=RED)
                self._append_log("Problem: " + msg)
                self._enable(self.retry_btn, True, primary=False)
                self._enable(self.back_btn, True, primary=False)
                if len(ev) > 4 and ev[4]:
                    self._enable(self.skip_btn, True, primary=False)
        elif kind == "finished":
            self.status.configure(text="Everything is set up and checked.", fg=GREEN)
            self._enable(self.next_btn, True)
            self.next_btn.focus_set()
            self.bind("<Return>", lambda e: self.show("done"))


def selftest() -> int:
    """Build every screen once without downloading or saving anything (used by tests and the build)."""
    app = Wizard()
    app.withdraw()
    app.report = checks.check_system(paths.DATA_DIR, with_gpu=False, with_network=False)
    for name in Wizard.SCREENS:
        if name == "install":
            app.start_install = lambda: None  # don't run real steps
        for engine in (("online", "ollama") if name == "brain" else ("online",)):
            app.engine = engine
            app.show(name)
            app.update()
    app.destroy()
    print("setup wizard selftest ok")
    return 0


def run(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    Wizard(restart_kairo_on_close="--restart-kairo" in argv).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
