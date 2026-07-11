"""OSS object storage: quote artifacts, the stub outbox, and the RFQ inbox (FR-091, FR-093, FR-021).

Buckets and key layouts are frozen (section 12.6):
    oss://quotemind-artifacts/quotes/{quote_number}.pdf   the rendered quote, private
    oss://quotemind-artifacts/outbox/{quote_number}.eml   the stub transport's message
    oss://quotemind-inbox/rfq/...                         dropped RFQ documents

Presigned URLs are V4-signed GETs, which is why the bucket is constructed with an explicit region.
"""

from __future__ import annotations

from typing import Any

import oss2
from oss2.credentials import StaticCredentialsProvider

from ..config.settings import Settings

ARTIFACT_PREFIX = "quotes/"
OUTBOX_PREFIX = "outbox/"
TRACE_PREFIX = "traces/"
INBOX_PREFIX = "rfq/"
PRESIGNED_TTL_SECONDS = 600  # FR-091


def artifact_key(quote_number: str) -> str:
    """oss://quotemind-artifacts/quotes/{quote_number}.pdf"""
    return f"{ARTIFACT_PREFIX}{quote_number}.pdf"


def outbox_key(quote_number: str) -> str:
    """oss://quotemind-artifacts/outbox/{quote_number}.eml"""
    return f"{OUTBOX_PREFIX}{quote_number}.eml"


def trace_key(quote_id: str) -> str:
    """oss://quotemind-artifacts/traces/{quote_id}.json (FR-111)"""
    return f"{TRACE_PREFIX}{quote_id}.json"


def _bucket(settings: Settings, name: str) -> Any:
    auth = oss2.ProviderAuthV4(
        StaticCredentialsProvider(
            access_key_id=settings.alibaba_cloud_access_key_id,
            access_key_secret=settings.alibaba_cloud_access_key_secret,
        )
    )
    return oss2.Bucket(auth, settings.oss_endpoint, name, region=settings.region)


class ArtifactStore:
    """Reads and writes the two OSS buckets. Objects stay private; access is via presigned URLs."""

    def __init__(self, artifacts: Any, inbox: Any) -> None:
        self.artifacts = artifacts
        self.inbox = inbox

    @classmethod
    def from_settings(cls, settings: Settings) -> ArtifactStore:
        return cls(
            artifacts=_bucket(settings, settings.oss_bucket_artifacts),
            inbox=_bucket(settings, settings.oss_bucket_inbox),
        )

    # --- artifacts (FR-091, FR-093) ---
    def put_pdf(self, quote_number: str, data: bytes) -> str:
        key = artifact_key(quote_number)
        self.artifacts.put_object(key, data, headers={"Content-Type": "application/pdf"})
        return key

    def put_eml(self, quote_number: str, data: bytes) -> str:
        key = outbox_key(quote_number)
        self.artifacts.put_object(key, data, headers={"Content-Type": "message/rfc822"})
        return key

    def put_trace(self, quote_id: str, document_json: str) -> str:
        """FR-111: persist the reasoning trace next to the quote artifacts."""
        key = trace_key(quote_id)
        self.artifacts.put_object(
            key, document_json.encode("utf-8"), headers={"Content-Type": "application/json"}
        )
        return key

    def presigned_get(self, key: str, expires: int = PRESIGNED_TTL_SECONDS) -> str:
        """FR-091: a fresh V4-signed GET URL. slash_safe keeps the key's slashes unescaped."""
        url: str = self.artifacts.sign_url("GET", key, expires, slash_safe=True)
        return url

    def exists(self, key: str) -> bool:
        return bool(self.artifacts.object_exists(key))

    # --- inbox (FR-021) ---
    def list_inbox(self, prefix: str = INBOX_PREFIX, limit: int = 100) -> list[str]:
        """Keys dropped under rfq/. Directory placeholders are skipped."""
        listing = oss2.ObjectIterator(self.inbox, prefix=prefix, max_keys=limit)
        return [obj.key for obj in listing if not obj.key.endswith("/")]

    def get_inbox_object(self, key: str) -> bytes:
        data: bytes = self.inbox.get_object(key).read()
        return data
