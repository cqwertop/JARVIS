"""JARVIS settings.

Defaults live here. Your own changes go in data/settings.json, which is created the first time JARVIS runs
and only needs to contain the values you want to change (everything else falls back to these defaults).
data/ is never committed to git, so personal settings stay on this PC.
"""

import copy
import json
import logging
from pathlib import Path

from paths import DATA_DIR

SETTINGS_FILE = DATA_DIR / "settings.json"

log = logging.getLogger("jarvis.settings")

DEFAULTS: dict = {
    "assistant_name": "JARVIS",
    # Spellings speech recognition produces for the name. The first one is the "real" one.
    "wake_words": ["jarvis", "jervis", "javis", "jarves", "jarvi", "jarvus"],
    # How JARVIS decides you're talking to it:
    #   conversation  - say "Jarvis" once, then keep talking without it until you go quiet (default)
    #   wake_word     - every command must include "Jarvis"
    #   always        - everything heard goes to JARVIS, which ignores speech not meant for it (uses more AI usage)
    #   push_to_talk  - the microphone only opens when you press the talk hotkey / HUD button
    #   text          - microphone never used; type to JARVIS in the on-screen panel
    "listen_mode": "conversation",
    # Microphone to use (name as the system lists it). Empty = the system default.
    "microphone_name": "",
    # In conversation mode: how long after JARVIS answers you can follow up without saying its name.
    "follow_up_seconds": 20,
    # Let "stop" / "Jarvis, ..." cut JARVIS off while it's talking.
    "barge_in": True,
    # Short beep when JARVIS starts listening for a command.
    "listen_chime": True,
    # Which AI to use: auto (Claude API if ANTHROPIC_API_KEY is set, else your Claude plan), api (Claude API key),
    # pro (Claude plan via Claude Code), online (another company's API, see "online"), ollama (local model)
    "backend": "auto",
    "claude_model_api": "claude-sonnet-5-5",
    # For backend "online": provider id from providers.py (openai, gemini, openrouter, groq, mistral, deepseek,
    # xai, custom), the model, and (custom only) the service's base URL. The key itself is in the OS keyring.
    "online": {"provider": "", "model": "", "base_url": ""},
    "claude_model_pro": "sonnet",
    # If Claude is unreachable or out of usage, answer with the local Ollama model instead.
    "fallback_to_ollama": True,
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen3:8b",
    "embedding_model": "embeddinggemma",
    "voice": {
        "neural_voice": "en-GB-RyanNeural",
        "rate": "+5%",
        "volume": "+0%",
        "fallback_voice": "David",
        "fallback_rate": 1,
    },
    "personality": {
        "style": "professional",  # professional | casual
        "humor": True,
        "address_user_as": "sir",  # leave empty to not use a title
        "verbosity": "concise",  # concise | detailed
    },
    "hud": True,  # small on-screen status indicator with mute / stop buttons
    "hotkeys": {
        "enabled": True,
        "mute": "ctrl+alt+m",  # turn the microphone off / on
        "stop": "ctrl+alt+s",  # stop JARVIS talking
        "talk": "ctrl+alt+j",  # start listening without saying the name
        "panel": "ctrl+alt+h",  # hide / show the on-screen panel
    },
    "log_transcripts": True,  # write what you said / JARVIS said to jarvis.log
    "start_at_login": False,  # set by the setup wizard
    "setup_complete": False,  # the installed app shows the setup wizard until this is true
}

LISTEN_MODES = ("conversation", "wake_word", "always", "push_to_talk", "text")


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if key.startswith("_"):
            continue  # comments
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path: Path = SETTINGS_FILE) -> dict:
    """Defaults merged with the user's data/settings.json. Never raises: a broken file falls back to defaults."""
    user: dict = {}
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(user, dict):
                raise ValueError("settings.json must contain a JSON object")
        except (ValueError, OSError) as exc:
            log.error("Ignoring %s (%s) - using defaults. Fix or delete the file.", path, exc)
            user = {}
    else:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            starter = {
                "_comment": "Put only the settings you want to change here. All options and their defaults are in settings.py.",
                "listen_mode": DEFAULTS["listen_mode"],
                "follow_up_seconds": DEFAULTS["follow_up_seconds"],
            }
            path.write_text(json.dumps(starter, indent=2), encoding="utf-8")
        except OSError:
            pass
    merged = _merge(DEFAULTS, user)
    if merged["listen_mode"] not in LISTEN_MODES:
        log.error("Unknown listen_mode %r - using 'conversation'.", merged["listen_mode"])
        merged["listen_mode"] = "conversation"
    return merged


def update(changes: dict, path: Path = SETTINGS_FILE) -> dict:
    """Merge `changes` into the user's settings file, keeping everything else they set. Returns the new file content."""
    current: dict = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(current, dict):
                current = {}
        except (ValueError, OSError):
            backup = path.with_suffix(".corrupt.json")
            try:
                backup.write_bytes(path.read_bytes())
            except OSError:
                pass
            current = {}
    current = _merge(current, changes) if current else dict(changes)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, indent=2), encoding="utf-8")
    tmp.replace(path)
    return current
