"""Everything JARVIS can actually *do* on this PC.

Each function decorated with @beta_tool becomes a tool Claude can call.
The docstring is what Claude reads to decide when to use it, so keep them clear.
To add a new ability: write a function here, decorate it, and add it to ALL_TOOLS.
"""

import ctypes
import datetime as dt
import difflib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

import psutil
from anthropic import beta_tool

import memory as memory_mod
import tasks as tasks_mod
from settings import DATA_DIR

HERE = Path(__file__).parent
NOTES_FILE = DATA_DIR / "notes.txt"
REMINDERS_FILE = DATA_DIR / "reminders.json"
IS_WINDOWS = sys.platform == "win32"

# main.py sets this so reminders can speak out loud when they fire.
announce = print

# Set up by init() - long-term memory and the task list.
memory_store: memory_mod.MemoryStore | None = None
task_store: tasks_mod.TaskStore | None = None


def init(settings: dict):
    """Open the data files. Older versions kept notes/reminders next to the code - move them into data/."""
    global memory_store, task_store
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for old in (HERE / "notes.txt", HERE / "reminders.json"):
        new = DATA_DIR / old.name
        if old.exists() and not new.exists():
            old.replace(new)
    embedder = memory_mod.Embedder(settings["ollama_url"], settings["embedding_model"])
    memory_store = memory_mod.MemoryStore(DATA_DIR / "memory.json", embedder)
    task_store = tasks_mod.TaskStore(DATA_DIR / "tasks.json")


def _get_json(url: str, timeout: float = 10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------- time & weather

@beta_tool
def get_current_time() -> str:
    """Get the current local date and time on this computer."""
    return dt.datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")


@beta_tool
def get_weather(location: str) -> str:
    """Get the current weather and today's forecast for a place.

    Args:
        location: City name, e.g. "London" or "Austin, Texas".
    """
    city = location.split(",")[0].strip()
    geo = _get_json(
        "https://geocoding-api.open-meteo.com/v1/search?count=5&name=" + urllib.parse.quote(city)
    )
    results = geo.get("results") or []
    if not results:
        return f"Could not find a place called {location}."
    # Prefer a result whose region/country matches the rest of what was asked.
    rest = location.lower()
    place = next(
        (r for r in results if any(str(r.get(k, "")).lower() in rest for k in ("admin1", "country") if r.get(k))),
        results[0],
    )
    lat, lon = place["latitude"], place["longitude"]
    data = _get_json(
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&timezone=auto&forecast_days=1"
    )
    return json.dumps(
        {
            "place": f"{place['name']}, {place.get('admin1', '')}, {place.get('country', '')}",
            "current": data.get("current"),
            "current_units": data.get("current_units"),
            "today": data.get("daily"),
            "note": "weather_code is a WMO code (0 clear, 1-3 cloudy, 45/48 fog, 51-67 rain/drizzle, 71-77 snow, 80-82 showers, 95+ thunderstorm)",
        }
    )


# --------------------------------------------------------------------------- apps & websites

_start_apps_cache: dict[str, str] | None = None


def _start_apps() -> dict[str, str]:
    """Every app in the Start menu (including Store apps) -> its launch ID."""
    global _start_apps_cache
    if _start_apps_cache is None:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=30,
        ).stdout
        apps = json.loads(out) if out.strip() else []
        if isinstance(apps, dict):
            apps = [apps]
        _start_apps_cache = {a["Name"]: a["AppID"] for a in apps}
    return _start_apps_cache


_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "task manager": "taskmgr.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "settings": "ms-settings:",
    "control panel": "control.exe",
}


@beta_tool
def open_application(name: str) -> str:
    """Open/launch an application installed on this Windows PC (e.g. Chrome, Spotify, Word, Notepad, Discord, Steam).

    Args:
        name: The app's name as a person would say it.
    """
    key = name.lower().strip()
    if key in _ALIASES:
        os.startfile(_ALIASES[key])
        return f"Opened {name}."

    apps = _start_apps()
    lowered = {n.lower(): n for n in apps}
    match = None
    # exact, then "starts with", then "contains", then fuzzy
    if key in lowered:
        match = lowered[key]
    else:
        for cand_lower, cand in sorted(lowered.items(), key=lambda kv: len(kv[0])):
            if cand_lower.startswith(key) or key in cand_lower:
                match = cand
                break
        if match is None:
            close = difflib.get_close_matches(key, list(lowered), n=1, cutoff=0.6)
            match = lowered[close[0]] if close else None

    if match:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{apps[match]}"])
        return f"Opened {match}."

    try:
        os.startfile(name)
        return f"Opened {name}."
    except OSError:
        return f"I couldn't find an app called {name} on this PC."


@beta_tool
def close_application(name: str) -> str:
    """Close a running application by name (e.g. "chrome", "spotify", "notepad").

    Args:
        name: The app's name as a person would say it.
    """
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    if len(key) < 3:
        return f"'{name}' is too short to match safely - say the app's full name."
    killed = set()
    for proc in psutil.process_iter(["name"]):
        pname = (proc.info["name"] or "").lower()
        if key and key in re.sub(r"[^a-z0-9]", "", pname.removesuffix(".exe")):
            if pname in ("explorer.exe", "python.exe", "pythonw.exe"):
                continue  # never close the desktop or JARVIS itself
            try:
                proc.terminate()
                killed.add(proc.info["name"])
            except psutil.Error:
                pass
    return f"Closed {', '.join(sorted(killed))}." if killed else f"No running app matched {name}."


@beta_tool
def open_website(url: str) -> str:
    """Open a website in the default web browser.

    Args:
        url: Full URL or domain, e.g. "github.com" or "https://www.bbc.co.uk/news".
    """
    if not re.match(r"^https?://", url):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}."


@beta_tool
def play_on_youtube(query: str) -> str:
    """Play a song or video on YouTube in the browser - finds the top result and opens it.

    Args:
        query: What to play, e.g. "Back in Black AC/DC" or "lofi hip hop".
    """
    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    try:
        req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"})
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
        video_id = re.search(r'"videoId":"([\w-]{11})"', html).group(1)
        webbrowser.open(f"https://www.youtube.com/watch?v={video_id}")
        return f"Playing the top YouTube result for {query}."
    except Exception:
        webbrowser.open(search_url)
        return f"Opened YouTube search results for {query}."


# --------------------------------------------------------------------------- sound & media

def _speakers():
    from pycaw.pycaw import AudioUtilities

    return AudioUtilities.GetSpeakers().EndpointVolume


@beta_tool
def set_volume(level: int) -> str:
    """Set the computer's master volume.

    Args:
        level: Volume from 0 to 100.
    """
    level = max(0, min(100, int(level)))
    vol = _speakers()
    vol.SetMute(0, None)
    vol.SetMasterVolumeLevelScalar(level / 100, None)
    return f"Volume set to {level} percent."


@beta_tool
def get_volume() -> str:
    """Get the current master volume and whether it's muted."""
    vol = _speakers()
    return f"Volume is {round(vol.GetMasterVolumeLevelScalar() * 100)} percent, muted: {bool(vol.GetMute())}."


@beta_tool
def set_mute(muted: bool) -> str:
    """Mute or unmute the computer's sound.

    Args:
        muted: True to mute, False to unmute.
    """
    _speakers().SetMute(1 if muted else 0, None)
    return "Muted." if muted else "Unmuted."


_MEDIA_KEYS = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}


@beta_tool
def media_control(action: str) -> str:
    """Control whatever media is playing (Spotify, YouTube, etc.) like the keyboard media keys.

    Args:
        action: One of "play_pause", "next", "previous", "stop".
    """
    code = _MEDIA_KEYS.get(action)
    if code is None:
        return f"Unknown action {action}. Use one of {list(_MEDIA_KEYS)}."
    ctypes.windll.user32.keybd_event(code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(code, 0, 2, 0)
    return f"Sent {action}."


# --------------------------------------------------------------------------- reminders & notes

_reminders: list[dict] = []
_reminders_lock = threading.Lock()


def _save_reminders():
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REMINDERS_FILE.write_text(json.dumps(_reminders, indent=2))


def _reminder_loop():
    while True:
        now = time.time()
        due = []
        with _reminders_lock:
            for r in list(_reminders):
                if r["due"] <= now:
                    due.append(r)
                    _reminders.remove(r)
            if due:
                _save_reminders()
        for r in due:
            announce(f"Reminder: {r['message']}")
        time.sleep(5)


def start_reminder_service():
    """Loads saved reminders and starts checking them in the background."""
    if REMINDERS_FILE.exists():
        try:
            _reminders.extend(json.loads(REMINDERS_FILE.read_text()))
        except json.JSONDecodeError:
            pass
    threading.Thread(target=_reminder_loop, daemon=True).start()


@beta_tool
def set_reminder(message: str, minutes_from_now: float) -> str:
    """Set a spoken reminder or timer. For a clock time like "at 5pm", call get_current_time first and work out the minutes.

    Args:
        message: What to remind about, e.g. "take the pizza out".
        minutes_from_now: How many minutes from now (can be fractional, e.g. 0.5 for 30 seconds).
    """
    due = time.time() + float(minutes_from_now) * 60
    with _reminders_lock:
        _reminders.append({"message": message, "due": due})
        _save_reminders()
    when = dt.datetime.fromtimestamp(due).strftime("%I:%M %p")
    return f"Reminder set for {when}: {message}."


@beta_tool
def list_reminders() -> str:
    """List the reminders that haven't gone off yet."""
    with _reminders_lock:
        if not _reminders:
            return "No upcoming reminders."
        return "\n".join(
            f"{dt.datetime.fromtimestamp(r['due']).strftime('%a %I:%M %p')}: {r['message']}"
            for r in sorted(_reminders, key=lambda r: r["due"])
        )


@beta_tool
def cancel_reminders(contains: str = "") -> str:
    """Cancel upcoming reminders.

    Args:
        contains: Only cancel reminders whose message contains this text. Leave empty to cancel all.
    """
    with _reminders_lock:
        before = len(_reminders)
        _reminders[:] = [r for r in _reminders if contains and contains.lower() not in r["message"].lower()]
        _save_reminders()
        return f"Cancelled {before - len(_reminders)} reminder(s)."


@beta_tool
def take_note(text: str) -> str:
    """Save a note to the notes file so it can be read back later.

    Args:
        text: The note to save.
    """
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with NOTES_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {text}\n")
    return "Note saved."


@beta_tool
def read_notes(last_n: int = 10) -> str:
    """Read back the most recent saved notes.

    Args:
        last_n: How many of the latest notes to return.
    """
    if not NOTES_FILE.exists():
        return "There are no notes yet."
    lines = NOTES_FILE.read_text(encoding="utf-8").strip().splitlines()
    return "\n".join(lines[-max(1, int(last_n)):]) or "There are no notes yet."


# --------------------------------------------------------------------------- system

@beta_tool
def get_system_status() -> str:
    """Get battery level, CPU and memory usage, and disk space of this PC."""
    info = {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_free_gb": round(psutil.disk_usage(Path.home().anchor or "/").free / 1e9, 1),
    }
    battery = psutil.sensors_battery()
    if battery:
        info["battery_percent"] = round(battery.percent)
        info["plugged_in"] = battery.power_plugged
    else:
        info["battery"] = "no battery (desktop PC)"
    return json.dumps(info)


@beta_tool
def take_screenshot() -> str:
    """Take a screenshot of the screen and save it to the Pictures folder."""
    from PIL import ImageGrab

    folder = Path.home() / "Pictures" / "JARVIS Screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"screenshot_{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.png"
    ImageGrab.grab(all_screens=True).save(path)
    return f"Screenshot saved to {path}."


@beta_tool
def system_power(action: str) -> str:
    """Lock, sleep, shut down or restart the PC. Shut down and restart wait 60 seconds so they can be cancelled.
    Only shut down or restart if the user clearly asked for it.

    Args:
        action: One of "lock", "sleep", "shutdown", "restart", "cancel_shutdown".
    """
    if action == "lock":
        ctypes.windll.user32.LockWorkStation()
        return "Locked."
    if action == "sleep":
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return "Going to sleep."
    if action == "shutdown":
        subprocess.run(["shutdown", "/s", "/t", "60"])
        return "Shutting down in 60 seconds. Say 'cancel shutdown' to stop it."
    if action == "restart":
        subprocess.run(["shutdown", "/r", "/t", "60"])
        return "Restarting in 60 seconds. Say 'cancel shutdown' to stop it."
    if action == "cancel_shutdown":
        subprocess.run(["shutdown", "/a"])
        return "Shutdown cancelled."
    return f"Unknown action {action}."


# --------------------------------------------------------------------------- long-term memory

@beta_tool
def remember(text: str, category: str = "fact") -> str:
    """Save something to long-term memory so it's available in future conversations. Use when the user asks you to
    remember something, states a lasting preference, or shares lasting facts about their projects, school or people.
    Write it as a self-contained statement, e.g. "The user's robotics project uses an Arduino Mega and two servos".

    Args:
        text: The fact to remember, as a complete sentence.
        category: One of "preference", "project", "person", "school", "device", "fact".
    """
    item, is_new = memory_store.add(text, category)
    return f"{'Remembered' if is_new else 'Updated existing memory'} #{item['id']}: {item['text']}"


@beta_tool
def recall(query: str = "", category: str = "") -> str:
    """Search long-term memory. Use whenever earlier knowledge about the user could help (their projects, preferences,
    school, people), and when they ask what you remember. Leave query empty to list the most recent memories.

    Args:
        query: What to look for, e.g. "robotics project" or "music taste".
        category: Optional filter: "preference", "project", "person", "school", "device", "fact".
    """
    found = memory_store.search(query, category=category)
    if not found:
        return "Nothing relevant in memory."
    return "\n".join(f"#{i['id']} ({i['category']}): {i['text']}" for i in found)


@beta_tool
def forget(memory_ids: list[int]) -> str:
    """Permanently delete memories by their # id (use recall first to find the ids). Use when the user says to forget
    something or to stop using some information.

    Args:
        memory_ids: The ids to delete, e.g. [3, 7].
    """
    removed = memory_store.delete([int(i) for i in memory_ids])
    if not removed:
        return "No memories with those ids."
    return "Deleted: " + "; ".join(i["text"] for i in removed)


@beta_tool
def list_all_memories(category: str = "") -> str:
    """List everything stored in long-term memory (for "show me what you have stored").

    Args:
        category: Optional filter: "preference", "project", "person", "school", "device", "fact".
    """
    items = memory_store.all(category)
    if not items:
        return "Memory is empty."
    return f"{len(items)} memories (stored in {memory_store.path}):\n" + "\n".join(
        f"#{i['id']} ({i['category']}): {i['text']}" for i in items
    )


# --------------------------------------------------------------------------- tasks & school

@beta_tool
def add_task(title: str, due: str = "", kind: str = "task", subject: str = "", priority: int = 2, notes: str = "") -> str:
    """Add a task, homework assignment, test, project or study session to the user's task list.
    For relative dates ("Friday", "next week") call get_current_time first and work out the date.

    Args:
        title: What needs doing, e.g. "Chapter 5 worksheet".
        due: Due date as "YYYY-MM-DD" or "YYYY-MM-DD HH:MM" (24h). Empty if none.
        kind: One of "task", "assignment", "test", "project", "study".
        subject: School subject or project name, e.g. "Chemistry" or "Robotics". Optional.
        priority: 1 high, 2 normal, 3 low.
        notes: Optional extra details.
    """
    item = task_store.add(title, due, kind, subject, priority, notes)
    return "Added " + task_store.format([item])


@beta_tool
def list_tasks(subject: str = "", kind: str = "", include_done: bool = False) -> str:
    """List the user's tasks, assignments, tests and deadlines, soonest first, with overdue items flagged.
    Use for "what's due", "what homework do I have", planning the day, etc.

    Args:
        subject: Optional filter by subject/project.
        kind: Optional filter: "task", "assignment", "test", "project", "study".
        include_done: Also show completed items.
    """
    items = task_store.open_items(subject, kind)
    if include_done:
        items += [i for i in task_store.items if i["done"] and (not subject or subject.lower() in i["subject"].lower())]
    if not items:
        return "No tasks." if include_done else "No open tasks."
    return task_store.format(items)


@beta_tool
def complete_task(task_id: int) -> str:
    """Mark a task as done (use list_tasks to find its # id).

    Args:
        task_id: The task's # id.
    """
    item = task_store.set_done(int(task_id))
    return f"Marked done: {item['title']}." if item else f"No task #{task_id}."


@beta_tool
def delete_task(task_id: int) -> str:
    """Permanently delete a task. Only when the user clearly asks to delete or remove it (otherwise use complete_task).

    Args:
        task_id: The task's # id.
    """
    item = task_store.delete(int(task_id))
    return f"Deleted: {item['title']}." if item else f"No task #{task_id}."


ALL_TOOLS = [
    get_current_time,
    get_weather,
    open_application,
    close_application,
    open_website,
    play_on_youtube,
    set_volume,
    get_volume,
    set_mute,
    media_control,
    set_reminder,
    list_reminders,
    cancel_reminders,
    take_note,
    read_notes,
    get_system_status,
    take_screenshot,
    system_power,
    remember,
    recall,
    forget,
    list_all_memories,
    add_task,
    list_tasks,
    complete_task,
    delete_task,
]
