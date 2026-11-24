"""JARVIS health check - the first step of the self-maintenance cycle.

    .venv\\Scripts\\python.exe health_check.py            check and print a report
    .venv\\Scripts\\python.exe health_check.py --notify   also show a desktop notification if something is wrong

Checks: code compiles, unit tests pass, dependencies are consistent, data files are readable, JARVIS is
alive (data/status.json heartbeat), new errors in jarvis.log since the last check, and the AI backends are reachable.
It only reads and reports - it never changes code or data. Reports go to data/health/.
Exit code: 0 all good, 1 warnings, 2 errors.
"""

import argparse
import datetime as dt
import json
import py_compile
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import settings as settings_mod  # noqa: E402

DATA = settings_mod.DATA_DIR
HEALTH_DIR = DATA / "health"
STATE_FILE = HEALTH_DIR / "state.json"
LEVELS = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}


class Report:
    def __init__(self):
        self.items: list[tuple[str, str, str]] = []

    def add(self, level: str, check: str, message: str):
        self.items.append((level, check, message))

    @property
    def worst(self) -> str:
        return max((i[0] for i in self.items), key=LEVELS.get, default="INFO")

    def markdown(self) -> str:
        lines = [f"# JARVIS health report - {dt.datetime.now():%Y-%m-%d %H:%M}", "", f"Overall: **{self.worst}**", ""]
        for level, check, msg in sorted(self.items, key=lambda i: -LEVELS[i[0]]):
            lines.append(f"- **{level}** `{check}`: {msg}")
        return "\n".join(lines) + "\n"


def check_compile(r: Report):
    bad = []
    for f in sorted(HERE.glob("*.py")) + sorted((HERE / "tests").glob("*.py")):
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as exc:
            bad.append(f"{f.name}: {exc.msg.strip().splitlines()[-1]}")
    r.add("CRITICAL" if bad else "INFO", "compile", "; ".join(bad) if bad else "all Python files compile")


def check_tests(r: Report):
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                          cwd=HERE, capture_output=True, text=True, timeout=600)
    summary = (re.findall(r"Ran \d+ tests? in [\d.]+s", proc.stderr) or ["?"])[-1]
    if proc.returncode == 0:
        r.add("INFO", "tests", f"passed ({summary})")
    else:
        failures = re.findall(r"^(?:FAIL|ERROR): (.+)$", proc.stderr, re.M)
        r.add("ERROR", "tests", f"failed ({summary}): " + "; ".join(failures[:8]))


def check_dependencies(r: Report):
    proc = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True, timeout=120)
    if proc.returncode == 0:
        r.add("INFO", "dependencies", "installed packages are consistent")
    else:
        r.add("WARNING", "dependencies", proc.stdout.strip().replace("\n", "; ")[:500])


def check_data_files(r: Report):
    bad = []
    for name in ("settings.json", "memory.json", "tasks.json", "reminders.json"):
        f = DATA / name
        if f.exists():
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except ValueError as exc:
                bad.append(f"{name}: {exc}")
    corrupt = [p.name for p in DATA.glob("*.corrupt.json")]
    if bad:
        r.add("ERROR", "data", "unreadable: " + "; ".join(bad))
    if corrupt:
        r.add("WARNING", "data", f"recovered copies of damaged files exist (check them, then delete): {', '.join(corrupt)}")
    if not bad and not corrupt:
        r.add("INFO", "data", "data files are readable")


def check_heartbeat(r: Report):
    f = DATA / "status.json"
    if not f.exists():
        r.add("INFO", "heartbeat", "JARVIS hasn't written a status file yet (not started since the update)")
        return
    status = json.loads(f.read_text(encoding="utf-8"))
    age = dt.datetime.now() - dt.datetime.fromisoformat(status["updated"])
    alive = _pid_alive(status.get("pid"))
    if not alive:
        r.add("WARNING", "heartbeat", f"JARVIS isn't running (last seen {status['updated']})")
    elif age > dt.timedelta(minutes=10) and status.get("state") not in ("muted", "push_to_talk"):
        r.add("WARNING", "heartbeat", f"JARVIS is running but hasn't reported in {age.seconds // 60} min - it may be stuck")
    else:
        r.add("INFO", "heartbeat", f"running (state {status.get('state')}, AI {status.get('backend')})")
    if status.get("last_error"):
        r.add("WARNING", "last_error", status["last_error"])


def _pid_alive(pid) -> bool:
    try:
        import psutil

        return bool(pid) and psutil.pid_exists(int(pid))
    except Exception:
        return True


def check_log(r: Report, state: dict):
    since = state.get("log_checked_until", "")
    newest = since
    errors: list[str] = []
    import paths

    for f in sorted(paths.LOG_FILE.parent.glob("jarvis.log*")):
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (ERROR|CRITICAL)\s+(.*)", line)
            if m and m.group(1) > since:
                errors.append(f"{m.group(1)} {m.group(3)}"[:200])
                newest = max(newest, m.group(1))
            elif re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", line):
                newest = max(newest, line[:19])
    state["log_checked_until"] = newest
    if errors:
        r.add("WARNING" if len(errors) < 5 else "ERROR", "log", f"{len(errors)} new error(s); latest: " + " | ".join(errors[-3:]))
    else:
        r.add("INFO", "log", "no new errors in jarvis.log")


def check_backends(r: Report, s: dict):
    if shutil.which("claude"):
        r.add("INFO", "claude_code", "Claude Code is installed (needed for the Claude-plan backend)")
    else:
        r.add("WARNING", "claude_code", "Claude Code CLI not found - the Claude-plan backend won't start")
    try:
        with urllib.request.urlopen(s["ollama_url"] + "/api/tags", timeout=3) as resp:
            names = {m["name"] for m in json.loads(resp.read())["models"]}
        missing = [m for m in (s["ollama_model"], s["embedding_model"]) if m not in names and f"{m}:latest" not in names]
        if missing:
            r.add("WARNING", "ollama", f"running, but model(s) not downloaded: {', '.join(missing)}")
        else:
            r.add("INFO", "ollama", f"running with {s['ollama_model']} and {s['embedding_model']}")
    except Exception:
        level = "WARNING" if s["fallback_to_ollama"] or s["backend"] == "ollama" else "INFO"
        r.add(level, "ollama", "Ollama isn't reachable - no offline fallback or semantic memory search")


def notify(title: str, message: str):
    """Windows desktop notification using only built-in PowerShell."""
    if sys.platform != "win32":
        return
    msg = message.replace("'", "''").replace("\n", " ")[:250]
    ps = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$x = $t.GetElementsByTagName('text'); $x.Item(0).AppendChild($t.CreateTextNode('{title.replace("'", "''")}')) > $null
$x.Item(1).AppendChild($t.CreateTextNode('{msg}')) > $null
$app = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($t))
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=30)


def run(notify_on_problem: bool = False, run_tests: bool = True) -> Report:
    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    s = settings_mod.load()
    r = Report()
    for name, fn in [("compile", lambda: check_compile(r)), ("tests", lambda: check_tests(r) if run_tests else None),
                     ("dependencies", lambda: check_dependencies(r)), ("data", lambda: check_data_files(r)),
                     ("heartbeat", lambda: check_heartbeat(r)), ("log", lambda: check_log(r, state)),
                     ("backends", lambda: check_backends(r, s))]:
        try:
            fn()
        except Exception as exc:  # a broken check is itself worth reporting, but mustn't stop the others
            r.add("WARNING", name, f"check itself failed: {exc!r}")
    (HEALTH_DIR / "latest.md").write_text(r.markdown(), encoding="utf-8")
    with (HEALTH_DIR / "history.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": dt.datetime.now().isoformat(timespec="seconds"), "worst": r.worst,
                            "problems": [i for i in r.items if i[0] != "INFO"]}) + "\n")
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    if notify_on_problem and LEVELS[r.worst] >= LEVELS["WARNING"]:
        problems = [f"{c}: {m}" for lvl, c, m in r.items if LEVELS[lvl] >= 1]
        notify(f"JARVIS health: {r.worst}", " / ".join(problems)[:250])
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--notify", action="store_true", help="desktop notification if anything is wrong")
    ap.add_argument("--skip-tests", action="store_true")
    args = ap.parse_args()
    r = run(args.notify, not args.skip_tests)
    print(r.markdown())
    return {"INFO": 0, "WARNING": 1}.get(r.worst, 2)


if __name__ == "__main__":
    sys.exit(main())
