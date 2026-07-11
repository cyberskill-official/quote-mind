"""FR-048: procedural memory - the terms a quote carries, retrieved rather than hardcoded.

Three kinds of memory meet in one quote, and it is worth naming which is which:

  * **procedural** (this file) - what the business always does. Payment terms, delivery norms,
    warranty language. Retrieved from the `sop` tenant, per topic, by what is being quoted.
  * **episodic** (memory/recall.py) - what happened last time, with *this* customer.
  * **semantic** (the catalog) - what the products are.

Until now the terms were a module-level constant, so every quote said "delivery within 7 working
days" - including a quote for a made-to-order server with a six-week manufacturer lead time. That
is not a formatting problem. It is a promise the business cannot keep, printed on a document a
customer is invoiced from.

The retrieval is per *topic*, not global: a single top-k over the whole tenant would happily return
three payment snippets and no warranty. So each of payment / delivery / warranty gets its own
search, seeded with a query built from the quote's own line descriptions, and the best hit wins.
A topic that retrieves nothing falls back to the seeded default for that topic, because a quote
with no payment terms is worse than a quote with generic ones.

Like episodic recall, this touches the *words* and never the numbers.
"""

from __future__ import annotations

from ..config.settings import Settings
from ..models import BilingualText, QuoteTerms, RFQExtraction, SOPSnippet, SopTopic
from .embedding import embed_text
from .store import MemoryFacade

# One search per topic; the best hit is used. 4 is enough to see past a near-duplicate.
TOP_K = 4

# Retrieval is an aid. If the sop tenant is empty (a fresh tenant, an un-seeded environment), the
# quote still has to carry terms - so these are the same sentences seed/sop.py writes.
FALLBACK: dict[SopTopic, BilingualText] = {
    SopTopic.PAYMENT: BilingualText(
        vi="Thanh toán 100% trong vòng 30 ngày kể từ ngày nhận hàng, bằng chuyển khoản.",
        en="100% payment within 30 days of delivery, by bank transfer.",
    ),
    SopTopic.DELIVERY: BilingualText(
        vi="Giao hàng trong vòng 7 ngày làm việc đối với các mặt hàng có sẵn trong kho.",
        en="Delivery within 7 working days for items held in stock.",
    ),
    SopTopic.WARRANTY: BilingualText(
        vi="Bảo hành chính hãng 12 tháng.",
        en="12 months manufacturer warranty.",
    ),
}


def _query(extraction: RFQExtraction, topic: SopTopic) -> str:
    """What this quote is about, as a query - the topic word plus the goods being quoted.

    The topic word is in the query on purpose. The snippets are indexed on their own text, so
    "bảo hành / warranty" pulls the warranty snippets toward the top, and the line descriptions then
    decide *which* warranty snippet - the 36-month enterprise one for a server, the vendor-support
    one for a licence.
    """
    goods = " ".join(line.description_normalized for line in extraction.lines[:8])
    return f"{topic.value} {goods}".strip()


def retrieve_terms(
    *,
    facade: MemoryFacade,
    settings: Settings,
    extraction: RFQExtraction,
) -> tuple[QuoteTerms, list[str]]:
    """FR-048: the payment, delivery and warranty terms this quote should carry.

    Returns the terms and the ids of the snippets that produced them, so the trace can show a
    reviewer *which* SOP was applied - a term that appears from nowhere is a term nobody trusts.
    """
    chosen: dict[SopTopic, BilingualText] = {}
    applied: list[str] = []

    for topic in (SopTopic.PAYMENT, SopTopic.DELIVERY, SopTopic.WARRANTY):
        hits: list[tuple[SOPSnippet, float]] = []
        try:
            vector = embed_text(_query(extraction, topic), settings)
            hits = [hit for hit in facade.search_sop(vector, top_k=TOP_K) if hit[0].topic == topic]
        except Exception:  # noqa: BLE001 - SOP retrieval is an aid, never a dependency
            hits = []

        if hits:
            snippet, score = hits[0]
            chosen[topic] = snippet.text
            applied.append(f"{topic.value}@{score:.2f}")
        else:
            chosen[topic] = FALLBACK[topic]
            applied.append(f"{topic.value}=default")

    return (
        QuoteTerms(
            payment=chosen[SopTopic.PAYMENT],
            delivery=chosen[SopTopic.DELIVERY],
            warranty=chosen[SopTopic.WARRANTY],
        ),
        applied,
    )
