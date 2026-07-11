"""FR-044/045/046: episodic memory, written on a human decision and recalled before the next one.

The scoring in `memory/episodic.py` has been correct and unit-tested since PR-4. It was also, until
now, dead code: nothing called it. These tests cover the wiring, and in particular the two things
wiring gets wrong - ranking on the wrong number, and letting a memory failure cost a decision.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from quotemind.memory.recall import recall_episodes, summarize, write_episode
from quotemind.models import BilingualText, EpisodicQuoteMemory, Outcome

from .test_service import _result, _Settings

NOW = datetime(2026, 7, 11, tzinfo=timezone.utc)


class FakeEmbed:
    """Embeddings are irrelevant to ranking here - the fake similarity comes from the store."""

    def __init__(self) -> None:
        self.embeddings = self
        self.calls = 0

    def create(self, **_kwargs: Any) -> Any:
        self.calls += 1
        datum = type("E", (), {"embedding": [0.0] * 1024, "index": 0})()
        return type("R", (), {"data": [datum], "usage": None})()


class FakeChat:
    def __init__(self, content: str) -> None:
        self.content = content
        self.chat = self
        self.completions = self

    def create(self, **_kwargs: Any) -> Any:
        message = type("M", (), {"content": self.content})()
        return type("R", (), {"choices": [type("C", (), {"message": message})()]})()


class FakeFacade:
    def __init__(self, hits: list[tuple[EpisodicQuoteMemory, float]] | None = None) -> None:
        self.written: list[tuple[EpisodicQuoteMemory, str]] = []
        self.hits = hits or []

    def put_episodic(self, memory: EpisodicQuoteMemory, customer_id: str, _embedding: Any) -> None:
        self.written.append((memory, customer_id))

    def search_episodic(
        self, _customer_id: str, _vector: Any, top_k: int = 5
    ) -> list[tuple[EpisodicQuoteMemory, float]]:
        return self.hits[:top_k]


def _memory(
    *, number: str, outcome: Outcome, importance: float, age_days: float, words: int = 10
) -> EpisodicQuoteMemory:
    text = " ".join(["từ"] * words)
    return EpisodicQuoteMemory(
        memory_id=f"mem-{number}",
        quote_number=number,
        summary=BilingualText(vi=text, en=text),
        outcome=outcome,
        importance=importance,
        created_at=NOW - timedelta(days=age_days),
    )


# --- FR-044: the write ---
def test_an_approval_is_remembered_with_its_importance() -> None:
    facade = FakeFacade()
    memory = write_episode(
        facade=facade,  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        quote=_result(1).quote,  # type: ignore[arg-type]
        customer_id="cust_thanhcong",
        outcome=Outcome.APPROVED,
        now=NOW,
        chat_client=FakeChat('{"vi": "Đã duyệt", "en": "Approved"}'),
        embed_client=FakeEmbed(),
    )
    assert facade.written[0][1] == "cust_thanhcong"
    assert memory.outcome is Outcome.APPROVED
    assert memory.summary.vi == "Đã duyệt"  # diacritics intact through the whole path
    assert memory.importance == 0.7  # FR-046 base for an approval


def test_a_rejection_is_the_most_important_thing_to_remember() -> None:
    facade = FakeFacade()
    memory = write_episode(
        facade=facade,  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        quote=_result(1).quote,  # type: ignore[arg-type]
        customer_id="c1",
        outcome=Outcome.REJECTED,
        human_edits="too expensive",
        now=NOW,
        chat_client=FakeChat('{"vi": "Từ chối", "en": "Rejected"}'),
        embed_client=FakeEmbed(),
    )
    assert memory.importance == 0.9  # a rejection outranks an approval, per FR-046
    assert memory.human_edits == "too expensive"


def test_a_broken_summariser_does_not_lose_the_episode() -> None:
    # Losing the memory because the model returned prose instead of JSON would be the worst of both:
    # we pay for the call and remember nothing.
    facade = FakeFacade()
    memory = write_episode(
        facade=facade,  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        quote=_result(1).quote,  # type: ignore[arg-type]
        customer_id="c1",
        outcome=Outcome.APPROVED,
        now=NOW,
        chat_client=FakeChat("I'm sorry, I can't do that"),
        embed_client=FakeEmbed(),
    )
    assert len(facade.written) == 1
    assert "Quyết định: approved" in memory.summary.vi  # the deterministic fallback


def test_the_summary_falls_back_rather_than_raising() -> None:
    quote = _result(1).quote
    assert quote is not None
    summary = summarize(
        quote,
        Outcome.APPROVED,
        None,
        _Settings(),  # type: ignore[arg-type]
        client=FakeChat("not json"),
    )
    assert summary.vi and summary.en


# --- FR-045/046: the recall ---
def test_recall_ranks_on_effective_score_not_on_similarity() -> None:
    # The bug this guards: a perfectly-matched, year-old, low-importance episode outranking last
    # week's rejection. Similarity alone would put `old` first. Effective score must not.
    old = _memory(number="QM-2025-0001", outcome=Outcome.APPROVED, importance=0.7, age_days=365)
    recent = _memory(number="QM-2026-0009", outcome=Outcome.REJECTED, importance=0.9, age_days=3)
    facade = FakeFacade([(old, 0.95), (recent, 0.60)])

    recalls, _ = recall_episodes(
        facade=facade,  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        customer_id="c1",
        query_text="laptop",
        now=NOW,
        embed_client=FakeEmbed(),
    )
    assert [r.quote_number for r in recalls] == ["QM-2026-0009", "QM-2025-0001"]
    assert recalls[0].effective_score > recalls[1].effective_score


def test_recall_returns_at_most_three() -> None:
    hits = [
        (
            _memory(
                number=f"QM-2026-{i:04d}",
                outcome=Outcome.APPROVED,
                importance=0.8,
                age_days=i,
            ),
            0.9,
        )
        for i in range(1, 8)
    ]
    recalls, _ = recall_episodes(
        facade=FakeFacade(hits),  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        customer_id="c1",
        query_text="laptop",
        now=NOW,
        embed_client=FakeEmbed(),
    )
    assert len(recalls) == 3  # FR-045


def test_recall_carries_every_term_of_its_own_ranking() -> None:
    # A reviewer must be able to see *why* a memory surfaced, not just that it did.
    hit = _memory(number="QM-2026-0001", outcome=Outcome.REJECTED, importance=0.9, age_days=90)
    recalls, _ = recall_episodes(
        facade=FakeFacade([(hit, 0.8)]),  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        customer_id="c1",
        query_text="laptop",
        now=NOW,
        embed_client=FakeEmbed(),
    )
    recall = recalls[0]
    assert recall.similarity == 0.8
    assert recall.importance == 0.9
    assert abs(recall.recency_decay - 0.5) < 1e-9  # 90 days is exactly one half-life
    assert abs(recall.effective_score - 0.8 * 0.5 * 0.9) < 1e-9


def test_the_token_budget_drops_the_weakest_memories_and_says_so() -> None:
    # FR-049: a 1200-token budget. Each of these summaries costs ~600 tokens, so only two fit -
    # and it must be the two with the highest effective score, not the first two the store returned.
    hits = [
        (
            _memory(
                number=f"QM-2026-{i:04d}",
                outcome=Outcome.APPROVED,
                importance=0.9 - i / 100,
                age_days=1,
                words=400,
            ),
            0.9,
        )
        for i in range(1, 6)
    ]
    recalls, truncated = recall_episodes(
        facade=FakeFacade(hits),  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        customer_id="c1",
        query_text="laptop",
        now=NOW,
        embed_client=FakeEmbed(),
    )
    assert truncated is True
    assert 0 < len(recalls) < 5
    # What survived is the highest-scoring, not the first one the store happened to return.
    assert recalls[0].quote_number == "QM-2026-0001"


def test_no_memories_is_not_an_error() -> None:
    recalls, truncated = recall_episodes(
        facade=FakeFacade([]),  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        customer_id="brand-new-customer",
        query_text="laptop",
        now=NOW,
        embed_client=FakeEmbed(),
    )
    assert recalls == []
    assert truncated is False
