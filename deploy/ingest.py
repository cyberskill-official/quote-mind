"""TASK-021 OSS drop channel: objects under oss://quotemind-inbox/rfq/ become quotes.

Two entry points, one code path:

    handler(event, context)     Function Compute OSS trigger (quotemind-ingest)
    python deploy/ingest.py     scan the inbox once and ingest anything not seen before

The dropped object's key becomes the quote's source_uri and the channel is oss_drop, so an RFQ that
arrived by file is indistinguishable downstream from one posted to the API.

And it really is the same path now. It was not. This module used to check the filename against a
short list of text suffixes and, for anything else, register the quote and *park it* behind a
comment saying PDF and Excel parsing would "land with TASK-031/032". Those tasks landed. The comment
did not - so the one intake channel that exists specifically for files was the only one that could
not read a file, and a dropped spreadsheet became a numbered quote stuck at `received`, forever.
The parser routing now lives in QuoteService, and both channels call it.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from quotemind.api.app import SELLER_BLOCK
from quotemind.cloud import ArtifactStore
from quotemind.config.settings import require_settings
from quotemind.intake import doc_type_for
from quotemind.memory.quotes import QuoteStore
from quotemind.memory.store import MemoryFacade
from quotemind.models import Channel, DocType, QuoteRecord
from quotemind.service import QuoteService


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
    doc_type = doc_type_for(filename)

    # Text is decoded; a spreadsheet, PDF or image is handed to the parser as the bytes it is. The
    # record's `text` is only what a reviewer sees in the queue, so for a file it is a label - but
    # the idempotency digest is taken over the real bytes (TASK-024), not over that label. Hashing the
    # label would collide two different spreadsheets that happened to share a filename.
    if doc_type is DocType.EMAIL_TEXT:
        payload: str | bytes = raw.decode("utf-8", errors="replace")
        text = str(payload)
    else:
        payload = raw
        text = f"[{doc_type.value}] {filename}"

    record, created = service.submit(
        text=text,
        digest_payload=raw,
        channel=Channel.OSS_DROP,
        filename=filename,
        source_uri=source_uri,
    )
    if not created:  # TASK-024: the same bytes dropped twice is still one quote
        return record
    return await service.process(record, payload, doc_type=doc_type)


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
