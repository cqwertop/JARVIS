"""Logging setup. jarvis.log is size-limited (rotates at 1 MB, keeps 3 old files) so it can't fill the disk."""

import logging
import logging.handlers
import sys
from paths import LOG_FILE
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class _StreamToLogger:
    """Catches stray print()s / library output when JARVIS runs hidden, so they land in the log too."""

    def __init__(self, logger: logging.Logger, level: int):
        self._logger, self._level, self._buf = logger, level, ""

    def write(self, text: str):
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._logger.log(self._level, line.rstrip())

    def flush(self):
        if self._buf.strip():
            self._logger.log(self._level, self._buf.rstrip())
        self._buf = ""


def setup(to_file: bool, verbose: bool = False) -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    if to_file:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(handler)
        sys.stdout = _StreamToLogger(logging.getLogger("stdout"), logging.INFO)
        sys.stderr = _StreamToLogger(logging.getLogger("stderr"), logging.ERROR)
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s" if not verbose else FORMAT))
        root.addHandler(handler)
    # Quiet chatty libraries.
    for noisy in ("httpx", "httpcore", "anthropic", "urllib3", "asyncio", "comtypes", "mcp", "claude_agent_sdk"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger("jarvis")
