"""JARVIS settings.

Defaults live here. Your own changes go in data/settings.json, which is created the first time JARVIS runs
and only needs to contain the values you want to change (everything else falls back to these defaults).
data/ is never committed to git, so personal settings stay on this PC.
"""

import copy
import json
import logging
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
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
    "listen_mode": "conversation",
    # In conversation mode: how long after JARVIS answers you can follow up without saying its name.
    "follow_up_seconds": 20,
    # Let "stop" / "Jarvis, ..." cut JARVIS off while it's talking.
    "barge_in": True,
    # Short beep when JARVIS starts listening for a command.
    "listen_chime": True,
    # Which AI to use: auto (Claude API if ANTHROPIC_API_KEY is set, else your Claude plan), api, pro, ollama
    "backend": "auto",
    "claude_model_api": "claude-sonnet-5-5",
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
    },
    "log_transcripts": True,  # write what you said / JARVIS said to jarvis.log
}


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
    if merged["listen_mode"] not in ("conversation", "wake_word", "always", "push_to_talk"):
        log.error("Unknown listen_mode %r - using 'conversation'.", merged["listen_mode"])
        merged["listen_mode"] = "conversation"
    return merged
