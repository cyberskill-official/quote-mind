"""FR-123: the CI smoke eval.

Replays 5 recorded cases (eval/dataset/cassettes/) through the real pipeline with the models stubbed
out, and asserts that extraction and pricing have not regressed. No API key, no cost, no network.

The thresholds are exact, not approximate. Everything downstream of the model in this system is
deterministic - fusion, the SKU whitelist, assembly, VAT, the critic's recompute - so given the same
recorded model output it must produce the same quote to the đồng, every time. A "close enough"
threshold here would be an invitation for the money to drift.

The two adversarial cases are scored differently, and deliberately so. Their correct outcome is
*not* a priced quote - it is a refusal. adv_001 asks for a product that is not in the catalog;
adv_002 asks for a 64GB Latitude 5450 when the catalog tops out at 32GB, and the recorded run shows
the model reaching for a SKU outside the candidate list, which the whitelist then refused. Folding
those into a precision/recall average would reward the system for guessing. So they get their own
assertion: they must escalate, and they must not invent a price.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from quotemind import orchestrator
from quotemind.config.seller import SELLER_BLOCK
from quotemind.eval_.cassette import Cassette, available
from quotemind.eval_.metrics import CaseResult, aggregate, expected_pairs, score_skus
from quotemind.eval_.run import expected_total, load_cases
from quotemind.models import CatalogProduct
from quotemind.seed.data import BY_SKU, CUSTOMERS

BY_CUSTOMER = {customer.customer_id: customer for customer in CUSTOMERS}
_EMAIL = {
    customer.customer_id: (customer.emails[0] if customer.emails else "")
    for customer in CUSTOMERS
}

pytestmark = pytest.mark.skipif(not available(), reason="no cassettes recorded")


class _Settings:
    """Just the fields the deterministic half of the pipeline reads."""

    quote_validity_days = 14
    margin_floor_pct = 5
    fx_usd_vnd = 25_400
    trace_content = False


class _Facade:
    """Retrieval replayed from the cassette: the same candidates the live run actually saw.

    The customer is replayed too. It has to be: the tier decides which price column the engine
    reads, so a stub that resolved no customer would quietly price everything at end-customer list
    and the smoke eval would 'fail' on a pipeline that is working perfectly.
    """

    def __init__(self, cassette: Cassette, customer_id: str | None) -> None:
        self.cassette = cassette
        self.customer = BY_CUSTOMER.get(customer_id or "")
        self.line = 0

    def _products(self, skus: list[str]) -> list[tuple[CatalogProduct, float]]:
        return [(BY_SKU[sku], 1.0) for sku in skus if sku in BY_SKU]

    def search_catalog_vector(self, _vector: Any, top_k: int = 8) -> list[Any]:
        record = self.cassette.lines[min(self.line, len(self.cassette.lines) - 1)]
        return self._products(record.vector_skus)[:top_k]

    def search_catalog_text(self, _text: str, limit: int = 8) -> list[Any]:
        record = self.cassette.lines[min(self.line, len(self.cassette.lines) - 1)]
        return self._products(record.text_skus)[:limit]

    def search_customers_text(self, _text: str, limit: int = 5) -> list[Any]:
        return [(self.customer, 1.0)] if self.customer else []


def _install(monkeypatch: pytest.MonkeyPatch, cassette: Cassette, facade: _Facade) -> None:
    async def fake_extract(_text: str, _settings: Any, **_kwargs: Any) -> Any:
        return cassette.extraction

    async def fake_select(
        _description: str, _candidates: list[CatalogProduct], _settings: Any, **_kwargs: Any
    ) -> Any:
        record = cassette.lines[min(facade.line, len(cassette.lines) - 1)]
        facade.line += 1
        return record.selection

    monkeypatch.setattr(orchestrator, "extract_text_rfq", fake_extract)
    monkeypatch.setattr(orchestrator, "select_sku", fake_select)
    monkeypatch.setattr(orchestrator, "embed_text", lambda *_a, **_k: [0.0] * 1024)


def _run(case_id: str, monkeypatch: pytest.MonkeyPatch) -> CaseResult:
    case = {item.case_id: item for item in load_cases()}[case_id]
    cassette = Cassette.load(case_id)
    facade = _Facade(cassette, case.labels.customer_id)
    _install(monkeypatch, cassette, facade)

    result = orchestrator.quote_from_text(
        case.input.text or "",
        settings=_Settings(),  # type: ignore[arg-type]
        facade=facade,  # type: ignore[arg-type]
        seller_block=SELLER_BLOCK,
        sequence=1,
        customer_email=_EMAIL.get(case.labels.customer_id or ""),
    )
    pipeline = asyncio.run(result)

    predicted = (
        [(line.sku, str(int(line.qty))) for line in pipeline.quote.lines if line.sku]
        if pipeline.quote
        else []
    )
    expected = expected_pairs(case)
    correct, attempted = score_skus(predicted, expected)
    return CaseResult(
        case_id=case_id,
        predicted=predicted,
        expected=expected,
        sku_correct=correct,
        sku_attempted=attempted,
        total_vnd=int(pipeline.quote.total_vnd) if pipeline.quote else None,
        expected_total_vnd=expected_total(case),
        price_exact=(
            pipeline.quote is not None
            and expected_total(case) is not None
            and int(pipeline.quote.total_vnd) == expected_total(case)
        ),
        has_pdf=pipeline.html is not None,
        blocking_flags=list(pipeline.critic.blocking) if pipeline.critic else [],
        success=False,
    )


ADVERSARIAL = ["adv_001", "adv_002"]
NORMAL = [case_id for case_id in available() if case_id not in ADVERSARIAL]


@pytest.mark.parametrize("case_id", NORMAL)
def test_replayed_case_prices_to_the_dong(case_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(case_id, monkeypatch)
    assert result.total_vnd == result.expected_total_vnd, (
        f"{case_id}: the deterministic path produced {result.total_vnd}, "
        f"the engine says {result.expected_total_vnd}"
    )


def test_smoke_eval_meets_its_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    results = [_run(case_id, monkeypatch) for case_id in NORMAL]
    agg = aggregate(results)

    assert agg["cases"] == len(NORMAL)
    assert agg["line_extraction"]["f1"] == 1.0  # recorded output -> the same lines, every time
    assert agg["price_exactness"] == 1.0  # and the same money, to the đồng
    assert agg["sku_top1_accuracy"] == 1.0


def test_the_out_of_catalog_line_is_refused_not_substituted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # adv_001 asks for a Wacom tablet the catalog does not carry, alongside a laptop it does.
    # The laptop must be priced; the tablet must not be quietly swapped for something plausible.
    result = _run("adv_001", monkeypatch)
    assert result.predicted == [("DELL-LAT-5450", "2")]
    assert result.total_vnd == result.expected_total_vnd  # and the rest still prices exactly


def test_the_spec_conflict_escalates_instead_of_inventing_a_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # adv_002 asks for a 64GB Latitude 5450. No such machine exists. On the recorded run the model
    # reached for a SKU that was not among its candidates and the whitelist refused it, so no quote
    # is produced and a human is asked. Quoting a 32GB laptop against a 64GB request would be the
    # failure mode that matters - the customer would only find out on delivery.
    result = _run("adv_002", monkeypatch)
    assert result.predicted == []
    assert result.total_vnd is None
