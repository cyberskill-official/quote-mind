"""Live smoke for FR-111/112: run one real RFQ and prove the trace is persisted, with real costs.

    python deploy/smoke_trace.py

Talks to real DashScope, real Tablestore and real OSS. Prints the trace exactly as the dashboard's
panel will render it, then re-reads it from OSS so the persistence path is proven, not assumed.
"""

from __future__ import annotations

import asyncio
import json

from quotemind.api.app import SELLER_BLOCK
from quotemind.cloud.oss import ArtifactStore, trace_key
from quotemind.config.settings import require_settings
from quotemind.memory.quotes import QuoteStore
from quotemind.memory.store import MemoryFacade
from quotemind.service import QuoteService

RFQ = """Kính gửi CyberSkill,
Công ty Thành Công cần báo giá gấp:
- 2 laptop Dell Latitude 5450 i5 16GB
- 1 màn hình Dell 24 inch
Trân trọng, Chị Lan - mua.hang@thanhcong.vn
"""


async def main() -> None:
    settings = require_settings()
    service = QuoteService(
        store=QuoteStore.from_settings(settings),
        facade=MemoryFacade.from_settings(settings),
        settings=settings,
        seller_block=SELLER_BLOCK,
    )

    record, created = service.submit(text=RFQ)
    print(f"submitted {record.quote_number} ({record.quote_id}) created={created}")
    final = await service.process(record, RFQ, customer_email="mua.hang@thanhcong.vn")
    print(f"status: {final.status.value}  flags: {final.flags}")

    document = service.trace(final.quote_id)  # API-05, read back from the durable row
    print(f"\ntrace: {len(document['steps'])} steps")
    for step in document["steps"]:
        target = step["tool"] or step["model"] or "-"
        print(
            f"  {step['seq']:>2}. {step['agent']:<15} {step['action']:<9} {target:<20}"
            f" {step['tokens_in']:>6}->{step['tokens_out']:<5} tok"
            f"  ${step['cost_usd']:<10} {step['duration_ms']:>5} ms  {step['summary']}"
        )
    print(
        f"\ntotals: {document['total_tokens_in']} -> {document['total_tokens_out']} tokens,"
        f" ${document['total_cost_usd']}, {document['total_duration_ms']} ms"
    )
    print(f"content bodies captured: {len(document['contents'])} (TRACE_CONTENT off = 0)")

    # The point of the exercise: it is really in OSS, not just in memory.
    artifacts = ArtifactStore.from_settings(settings)
    key = trace_key(final.quote_id)
    raw = artifacts.artifacts.get_object(key).read()
    persisted = json.loads(raw)
    print(f"\noss://{settings.oss_bucket_artifacts}/{key}: {len(raw)} bytes")
    print(f"round-trip: {len(persisted['steps'])} steps, ${persisted['total_cost_usd']}")


if __name__ == "__main__":  # pragma: no cover - operational script
    asyncio.run(main())
