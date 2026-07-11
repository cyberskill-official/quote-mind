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
from ..models import BilingualText, Category, QuoteTerms, RFQExtraction, SOPSnippet, SopTopic
from .embedding import embed_text
from .store import MemoryFacade

# The search is over the WHOLE tenant and the topic filter is applied afterwards, so top_k has to be
# large enough that the filter cannot starve. It was 4, and that was a bug: asked for the payment
# terms on a server, only one payment snippet survived into the top 4 - and it happened to be the
# wrong one, so it won by default. A filter applied after a truncation is a filter over a lottery.
TOP_K = 25

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


def _applicable(snippet: SOPSnippet, categories: set[Category]) -> bool:
    """FR-048: may this term be printed on a quote containing these goods?

    Retrieval proposes; this disposes. Vector similarity is a fine way to *rank* the terms that are
    allowed, and a terrible way to decide which are allowed at all - "software licences: 100% before
    activation" and "100% within 30 days of delivery" both talk about money and both say 100%, so
    they sit close together in the embedding, and the first one outranked the second on a quote for
    a Dell PowerEdge server. That is a payment obligation the customer never agreed to, printed on a
    document they get invoiced from.

    Whether a software payment term applies to a server is not a fuzzy question. The business knows.
    An empty `applies_to` means the term is universal, which is the common case.
    """
    return not snippet.applies_to or bool(set(snippet.applies_to) & categories)


def retrieve_terms(
    *,
    facade: MemoryFacade,
    settings: Settings,
    extraction: RFQExtraction,
    categories: set[Category] | None = None,
) -> tuple[QuoteTerms, list[str]]:
    """FR-048: the payment, delivery and warranty terms this quote should carry.

    `categories` are the catalog categories of the *matched* lines - so this runs after matching,
    not before. Passing nothing means "no goods resolved", and then only the universal terms apply,
    which is the safe direction: a term that says nothing specific is never wrong.

    Returns the terms and a note per topic saying where each came from, so the trace can show a
    reviewer *which* SOP was applied. A term that appears from nowhere is a term nobody trusts.
    """
    goods = categories or set()
    chosen: dict[SopTopic, BilingualText] = {}
    applied: list[str] = []

    for topic in (SopTopic.PAYMENT, SopTopic.DELIVERY, SopTopic.WARRANTY):
        hits: list[tuple[SOPSnippet, float]] = []
        try:
            vector = embed_text(_query(extraction, topic), settings)
            hits = [
                hit
                for hit in facade.search_sop(vector, top_k=TOP_K)
                if hit[0].topic == topic and _applicable(hit[0], goods)
            ]
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
