"""TASK-121 metrics.

The definitions are the whole argument, so they are written down rather than left implicit:

- **Line extraction P/R/F1** is scored on *(SKU, qty)* pairs, not on prose. A line that names the
  right product with the wrong quantity is wrong: a quote for 2 laptops when the customer asked for
  20 is not a partially-correct quote, it is a wrong quote.
- **SKU top-1 accuracy** is measured only over lines that were extracted at all. It answers "when
  the matcher had something to match, did it pick the right SKU", and is deliberately not penalised
  twice for an extraction miss (which P/R already counts).
- **Price exactness** is exact equality on the đồng, against a total recomputed from the true SKUs
  by the same deterministic engine. Approximately-right money is wrong money.
- **Task success** is the conjunction the spec asks for: right items ∧ right price ∧ a real PDF ∧ no
  blocking critic failure. Conjunctions are unforgiving, and that is the point - a system that gets
  the items right but the money wrong has not done the job.
- **Human-intervention rate** counts cases that could not be sent without a person editing them:
  needs_clarification, critic-blocked, or any unmatched line. A *lower* number is not automatically
  better - correctly asking for help on the adversarial cases is the right answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from ..models.eval import EvalCase


class CaseResult(BaseModel):
    """What one case produced. `skipped` cases are excluded from every aggregate."""

    case_id: str
    tags: list[str] = Field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None
    error: str | None = None

    predicted: list[tuple[str, str]] = Field(default_factory=list)  # (sku, qty) as strings
    expected: list[tuple[str, str]] = Field(default_factory=list)

    extracted_lines: int = 0
    sku_correct: int = 0
    sku_attempted: int = 0

    total_vnd: int | None = None
    expected_total_vnd: int | None = None
    price_exact: bool = False

    has_pdf: bool = False
    blocking_flags: list[str] = Field(default_factory=list)
    needs_human: bool = False
    success: bool = False

    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Decimal = Decimal("0")


def score_lines(
    predicted: Sequence[tuple[str, str]], expected: Sequence[tuple[str, str]]
) -> tuple[int, int, int]:
    """True positives, false positives, false negatives on exact (sku, qty) pairs."""
    remaining = list(expected)
    true_positive = 0
    for pair in predicted:
        if pair in remaining:
            remaining.remove(pair)
            true_positive += 1
    return true_positive, len(predicted) - true_positive, len(remaining)


def score_skus(
    predicted: Sequence[tuple[str, str]], expected: Sequence[tuple[str, str]]
) -> tuple[int, int]:
    """(correct, attempted) for top-1 SKU accuracy, ignoring quantity.

    Attempted is capped at the number of expected lines, so a run cannot inflate its own denominator
    by hallucinating extra lines - those are already punished by precision.
    """
    expected_skus = [sku for sku, _ in expected]
    predicted_skus = [sku for sku, _ in predicted]
    attempted = min(len(predicted_skus), len(expected_skus))
    remaining = list(expected_skus)
    correct = 0
    for sku in predicted_skus[:attempted]:
        if sku in remaining:
            remaining.remove(sku)
            correct += 1
    return correct, attempted


def prf(true_positive: int, false_positive: int, false_negative: int) -> tuple[float, float, float]:
    """Precision, recall, F1. An empty prediction scores 0, not a division by zero."""
    predicted = true_positive + false_positive
    actual = true_positive + false_negative
    precision = true_positive / predicted if predicted else 0.0
    recall = true_positive / actual if actual else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(int(fraction * len(ordered)), len(ordered) - 1)
    return ordered[index]


def aggregate(results: list[CaseResult]) -> dict[str, Any]:
    """Roll per-case results into the report. Skipped cases never enter the denominator."""
    scored = [result for result in results if not result.skipped]
    skipped = [result for result in results if result.skipped]
    if not scored:
        return {"cases": 0, "skipped": len(skipped)}

    true_positive = false_positive = false_negative = 0
    for result in scored:
        tp, fp, fn = score_lines(result.predicted, result.expected)
        true_positive += tp
        false_positive += fp
        false_negative += fn
    precision, recall, f1 = prf(true_positive, false_positive, false_negative)

    sku_attempted = sum(result.sku_attempted for result in scored)
    sku_correct = sum(result.sku_correct for result in scored)
    latencies = [result.latency_ms for result in scored]
    priced = [result for result in scored if result.expected_total_vnd is not None]

    return {
        "cases": len(scored),
        "skipped": len(skipped),
        "line_extraction": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "tp": true_positive,
            "fp": false_positive,
            "fn": false_negative,
        },
        "sku_top1_accuracy": round(sku_correct / sku_attempted, 4) if sku_attempted else 0.0,
        "price_exactness": (
            round(sum(result.price_exact for result in priced) / len(priced), 4) if priced else 0.0
        ),
        "task_success": round(sum(result.success for result in scored) / len(scored), 4),
        "human_intervention_rate": round(
            sum(result.needs_human for result in scored) / len(scored), 4
        ),
        "errors": sum(result.error is not None for result in scored),
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
        },
        "tokens": {
            "in": sum(result.tokens_in for result in scored),
            "out": sum(result.tokens_out for result in scored),
        },
        "cost_usd": {
            "total": str(sum((result.cost_usd for result in scored), Decimal(0))),
            "per_quote": str(
                (sum((result.cost_usd for result in scored), Decimal(0)) / len(scored)).quantize(
                    Decimal("0.000001")
                )
            ),
        },
    }


def expected_pairs(case: EvalCase) -> list[tuple[str, str]]:
    """Ground truth as (sku, qty) strings - Decimal('10') and Decimal('10.0') must not differ."""
    return [(line.sku, str(int(line.qty))) for line in case.labels.lines]
