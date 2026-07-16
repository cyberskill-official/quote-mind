"""TASK-046: gc prunes decayed episodic memories and flags compaction (SDK mocked)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from tablestore_for_agent_memory.base.base_knowledge_store import Document

from quotemind.memory import needs_compaction
from quotemind.memory.gc import run_gc
from quotemind.models import BilingualText, EpisodicQuoteMemory, Outcome

_NOW = datetime(2026, 7, 11, tzinfo=timezone.utc)


def _episodic_doc(
    memory_id: str, importance: float, age_days: int, customer: str = "cust_x"
) -> Document:
    memory = EpisodicQuoteMemory(
        memory_id=memory_id,
        quote_number="QM-2026-0001",
        summary=BilingualText(vi="x", en="x"),
        outcome=Outcome.APPROVED,
        importance=importance,
        created_at=_NOW - timedelta(days=age_days),
    )
    return Document(
        document_id=memory_id,
        tenant_id=f"episodic:{customer}",
        metadata={"payload_json": memory.model_dump_json(), "importance": importance},
    )


def test_needs_compaction() -> None:
    assert needs_compaction(51) is True
    assert needs_compaction(50) is False


def test_run_gc_prunes_decayed_and_ignores_other_tenants() -> None:
    facade = MagicMock()
    docs = [
        _episodic_doc("old", importance=0.1, age_days=400),  # ceiling < 0.05 -> prune
        _episodic_doc("fresh", importance=0.9, age_days=3),  # keep
        Document(document_id="cat", tenant_id="catalog", metadata={"payload_json": "{}"}),
    ]
    facade.knowledge.get_all_documents.return_value = iter(docs)

    report = run_gc(facade, on_date=_NOW)

    assert report["scanned"] == 2
    assert report["pruned"] == 1
    assert report["compaction_candidates"] == 0
    facade.knowledge.delete_document.assert_called_once_with("old", tenant_id="episodic:cust_x")
