"""Alibaba Cloud adapters (OSS object storage)."""

from __future__ import annotations

from .oss import (
    ARTIFACT_PREFIX,
    INBOX_PREFIX,
    OUTBOX_PREFIX,
    PRESIGNED_TTL_SECONDS,
    TRACE_PREFIX,
    ArtifactStore,
    artifact_key,
    outbox_key,
    trace_key,
)

__all__ = [
    "ARTIFACT_PREFIX",
    "INBOX_PREFIX",
    "OUTBOX_PREFIX",
    "TRACE_PREFIX",
    "PRESIGNED_TTL_SECONDS",
    "ArtifactStore",
    "artifact_key",
    "outbox_key",
    "trace_key",
]
