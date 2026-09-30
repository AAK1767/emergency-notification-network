"""
logger.py — Timestamped, tag-based logging utility.

Produces output like:
    2026-09-30 10:00:03.421 [SERVER] C1 registered
    2026-09-30 10:00:08.932 [CLIENT:C1] ALERT seq=42 received
"""

import sys
import threading
from datetime import datetime

_lock = threading.Lock()

# ANSI colour codes (disabled automatically if not a TTY)
_COLORS = {
    "DEBUG":   "\033[90m",      # grey
    "INFO":    "\033[97m",      # white
    "WARN":    "\033[93m",      # yellow
    "ERROR":   "\033[91m",      # red
    "SUCCESS": "\033[92m",      # green
    "RESET":   "\033[0m",
}

_use_color = sys.stdout.isatty()

# Global log level: DEBUG=0, INFO=1, WARN=2, ERROR=3
_LEVEL_MAP = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
_current_level = 0  # default: show everything

# Optional file handle for persisting logs
_log_file = None


def set_level(level: str):
    global _current_level
    _current_level = _LEVEL_MAP.get(level.upper(), 0)


def set_log_file(path: str):
    """Open a file for appending log lines (in addition to stdout)."""
    global _log_file
    _log_file = open(path, "a", encoding="utf-8")


def _emit(level: str, tag: str, message: str):
    if _LEVEL_MAP.get(level, 1) < _current_level:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"{now} [{tag}] {message}"
    with _lock:
        if _use_color:
            color = _COLORS.get(level, _COLORS["INFO"])
            print(f"{color}{line}{_COLORS['RESET']}", flush=True)
        else:
            print(line, flush=True)
        if _log_file:
            _log_file.write(line + "\n")
            _log_file.flush()


# Public API -----------------------------------------------------------

def debug(tag: str, msg: str):
    _emit("DEBUG", tag, msg)

def info(tag: str, msg: str):
    _emit("INFO", tag, msg)

def warn(tag: str, msg: str):
    _emit("WARN", tag, msg)

def error(tag: str, msg: str):
    _emit("ERROR", tag, msg)

def success(tag: str, msg: str):
    _emit("SUCCESS", tag, msg)
