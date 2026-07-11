"""FR-034/FR-042: when the system refuses to quote, it has to say why.

Found by re-running the eval against the shipped code. `adv_002` asks for a "Dell Latitude 5450 RAM
64GB SSD 2TB" - a configuration the catalogue does not sell. The matcher is shown the closest thing
(an i7 with 32GB and 1TB), compares it to the request, and **refuses**:

    "None of the candidate SKUs meet the requested 64GB RAM and 2TB SSD specifications."

That is the right call. Quietly selling someone a 32GB machine when they asked for 64GB is not a
rounding error, it is a commercial one, and the whole design of this system is that it stops rather
than guesses.

And then it threw the reason away. The reviewer got "no quote was produced", full stop - so to find
out *what happened*, they had to re-read the customer's email and go through the catalogue by hand.
Which is the entire job the autopilot exists to do.

A refusal is a decision. It gets persisted like one.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal
from typing import Any

from quotemind.memory.quotes import PAYLOAD_COLUMNS
from quotemind.models import (
    BilingualText,
    Buyer,
    MatchAlternative,
    MatchResult,
    MatchStatus,
    RFQExtraction,
    RFQLine,
    Status,
)
from quotemind.orchestrator import PipelineResult
from quotemind.service import QuoteService

from .test_dispatch import FakeArtifacts
from .test_service import FakeStore, _Settings

_ON = date(2026, 7, 12)

# What the matcher actually produced for adv_002, live, against the deployed catalogue.
_REFUSAL = MatchResult(
    line_ref=1,
    status=MatchStatus.NO_MATCH,
    sku=None,
    match_confidence=0.0,
    alternatives=[
        MatchAlternative(
            sku="DELL-LAT-5450-I7",
            reason=BilingualText(vi="i7, 32GB, 1TB - thiếu RAM.", en="i7, 32GB, 1TB - RAM short."),
        ),
        MatchAlternative(
            sku="DELL-LAT-5450",
            reason=BilingualText(vi="i5, 16GB, 512GB.", en="i5, 16GB, 512GB."),
        ),
    ],
    reason=BilingualText(
        vi="Không có SKU nào trong danh sách ứng viên đáp ứng đủ RAM 64GB và SSD 2TB như yêu cầu.",
        en="None of the candidate SKUs meet the requested 64GB RAM and 2TB SSD specifications.",
    ),
)

_EXTRACTION = RFQExtraction(
    buyer=Buyer(company="An Phát", email="kinhdoanh@anphat.com.vn"),
    lines=[
        RFQLine(
            raw_text="10 laptop Dell Latitude 5450 RAM 64GB SSD 2TB",
            description_normalized="Laptop Dell Latitude 5450 RAM 64GB SSD 2TB",
            quantity=Decimal(10),
            unit="cái",
            unit_original="cái",
            confidence=0.95,
        )
    ],
)


def _refusing_service(store: FakeStore) -> QuoteService:
    async def pipeline(_text: str, **_kwargs: Any) -> PipelineResult:
        return PipelineResult(
            extraction=_EXTRACTION,
            matches=[_REFUSAL],
            clarification_reasons=["NO_LINE_ITEMS"],
        )

    return QuoteService(
        store=store,  # type: ignore[arg-type]
        facade=object(),  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        seller_block={"name": "CyberSkill JSC"},
        pipeline=pipeline,
        artifacts=FakeArtifacts(),
    )


def test_a_refusal_keeps_the_reason_it_refused_for() -> None:
    store = FakeStore()
    service = _refusing_service(store)

    record, _ = service.submit(text="10 laptop Dell Latitude 5450 RAM 64GB SSD 2TB", on_date=_ON)
    final = asyncio.run(service.process(record, "10 laptop...", on_date=_ON))
    assert final.status is Status.NEEDS_CLARIFICATION

    review = service.review(final.quote_id)

    # The reason the system refused, in both languages, on the record - not only in a trace.
    matches = review["matches"]
    assert matches[0]["status"] == "no_match"
    assert "64GB" in matches[0]["reason"]["en"]
    assert "64GB" in matches[0]["reason"]["vi"]

    # What the customer actually asked for, so the reviewer does not have to re-read the email.
    assert review["extraction"]["lines"][0]["quantity"] == "10"

    # And the near-misses, so they can decide whether to substitute by hand.
    assert [alt["sku"] for alt in matches[0]["alternatives"]] == [
        "DELL-LAT-5450-I7",
        "DELL-LAT-5450",
    ]


def test_the_refusal_reason_reaches_the_queue_not_just_the_detail_pane() -> None:
    """A reviewer scanning the queue should see that this one needs them, without opening it."""
    store = FakeStore()
    service = _refusing_service(store)

    record, _ = service.submit(text="10 laptop 64GB", on_date=_ON)
    final = asyncio.run(service.process(record, "10 laptop 64GB", on_date=_ON))

    assert final.flags == ["NO_LINE_ITEMS"]
    assert service.queue(status=Status.NEEDS_CLARIFICATION)[0].flags == ["NO_LINE_ITEMS"]


def test_matches_json_is_a_column_the_store_actually_persists() -> None:
    """The three-list drift bug, one more time, on the column this fix adds."""
    assert "matches_json" in PAYLOAD_COLUMNS


def test_a_refused_quote_can_still_be_revised() -> None:
    """The extraction is persisted on the refusal path too, so the reviewer can amend and re-run.

    Before this, a refusal wrote no extraction - so the one action a reviewer would obviously want
    to take ("they meant the 32GB one, quote that") had nothing to work from.
    """
    store = FakeStore()
    service = _refusing_service(store)

    record, _ = service.submit(text="10 laptop 64GB", on_date=_ON)
    final = asyncio.run(service.process(record, "10 laptop 64GB", on_date=_ON))

    stored = store.rows[final.quote_id]
    assert stored["extraction_json"]
    assert "64GB" in json.loads(stored["extraction_json"])["lines"][0]["description_normalized"]
