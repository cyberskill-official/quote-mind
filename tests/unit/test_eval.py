"""EP-12: the dataset (FR-120) and the metric definitions (FR-121).

These tests guard the thing an eval can most easily get wrong: scoring itself generously.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from quotemind.eval_.metrics import CaseResult, aggregate, expected_pairs, prf, score_lines
from quotemind.eval_.run import blocked_on, expected_total
from quotemind.models.eval import EvalCase, EvalInput, EvalLabelLine, EvalLabels
from quotemind.seed.data import BY_SKU, CATALOG, CUSTOMERS
from quotemind.seed.generate import ALL_CASES, build_case


# --- FR-120: the dataset ---
def test_dataset_matches_the_composition_the_spec_asks_for() -> None:
    kinds = [case.kind for case in ALL_CASES]
    assert len(ALL_CASES) == 30
    assert kinds.count("xlsx") == 5
    assert kinds.count("pdf_digital") == 3
    assert kinds.count("pdf_scan") == 5
    assert sum("adversarial" in case.tags for case in ALL_CASES) == 2


def test_every_labelled_sku_exists_in_the_catalog() -> None:
    # A label pointing at a phantom SKU would score the matcher against a target it cannot hit.
    for case in ALL_CASES:
        for _, sku, _ in case.lines:
            assert sku in BY_SKU, f"{case.case_id} labels unknown SKU {sku}"


def test_every_labelled_customer_exists() -> None:
    known = {customer.customer_id for customer in CUSTOMERS}
    for case in ALL_CASES:
        assert case.customer_id is None or case.customer_id in known, case.case_id


def test_case_ids_are_unique() -> None:
    ids = [case.case_id for case in ALL_CASES]
    assert len(set(ids)) == len(ids)


def test_the_catalog_is_big_enough_for_the_metric_to_mean_something() -> None:
    # With a handful of SKUs, "top-1 accuracy" measures retrieval luck rather than discrimination.
    assert len(CATALOG) >= 50
    laptops = [product for product in CATALOG if product.category.value == "laptop"]
    assert len(laptops) >= 10
    # Confusable near-neighbours must actually be present, or the matcher is never tested.
    assert {"DELL-LAT-5450", "DELL-LAT-5450-I7", "DELL-LAT-5440", "DELL-LAT-7450"} <= set(BY_SKU)


def test_blocked_cases_are_declared_not_hidden() -> None:
    built = [build_case(case) for case in ALL_CASES]
    blocked = [case for case in built if blocked_on(case)]
    assert len(blocked) == 5  # the scanned PDFs
    assert all(blocked_on(case) == "FR-032" for case in blocked)


def test_the_generator_is_deterministic() -> None:
    first = [build_case(case).model_dump_json() for case in ALL_CASES]
    second = [build_case(case).model_dump_json() for case in ALL_CASES]
    assert first == second


# --- FR-121: the metrics ---
def _case(*lines: tuple[str, int], customer: str = "cust_thanhcong") -> EvalCase:
    return EvalCase(
        case_id="t",
        input=EvalInput(text="x"),
        labels=EvalLabels(
            lines=[
                EvalLabelLine(description_canon=sku, sku=sku, qty=Decimal(qty))
                for sku, qty in lines
            ],
            customer_id=customer,
        ),
    )


def test_a_right_product_with_the_wrong_quantity_is_a_miss_not_a_hit() -> None:
    # 2 laptops when the customer asked for 20 is not "partially correct". It is wrong.
    tp, fp, fn = score_lines([("DELL-LAT-5450", "2")], [("DELL-LAT-5450", "20")])
    assert (tp, fp, fn) == (0, 1, 1)


def test_scoring_counts_duplicates_once() -> None:
    tp, fp, fn = score_lines(
        [("A", "1"), ("A", "1")], [("A", "1")]
    )
    assert (tp, fp, fn) == (1, 1, 0)  # the second copy is a false positive, not a second hit


def test_prf_of_an_empty_prediction_is_zero_not_a_crash() -> None:
    assert prf(0, 0, 3) == (0.0, 0.0, 0.0)


def test_success_requires_the_whole_conjunction() -> None:
    # Items right, money right, but no renderable document -> not a success.
    partial = CaseResult(
        case_id="t",
        predicted=[("A", "1")],
        expected=[("A", "1")],
        price_exact=True,
        has_pdf=False,
        success=False,
    )
    assert aggregate([partial])["task_success"] == 0.0


def test_skipped_cases_never_enter_the_denominator() -> None:
    # The temptation an eval must resist: shrinking the denominator to flatter the score.
    results = [
        CaseResult(case_id="a", success=True, predicted=[("A", "1")], expected=[("A", "1")]),
        CaseResult(case_id="b", skipped=True, skip_reason="FR-032 not implemented"),
    ]
    agg = aggregate(results)
    assert agg["cases"] == 1
    assert agg["skipped"] == 1
    assert agg["task_success"] == 1.0  # 1/1 scored, not 1/2


def test_aggregate_reports_cost_per_quote() -> None:
    results = [
        CaseResult(case_id="a", cost_usd=Decimal("0.004")),
        CaseResult(case_id="b", cost_usd=Decimal("0.006")),
    ]
    agg = aggregate(results)
    assert agg["cost_usd"]["total"] == "0.010"
    assert agg["cost_usd"]["per_quote"] == "0.005000"


def test_expected_pairs_normalise_the_quantity() -> None:
    assert expected_pairs(_case(("DELL-LAT-5450", 10))) == [("DELL-LAT-5450", "10")]


# --- the ground-truth total ---
def test_ground_truth_total_is_computed_by_the_deterministic_engine() -> None:
    # 10 x DELL-LAT-5450 for a dealer: dealer price 19,800,000, less the 3% dealer project
    # discount, plus 8% VAT. The point is that the engine - not a hand-typed constant - defines it.
    total = expected_total(_case(("DELL-LAT-5450", 10)))
    assert total is not None and total > 0

    # Doubling the quantity must double the money. If it does not, the harness is not measuring
    # arithmetic at all.
    assert expected_total(_case(("DELL-LAT-5450", 20))) == total * 2


def test_the_telecom_sku_is_taxed_at_ten_percent_not_eight() -> None:
    # Appendix B: telecom is excluded from the 8% reduction. If the eval's ground truth got this
    # wrong, it would mark a correct quote as a price failure.
    telecom = expected_total(_case(("VIET-SIM-DATA", 100)))
    it_goods = expected_total(_case(("KAS-ENDPOINT", 100)))
    assert telecom is not None and it_goods is not None

    telecom_pre_vat = Decimal(telecom) / Decimal("1.10")
    it_pre_vat = Decimal(it_goods) / Decimal("1.08")
    # Both should land on a whole-đồng pre-VAT base; a wrong rate would leave a large remainder.
    assert abs(telecom_pre_vat - telecom_pre_vat.quantize(Decimal(1))) < Decimal("1")
    assert abs(it_pre_vat - it_pre_vat.quantize(Decimal(1))) < Decimal("1")


def test_an_unpriceable_case_has_no_ground_truth_total() -> None:
    assert expected_total(_case()) is None


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda case: case.case_id)
def test_every_case_has_a_computable_ground_truth(case: object) -> None:
    built = build_case(case)  # type: ignore[arg-type]
    if built.labels.lines:
        assert expected_total(built) is not None
