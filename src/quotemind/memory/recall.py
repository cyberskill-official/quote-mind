"""TASK-044/045: writing an episode when a human decides, and recalling episodes before drafting.

`episodic.py` next to this file holds the pure scoring - importance, recency decay, effective score.
It has been correct and tested since PR-4, and it has also, until now, been dead: nothing called it.
This module is the wiring.

**What memory is allowed to touch, and what it is not.** A recalled episode never reaches the money.
Prices are computed by `pricing/` from the catalog in exact Decimal dong, and the critic recomputes
them independently; a retrieved document that could nudge a number would put a similarity search
inside the arithmetic path, which is the one thing this whole architecture exists to prevent. So
recall feeds the *reviewer*: the memories, their scores, and the reasons they ranked where they did
are attached to the quote and rendered beside it, and every one of them is recorded in the trace.

That is a deliberate divergence from TASK-045's literal wording, which says to inject the memories
into "the drafter context". There is no LLM drafter to inject into - the quote is assembled
deterministically - and inventing one so a memory could influence a price would be a strictly worse
system. The retrieval, the ranking, the 1200-token budget and the trace record are all exactly as
specified; what the memories inform is the human, not the total.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI

from ..config.models import MODEL_DRAFTER
from ..config.settings import Settings
from ..models import (
    BilingualText,
    EpisodicQuoteMemory,
    EpisodicRecall,
    ItemBrief,
    Outcome,
    Quote,
    new_ulid,
)
from ..obs.log import log_event
from .budget import EPISODIC_TOKEN_BUDGET, budget_trim, estimate_tokens
from .embedding import embed_text
from .episodic import age_in_days, effective_score, initial_importance, recency_decay
from .store import MemoryFacade

TOP_K = 3  # TASK-045: top-3 episodic memories for the resolved customer
_SEARCH_K = 10  # over-fetch, because the vector store ranks on similarity alone and we re-rank

SUMMARY_SYS = """Bạn tóm tắt một báo giá đã được con người quyết định, để lần sau nhớ lại.

Trả về JSON, không có gì khác:
{"vi": "...", "en": "..."}

Mỗi bản tóm tắt tối đa 120 từ. Nêu: khách hàng cần gì, ta chào giá bao nhiêu, con người quyết định
thế nào và vì sao (nếu biết). Nêu sự thật, không suy đoán. Giữ nguyên dấu tiếng Việt."""


def _summary_text(quote: Quote, outcome: Outcome, human_edits: str | None) -> str:
    lines = "; ".join(
        f"{line.qty} x {line.sku or line.description.vi} @ {line.unit_price_vnd}"
        for line in quote.lines
    )
    parts = [
        f"Khách: {quote.customer_block.get('name', 'không rõ')}",
        f"Hàng: {lines}",
        f"Tổng: {quote.total_vnd} VND",
        f"Quyết định: {outcome.value}",
    ]
    if human_edits:
        parts.append(f"Ghi chú của người duyệt: {human_edits}")
    return "\n".join(parts)


def summarize(
    quote: Quote,
    outcome: Outcome,
    human_edits: str | None,
    settings: Settings,
    *,
    client: Any | None = None,
) -> BilingualText:
    """TASK-044: a bilingual summary of the episode, at most 120 words per language.

    Falls back to a deterministic summary if the model does not return usable JSON. A memory that
    fails to write is a memory that is silently never recalled, and losing the episode entirely
    because the summariser had a bad day would be the worst of both.
    """
    import json  # noqa: PLC0415 - local: only this fallback path needs it

    text = _summary_text(quote, outcome, human_edits)
    try:
        chat = client or OpenAI(
            api_key=settings.dashscope_api_key, base_url=settings.dashscope_base_url
        )
        response = chat.chat.completions.create(
            model=MODEL_DRAFTER,
            messages=[
                {"role": "system", "content": SUMMARY_SYS},
                {"role": "user", "content": text},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].removeprefix("json").strip()
        parsed = json.loads(raw)
        return BilingualText(vi=str(parsed["vi"]), en=str(parsed["en"]))
    except Exception as exc:  # noqa: BLE001 - never lose the episode over a summariser hiccup
        log_event(
            "episodic_summary_fallback",
            level=logging.WARNING,
            error=f"{type(exc).__name__}: {exc}",
        )
        return BilingualText(vi=text, en=text)


def write_episode(
    *,
    facade: MemoryFacade,
    settings: Settings,
    quote: Quote,
    customer_id: str,
    outcome: Outcome,
    human_edits: str | None = None,
    now: datetime | None = None,
    chat_client: Any | None = None,
    embed_client: Any | None = None,
) -> EpisodicQuoteMemory:
    """TASK-044: on approval or rejection, remember what happened and how the human decided."""
    summary = summarize(quote, outcome, human_edits, settings, client=chat_client)
    memory = EpisodicQuoteMemory(
        memory_id=new_ulid(),
        quote_number=quote.quote_number,
        summary=summary,
        items_brief=[
            ItemBrief(sku=line.sku or "", qty=line.qty, unit_price=line.unit_price_vnd)
            for line in quote.lines
            if line.sku
        ],
        outcome=outcome,
        human_edits=human_edits,
        importance=initial_importance(outcome, quote.total_vnd),
        created_at=now or datetime.now(timezone.utc),
    )
    embedding = embed_text(f"{summary.vi} {summary.en}", settings, client=embed_client)
    facade.put_episodic(memory, customer_id, embedding)

    log_event(
        "episodic_written",
        quote_id=quote.quote_number,
        customer_id=customer_id,
        outcome=outcome.value,
        importance=memory.importance,
    )
    return memory


def recall_episodes(
    *,
    facade: MemoryFacade,
    settings: Settings,
    customer_id: str,
    query_text: str,
    now: datetime | None = None,
    top_k: int = TOP_K,
    embed_client: Any | None = None,
) -> tuple[list[EpisodicRecall], bool]:
    """TASK-045: the top-3 episodes for this customer, re-ranked and fitted to the token budget.

    The vector store ranks on similarity alone, so it is over-fetched and re-ranked here by the
    TASK-046 effective score - similarity x recency_decay x importance. Without that, a perfectly
    matched but year-old episode outranks last week's rejection, which is exactly backwards.

    Returns (recalls, truncated); `truncated` is True when the budget dropped something.
    """
    vector = embed_text(query_text, settings, client=embed_client)
    hits = facade.search_episodic(customer_id, vector, top_k=_SEARCH_K)

    recalls: list[tuple[EpisodicRecall, int, float]] = []
    for memory, similarity in hits:
        age = age_in_days(memory.created_at, now)
        recall = EpisodicRecall(
            memory_id=memory.memory_id,
            quote_number=memory.quote_number,
            summary=memory.summary,
            outcome=memory.outcome,
            similarity=similarity,
            importance=memory.importance,
            recency_decay=recency_decay(age),
            age_days=age,
            effective_score=effective_score(similarity, memory.importance, age),
        )
        tokens = estimate_tokens(f"{recall.summary.vi} {recall.summary.en}")
        recalls.append((recall, tokens, recall.effective_score))

    kept, truncated = budget_trim(recalls, max_tokens=EPISODIC_TOKEN_BUDGET)
    ranked = sorted(kept, key=lambda r: r.effective_score, reverse=True)[:top_k]
    return ranked, truncated


__all__ = ["TOP_K", "recall_episodes", "summarize", "write_episode"]
