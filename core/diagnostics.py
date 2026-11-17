"""Low-volume diagnostic log for focus, window, input and shutdown events.

The log is intentionally written outside the render loop: only state
transitions are recorded, so logging can never turn into a frame-rate cost.
Set ``DESKTOP_SLASH_DEBUG=1`` to mirror entries to stderr (tests use this).
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from pathlib import Path

_LOCK = threading.Lock()
_MAX_BYTES = 2 * 1024 * 1024
_ONCE: dict[str, str] = {}
_LOG_PATH: Path | None = None
_MIRROR = os.environ.get("DESKTOP_SLASH_DEBUG", "").strip().lower() in {
    "1",
    "true",
    "yes",
}


def log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is not None:
        return _LOG_PATH
    base = os.environ.get("APPDATA") or str(Path.home() / ".desktop_slash")
    path = Path(base) / "DesktopSlash" / "desktop_slash.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path.home() / ".desktop_slash" / "desktop_slash.log"
        path.parent.mkdir(parents=True, exist_ok=True)
    _LOG_PATH = path
    return path


def _write(line: str) -> None:
    with _LOCK:
        path = log_path()
        try:
            if path.exists() and path.stat().st_size > _MAX_BYTES:
                rotated = path.with_name(path.name + ".1")
                try:
                    os.replace(path, rotated)
                except OSError:
                    pass
        except OSError:
            pass
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass
    if _MIRROR:
        try:
            sys.stderr.write(line + "\n")
            sys.stderr.flush()
        except (OSError, ValueError):
            pass


def log(category: str, message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
    _write(f"{stamp} [{category}] {message}")


def log_once(category: str, key: str, message: str) -> None:
    """Record a transition only when *key* changes value."""
    with _LOCK:
        if _ONCE.get(key) == message:
            return
        _ONCE[key] = message
    log(category, message)


def log_exception(category: str, message: str) -> None:
    detail = traceback.format_exc().rstrip()
    log(category, f"{message}\n{detail}")


def reset_once() -> None:
    with _LOCK:
        _ONCE.clear()


def session_banner(role: str) -> None:
    log("SESSION", f"{role} pid={os.getpid()} python={sys.version.split()[0]}")
