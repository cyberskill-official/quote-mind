"""TASK-008: logs are single-line JSON with the required keys and preserved diacritics."""

from __future__ import annotations

import io
import json
import logging

from quotemind.obs.log import JsonFormatter, log_event


def test_json_formatter_has_required_keys_and_keeps_diacritics() -> None:
    record = logging.LogRecord(
        name="quotemind",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Báo giá",
        args=None,
        exc_info=None,
    )
    record.quote_id = "QM-2026-0007"
    record.agent = "drafter"
    line = JsonFormatter().format(record)
    data = json.loads(line)
    assert {"ts", "level", "event", "quote_id", "agent"} <= set(data)
    assert data["event"] == "Báo giá"
    assert "Báo giá" in line  # ensure_ascii disabled: diacritics not escaped


def test_log_event_emits_one_json_line() -> None:
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("quotemind")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        log_event("received", quote_id="QM-2026-0007", agent="intake")
    finally:
        logger.removeHandler(handler)

    data = json.loads(buffer.getvalue().strip())
    assert data["event"] == "received"
    assert data["quote_id"] == "QM-2026-0007"
    assert data["agent"] == "intake"
