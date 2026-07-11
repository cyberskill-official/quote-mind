"""FR-021 OSS drop channel: objects under oss://quotemind-inbox/rfq/ become quotes.

Two entry points, one code path:

    handler(event, context)     Function Compute OSS trigger (quotemind-ingest)
    python deploy/ingest.py     scan the inbox once and ingest anything not seen before

The dropped object's key becomes the quote's source_uri and the channel is oss_drop, so an RFQ that
arrived by file is indistinguishable downstream from one posted to the API.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from quotemind.api.app import SELLER_BLOCK
from quotemind.cloud import ArtifactStore
from quotemind.config.settings import require_settings
from quotemind.memory.quotes import QuoteStore
from quotemind.memory.store import MemoryFacade
from quotemind.models import Channel, QuoteRecord
from quotemind.service import QuoteService

TEXT_SUFFIXES = (".txt", ".eml", ".md")


def build_service() -> QuoteService:
    settings = require_settings()
    return QuoteService(
        store=QuoteStore.from_settings(settings),
        facade=MemoryFacade.from_settings(settings),
        settings=settings,
        seller_block=SELLER_BLOCK,
        artifacts=ArtifactStore.from_settings(settings),
    )


async def ingest_key(service: QuoteService, artifacts: ArtifactStore, key: str) -> QuoteRecord:
    """Register the dropped object as a quote and run the pipeline over it."""
    raw = artifacts.get_inbox_object(key)
    filename = key.rsplit("/", 1)[-1]
    source_uri = f"oss://{service.settings.oss_bucket_inbox}/{key}"

    if not filename.lower().endswith(TEXT_SUFFIXES):
        # PDF/xlsx/image parsing lands with FR-031/032/033. Until the parser router is wired
        # here, a non-text drop is registered and parked for a human rather than guessed at.
        record, _ = service.submit(
            text=f"[binary drop: {filename}]",
            channel=Channel.OSS_DROP,
            filename=filename,
            source_uri=source_uri,
        )
        return record

    text = raw.decode("utf-8", errors="replace")
    record, created = service.submit(
        text=text, channel=Channel.OSS_DROP, filename=filename, source_uri=source_uri
    )
    if not created:  # FR-024: the same bytes dropped twice is still one quote
        return record
    return await service.process(record, text)


def handler(event: Any, _context: Any = None) -> dict[str, Any]:
    """Function Compute OSS trigger entry point."""
    payload = json.loads(event) if isinstance(event, str | bytes) else event
    service = build_service()
    artifacts = service.artifacts
    results: list[dict[str, str]] = []
    for record_event in payload.get("events", []):
        key = record_event["oss"]["object"]["key"]
        record = asyncio.run(ingest_key(service, artifacts, key))
        results.append({"key": key, "quote_id": record.quote_id, "status": record.status.value})
    return {"ingested": results}


def scan() -> None:
    """Demo path: ingest every object currently under rfq/ (idempotent by content hash)."""
    service = build_service()
    artifacts = service.artifacts
    keys = artifacts.list_inbox()
    if not keys:
        print("ingest: inbox is empty")
        return
    for key in keys:
        record = asyncio.run(ingest_key(service, artifacts, key))
        print(f"ingest: {key} -> {record.quote_number} ({record.status.value})")


if __name__ == "__main__":
    sys.exit(scan())
