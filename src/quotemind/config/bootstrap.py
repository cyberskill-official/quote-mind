"""TASK-012: model availability check at cold start, with documented fallbacks.

Every model id in section 4.6 is frozen, which is a strength right up until Model Studio retires one
of them - at which point a frozen constant becomes a hard outage. So on cold start each primary is
probed with a 1-token call, and an unavailable primary activates its documented fallback
(qwen3-max -> qwen-max, qwen-vl-ocr -> qwen3-vl-plus) with a WARN.

Two properties this is built to have, because the alternative in each case is worse:

- **It never blocks a cold start.** A probe that times out or errors marks the model UNKNOWN and the
  primary is used anyway. A boot check that can take the API down is a liability, not a safeguard -
  the failure it protects against is rarer than the failure it introduces.
- **The substitution is visible.** /health reports which model is actually in use and why. A silent
  fallback is how you end up debugging a quality regression for a day before noticing you have been
  running on a different model since Tuesday.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from ..obs.log import log_event
from .models import EMBED_DIMENSIONS, FALLBACKS, MODEL_CONSTANTS
from .settings import Settings

AVAILABLE = "available"
FALLBACK = "fallback"
UNKNOWN = "unknown"  # the probe itself failed; we proceed on the primary rather than block boot


@dataclass
class ModelStatus:
    """What we know about one frozen model constant, and what we will actually call."""

    role: str
    primary: str
    effective: str
    state: str
    detail: str = ""

    @property
    def substituted(self) -> bool:
        return self.effective != self.primary


# A 16x16 white PNG. The vision models reject a text-only message *and* an image smaller than
# 10px, so both facts had to be learned from the live service rather than assumed.
_PIXEL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFElEQVR4nGP4TyJgGNUwqmH4agAAr639H708R/EAAAAASUVORK5CYII="
)

# A model that rejects our *input* has, by definition, answered us: it is deployed, reachable and
# talking. Only a model that is genuinely gone should trigger a fallback. Without this distinction
# the check is fragile in the worst possible direction - any future tightening of an input rule by
# Model Studio would silently reroute production traffic onto a different model, which is precisely
# the outcome TASK-012 exists to prevent. So the probe fails closed on absence and open on argument.
_ABSENT_MARKERS = (
    "model_not_found",
    "modelnotfound",
    "does not exist",
    "not found",
    "unsupported model",
    "invalidmodel",
)


def _modality(model: str) -> str:
    """Which kind of call this model actually answers.

    This exists because of a bug the live run caught: probing every frozen id with the same
    text-chat call made `text-embedding-v4` (which has no chat endpoint) and `qwen-vl-ocr` (which
    rejects a message with no image part) both look unavailable. The vision model then "fell back"
    to qwen3-vl-plus on a perfectly healthy service. A health check that manufactures its own
    outages is worse than no health check - it reroutes production traffic for no reason, and it
    trains you to ignore it.
    """
    if model.startswith("text-embedding"):
        return "embeddings"
    if "-vl-" in model or model.endswith("-ocr"):
        return "vision"
    return "chat"


def _probe(client: OpenAI, model: str) -> tuple[bool, str]:
    """One cheap, correctly-shaped call. True if the model answered; the content is irrelevant."""
    try:
        modality = _modality(model)
        if modality == "embeddings":
            client.embeddings.create(model=model, input=["."], dimensions=EMBED_DIMENSIONS)
        elif modality == "vision":
            client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": _PIXEL}},
                            {"type": "text", "text": "."},
                        ],
                    }
                ],
                max_tokens=1,
            )
        else:
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "."}],
                max_tokens=1,
            )
    except Exception as exc:  # noqa: BLE001 - the SDK raises a different type per failure mode
        message = f"{type(exc).__name__}: {exc}"
        if _is_absent(exc):
            return False, message
        # It answered - just not the way we asked. That is a live model, and a bad probe.
        return True, f"reachable (probe rejected: {type(exc).__name__})"
    return True, ""


def _is_absent(exc: BaseException) -> bool:
    """True only when the model itself is gone, not when it merely disliked the probe."""
    message = str(exc).lower()
    return any(marker in message for marker in _ABSENT_MARKERS)


def check_models(settings: Settings, *, client: Any | None = None) -> list[ModelStatus]:
    """Probe every frozen model constant; fall back where documented (TASK-012)."""
    probe_client = client or OpenAI(
        api_key=settings.dashscope_api_key, base_url=settings.dashscope_base_url
    )
    statuses: list[ModelStatus] = []
    seen: dict[str, ModelStatus] = {}  # several roles share a model; probe each id once

    for role, primary in MODEL_CONSTANTS.items():
        if primary in seen:
            cached = seen[primary]
            statuses.append(
                ModelStatus(role, primary, cached.effective, cached.state, cached.detail)
            )
            continue

        started = time.perf_counter()
        ok, reason = _probe(probe_client, primary)
        elapsed = int((time.perf_counter() - started) * 1000)

        if ok:
            status = ModelStatus(role, primary, primary, AVAILABLE, f"{elapsed} ms")
        elif primary in FALLBACKS:
            substitute = FALLBACKS[primary]
            status = ModelStatus(role, primary, substitute, FALLBACK, reason)
            log_event(
                "model_fallback_activated",
                level=logging.WARNING,
                role=role,
                primary=primary,
                fallback=substitute,
                reason=reason,
            )
        else:
            # No documented fallback. Proceed on the primary and say so - the call may still work
            # (the probe could have hit a transient), and refusing to boot would be worse.
            status = ModelStatus(role, primary, primary, UNKNOWN, reason)
            log_event(
                "model_probe_failed_no_fallback",
                level=logging.WARNING,
                role=role,
                primary=primary,
                reason=reason,
            )

        seen[primary] = status
        statuses.append(status)

    return statuses


def health_models(statuses: list[ModelStatus]) -> dict[str, Any]:
    """The /health view (TASK-009 + TASK-012 AC): what we call, and any substitution, visibly."""
    return {
        "models": {status.role: status.effective for status in statuses},
        "substitutions": {
            status.role: {
                "primary": status.primary,
                "using": status.effective,
                "why": status.detail,
            }
            for status in statuses
            if status.substituted
        },
        "unverified": [status.role for status in statuses if status.state == UNKNOWN],
    }
