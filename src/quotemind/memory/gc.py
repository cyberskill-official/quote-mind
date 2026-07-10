"""Memory garbage collection (FR-046).

`python -m quotemind.memory.gc` runs run_gc against live Tablestore. Pruning is deterministic:
a memory is hard-deleted when its effective ceiling (importance x recency decay) falls below the
floor. Compaction of a customer's episodic memories beyond the limit into an LLM-written profile
summary is flagged here and produced by the drafter model in the agent path.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone

from ..models import EpisodicQuoteMemory
from .episodic import COMPACTION_LIMIT, PRUNE_FLOOR, age_in_days, should_prune
from .store import MemoryFacade


def needs_compaction(memory_count: int, limit: int = COMPACTION_LIMIT) -> bool:
    """FR-046: a customer's episodic memories should be compacted once they exceed the limit."""
    return memory_count > limit


def run_gc(facade: MemoryFacade, on_date: datetime | None = None) -> dict[str, int]:
    """Prune decayed episodic memories and count customers that need compaction.

    Live operation: scans and deletes KnowledgeStore documents in the episodic tenants.
    """
    now = on_date or datetime.now(timezone.utc)
    per_customer: Counter[str] = Counter()
    pruned = 0
    scanned = 0
    for document in facade.knowledge.get_all_documents():
        tenant = getattr(document, "tenant_id", "") or ""
        if not tenant.startswith("episodic:"):
            continue
        scanned += 1
        metadata = document.metadata or {}
        payload = metadata.get("payload_json")
        if not isinstance(payload, str):
            continue
        memory = EpisodicQuoteMemory.model_validate_json(payload)
        if should_prune(memory.importance, age_in_days(memory.created_at, now), PRUNE_FLOOR):
            facade.knowledge.delete_document(document.document_id, tenant_id=tenant)
            pruned += 1
        else:
            per_customer[tenant] += 1
    compaction_candidates = sum(1 for count in per_customer.values() if needs_compaction(count))
    return {"scanned": scanned, "pruned": pruned, "compaction_candidates": compaction_candidates}


def main() -> int:
    from ..config.settings import require_settings

    report = run_gc(MemoryFacade.from_settings(require_settings()))
    for key, value in report.items():
        print(f"gc: {key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
