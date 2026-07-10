"""Structured JSON logging to stdout (FR-008).

Emits one JSON object per line with timestamp, level, quote_id, agent, and event.
UTF-8 with ensure_ascii disabled so Vietnamese diacritics stay byte-exact.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import sys
from typing import Any

# Attributes present on a bare LogRecord; anything extra is a caller-supplied field.
_RESERVED = frozenset(vars(logging.makeLogRecord({})).keys())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": _dt.datetime.fromtimestamp(record.created, tz=_dt.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key in ("quote_id", "agent"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Route the root logger to stdout as JSON lines (idempotent)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def log_event(
    event: str,
    *,
    quote_id: str | None = None,
    agent: str | None = None,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    extra: dict[str, Any] = {"quote_id": quote_id, "agent": agent}
    extra.update(fields)
    logging.getLogger("quotemind").log(level, event, extra=extra)
