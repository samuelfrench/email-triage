"""File-based debug log shared by CLI and webapp.

Single rotating log file at data/webapp.log. Helpers in here also expose
a structured way for the webapp to query recent entries via /api/debug/logs.
"""
from __future__ import annotations

import logging
import logging.handlers
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import DATA_DIR

LOG_PATH = Path(DATA_DIR) / "webapp.log"
_TAIL_BUFFER_SIZE = 2000

_lock = threading.Lock()
_tail_buffer: deque[dict] = deque(maxlen=_TAIL_BUFFER_SIZE)
_configured = False


class _RingBufferHandler(logging.Handler):
    """Keep the last N records in memory so /api/debug/logs is instant."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.fromtimestamp(record.created).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                entry["exc"] = logging.Formatter().formatException(record.exc_info)
            _tail_buffer.append(entry)
        except Exception:
            self.handleError(record)


def configure(level: int = logging.INFO) -> logging.Logger:
    """Idempotently configure the root logger to write to data/webapp.log + a ring buffer."""
    global _configured
    with _lock:
        if _configured:
            return logging.getLogger("email_triage")

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

        file_handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=2_000_000, backupCount=3
        )
        file_handler.setFormatter(fmt)
        file_handler.setLevel(level)

        ring_handler = _RingBufferHandler()
        ring_handler.setLevel(level)

        root = logging.getLogger("email_triage")
        root.setLevel(level)
        root.handlers.clear()
        root.addHandler(file_handler)
        root.addHandler(ring_handler)
        root.propagate = False

        _configured = True
        root.info("debug log configured at %s", LOG_PATH)
        return root


def get(name: Optional[str] = None) -> logging.Logger:
    """Get a child logger under email_triage."""
    configure()
    return logging.getLogger(f"email_triage.{name}" if name else "email_triage")


def tail(limit: int = 200, level: Optional[str] = None) -> list[dict]:
    """Return up to `limit` most recent log entries from the ring buffer.

    Optional `level` filter (e.g. 'ERROR') filters by exact level name.
    """
    with _lock:
        items = list(_tail_buffer)
    if level:
        items = [e for e in items if e["level"] == level.upper()]
    return items[-limit:]


def clear_buffer() -> int:
    """Clear the in-memory ring buffer (file log untouched). Returns prior count."""
    with _lock:
        n = len(_tail_buffer)
        _tail_buffer.clear()
    return n
