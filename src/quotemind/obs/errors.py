"""Error taxonomy and retry policy (FR-113).

The rule that matters: **only model and tool calls are retried.** Deterministic steps - pricing,
assembly, the critic recompute - are never retried, because if they failed the input was wrong and
running them again just produces the same wrong answer more slowly. Retrying arithmetic would also
be the kind of thing that quietly hides a real bug.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

T = TypeVar("T")

RETRY_DELAYS: tuple[float, ...] = (1.0, 4.0)  # FR-113: two retries, exponential


class ErrorCode(str, Enum):
    """FR-113 taxonomy. Every failure the pipeline can record maps to one of these."""

    PARSE_FAIL = "PARSE_FAIL"
    MATCH_FAIL = "MATCH_FAIL"
    PRICE_FAIL = "PRICE_FAIL"
    DRAFT_FAIL = "DRAFT_FAIL"
    CRITIC_FAIL = "CRITIC_FAIL"
    DISPATCH_FAIL = "DISPATCH_FAIL"
    TIMEOUT = "TIMEOUT"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"


_TRANSIENT_MARKERS = (
    "timeout",
    "timed out",
    "temporarily unavailable",
    "rate limit",
    "too many requests",
    "throttl",
    "connection reset",
    "connection aborted",
    "service unavailable",
    "bad gateway",
    "internal server error",
    "502",
    "503",
    "504",
    "429",
)


def is_transient(exc: BaseException) -> bool:
    """True for the failures worth trying again: timeouts, throttling, 5xx, dropped connections."""
    if isinstance(exc, TimeoutError | ConnectionError):
        return True
    message = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


def classify(exc: BaseException, default: ErrorCode) -> ErrorCode:
    """Map an exception to a taxonomy code, defaulting to the stage that raised it."""
    if isinstance(exc, TimeoutError):
        return ErrorCode.TIMEOUT
    message = f"{type(exc).__name__}: {exc}".lower()
    if "timeout" in message or "timed out" in message:
        return ErrorCode.TIMEOUT
    if any(marker in message for marker in ("unavailable", "429", "rate limit", "throttl")):
        return ErrorCode.MODEL_UNAVAILABLE
    return default


async def retry_model_call(
    call: Callable[[], Awaitable[T]],
    *,
    delays: tuple[float, ...] = RETRY_DELAYS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """FR-113: run a model/tool call, retrying transient failures with 1s then 4s backoff.

    A non-transient failure is raised immediately - there is no point asking a model the same broken
    question three times.
    """
    attempt = 0
    while True:
        try:
            return await call()
        except Exception as exc:
            if attempt >= len(delays) or not is_transient(exc):
                raise
            await sleep(delays[attempt])
            attempt += 1
