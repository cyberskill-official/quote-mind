"""TASK-121/122: the metrics runner.

    python -m quotemind.eval_.run --mode pipeline
    python -m quotemind.eval_.run --mode baseline
    python -m quotemind.eval_.run --mode both --limit 5

Writes eval/reports/{ts}_{mode}.json plus a markdown summary. In `both` mode it prints the headline
the hackathon actually asks for: the success-rate delta between the multi-agent pipeline and the
single-agent baseline, measured on identical inputs with identical models.

Ground-truth totals are recomputed here from the labelled SKUs using the *same* deterministic
pricing engine the pipeline uses. That is deliberate and worth being explicit about: the engine is
unit-tested to 100% branch coverage and is the definition of a correct price in this system, so
"price exactness" asks whether a run reproduced the arithmetic the engine would have done from the
right SKUs. It does not let the pipeline mark its own homework, because the pipeline can still pick
the wrong SKUs, drop a line, or get the quantity wrong - all of which this catches.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ..config.models import MODEL_PLANNER
from ..config.seller import SELLER_BLOCK
from ..config.settings import Settings, require_settings
from ..memory.store import MemoryFacade
from ..models import LineSource, Tier
from ..models.eval import EvalCase
from ..obs.trace import Tracer
from ..orchestrator import (
    DEFAULT_NOTES,
    DEFAULT_TERMS,
    PipelineResult,
    quote_from_excel,
    quote_from_pdf,
    quote_from_text,
)
from ..quote import AssemblyLine, assemble_quote, format_quote_number
from ..seed.data import BY_SKU, CUSTOMERS
from .baseline import baseline_quote
from .metrics import CaseResult, aggregate, expected_pairs, score_skus

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "eval" / "dataset"
REPORTS = ROOT / "eval" / "reports"

_TIER_BY_CUSTOMER = {customer.customer_id: customer.tier for customer in CUSTOMERS}
_DISCOUNT_BY_CUSTOMER = {
    customer.customer_id: customer.project_discount_pct for customer in CUSTOMERS
}
_NAME_BY_CUSTOMER = {customer.customer_id: customer.name for customer in CUSTOMERS}
_EMAIL_BY_CUSTOMER = {
    customer.customer_id: (customer.emails[0] if customer.emails else None)
    for customer in CUSTOMERS
}


def load_cases(limit: int | None = None) -> list[EvalCase]:
    raw = json.loads((DATASET / "labels.json").read_text(encoding="utf-8"))
    cases = [EvalCase.model_validate(item) for item in raw]
    return cases[:limit] if limit else cases


def blocked_on(case: EvalCase) -> str | None:
    for tag in case.tags:
        if tag.startswith("blocked_on:"):
            return tag.split(":", 1)[1]
    return None


def expected_total(case: EvalCase) -> int | None:
    """The correct total for this case, computed by the deterministic engine from the true SKUs."""
    if not case.labels.lines:
        return None
    tier = _TIER_BY_CUSTOMER.get(case.labels.customer_id or "", Tier.END_CUSTOMER)
    discount = _DISCOUNT_BY_CUSTOMER.get(case.labels.customer_id or "", 3.0)
    quote = assemble_quote(
        quote_id="eval",
        quote_number=format_quote_number(2026, 1),
        seller_block=SELLER_BLOCK,
        customer_block={"name": case.labels.customer_id or "eval"},
        date="2026-07-11",
        validity_days=14,
        lines=[
            AssemblyLine(
                product=BY_SKU[line.sku],
                qty=line.qty,
                tier=tier,
                source=LineSource.MATCHED,
            )
            for line in case.labels.lines
        ],
        terms=DEFAULT_TERMS,
        notes=DEFAULT_NOTES,
        on_date=date(2026, 7, 11),
        project_discount_pct=discount,
    )
    return int(quote.total_vnd)


def _predicted_from_pipeline(result: PipelineResult) -> list[tuple[str, str]]:
    if result.quote is None:
        return []
    return [(line.sku, str(int(line.qty))) for line in result.quote.lines if line.sku]


async def _run_pipeline_case(
    case: EvalCase, settings: Settings, facade: MemoryFacade, sequence: int
) -> tuple[PipelineResult, Tracer]:
    tracer = Tracer(quote_id=case.case_id)
    customer_id = case.labels.customer_id or ""
    common: dict[str, Any] = {
        "settings": settings,
        "facade": facade,
        "seller_block": SELLER_BLOCK,
        "sequence": sequence,
        # A spreadsheet or PDF RFQ carries no sender inside the document - in the real world it
        # arrives attached to an email, and intake passes that envelope through (TASK-043). Feeding
        # the raw customer_id as a "hint" was wrong: resolve_customer matches on *name*, so file
        # cases silently fell through to END_CUSTOMER list pricing. The eval now supplies the
        # sender exactly as intake would.
        "customer_email": _EMAIL_BY_CUSTOMER.get(customer_id),
        "customer_hint": _NAME_BY_CUSTOMER.get(customer_id),
        "tracer": tracer,
    }
    if case.input.file and case.input.file.endswith(".xlsx"):
        data = (DATASET / case.input.file).read_bytes()
        return await quote_from_excel(data, **common), tracer
    if case.input.file and case.input.file.endswith(".pdf"):
        data = (DATASET / case.input.file).read_bytes()
        return await quote_from_pdf(data, **common), tracer
    return await quote_from_text(case.input.text or "", **common), tracer


async def run_case(
    case: EvalCase, mode: str, settings: Settings, facade: MemoryFacade, sequence: int
) -> CaseResult:
    """One case, one mode. An exception is a failed case, never a failed run."""
    reason = blocked_on(case)
    if reason:
        return CaseResult(
            case_id=case.case_id,
            tags=case.tags,
            skipped=True,
            skip_reason=f"{reason} not implemented",
        )

    expected = expected_pairs(case)
    result = CaseResult(
        case_id=case.case_id,
        tags=case.tags,
        expected=expected,
        expected_total_vnd=expected_total(case),
    )
    started = time.perf_counter()

    try:
        if mode == "pipeline":
            pipeline, tracer = await _run_pipeline_case(case, settings, facade, sequence)
            document = tracer.document()
            result.tokens_in = document.total_tokens_in
            result.tokens_out = document.total_tokens_out
            result.cost_usd = document.total_cost_usd
            result.predicted = _predicted_from_pipeline(pipeline)
            result.extracted_lines = len(pipeline.extraction.lines)
            result.blocking_flags = list(pipeline.critic.blocking) if pipeline.critic else []
            result.total_vnd = int(pipeline.quote.total_vnd) if pipeline.quote else None
            # The pipeline always renders HTML on the way to a PDF; a quote means a renderable doc.
            result.has_pdf = pipeline.html is not None
            unmatched = any(match.sku is None for match in pipeline.matches)
            result.needs_human = bool(
                pipeline.clarification_reasons or result.blocking_flags or unmatched
            )
        else:
            tracer = Tracer(quote_id=case.case_id)
            # model= is what prices the step (TASK-112); without it the baseline would report $0 and
            # the cost comparison would be a lie in the pipeline's favour.
            with tracer.step("SingleAgent", "quote", model=MODEL_PLANNER) as step:
                quote = await baseline_quote(
                    case.input.text or _text_of(case), settings=settings, facade=facade, usage=step
                )
            document = tracer.document()
            result.tokens_in = document.total_tokens_in
            result.tokens_out = document.total_tokens_out
            result.cost_usd = document.total_cost_usd
            result.predicted = [(line.sku, str(line.qty)) for line in quote.lines]
            result.extracted_lines = len(quote.lines)
            result.total_vnd = quote.total_vnd or None
            # Fairness note. The baseline has no renderer, and it would be rigging the comparison to
            # score it 0% on a "valid PDF" condition it was never given the plumbing to satisfy -
            # typesetting is not the architecture under test. So it is credited with a renderable
            # document whenever it produced priced lines and a positive total. The success metric
            # therefore turns on the two things that actually distinguish the architectures: did it
            # get the items right, and did it get the money right.
            result.has_pdf = bool(quote.lines and quote.total_vnd > 0)
            # It has no critic and no HITL gate, so nothing would ever stop a wrong quote going out.
            result.needs_human = not result.has_pdf
    except Exception as exc:  # noqa: BLE001 - one bad case must not take the run down
        result.error = f"{type(exc).__name__}: {exc}"

    result.latency_ms = int((time.perf_counter() - started) * 1000)

    result.sku_correct, result.sku_attempted = score_skus(result.predicted, expected)

    result.price_exact = (
        result.total_vnd is not None
        and result.expected_total_vnd is not None
        and result.total_vnd == result.expected_total_vnd
    )
    result.success = bool(
        result.error is None
        and sorted(result.predicted) == sorted(expected)
        and result.price_exact
        and result.has_pdf
        and not result.blocking_flags
    )
    return result


def _text_of(case: EvalCase) -> str:
    """The baseline is text-only, so a sheet/PDF case is flattened to raw text for fairness."""
    if case.input.text:
        return case.input.text
    if case.input.file and case.input.file.endswith(".pdf"):
        from ..parsing.pdf import extract_pdf_text  # noqa: PLC0415

        return extract_pdf_text((DATASET / case.input.file).read_bytes())
    from ..parsing import parse_excel  # noqa: PLC0415

    extraction = parse_excel((DATASET / (case.input.file or "")).read_bytes())
    return "\n".join(
        f"- {line.description_normalized}: {line.quantity}" for line in extraction.lines
    )


async def run_mode(
    mode: str, cases: list[EvalCase], settings: Settings, facade: MemoryFacade
) -> dict[str, Any]:
    results: list[CaseResult] = []
    for index, case in enumerate(cases, start=1):
        result = await run_case(case, mode, settings, facade, sequence=index)
        results.append(result)
        mark = "skip" if result.skipped else ("ok" if result.success else "FAIL")
        detail = result.error or result.skip_reason or ""
        print(
            f"  [{mode:<8}] {case.case_id:<14} {mark:<4} "
            f"{result.latency_ms:>6} ms  ${result.cost_usd}  {detail}"
        )
    return {
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "aggregate": aggregate(results),
        "cases": [result.model_dump(mode="json") for result in results],
    }


def _summary_row(name: str, report: dict[str, Any]) -> str:
    agg = report["aggregate"]
    return (
        f"| {name} | {agg['task_success']:.0%} | {agg['line_extraction']['f1']:.3f} | "
        f"{agg['sku_top1_accuracy']:.0%} | {agg['price_exactness']:.0%} | "
        f"{agg['human_intervention_rate']:.0%} | {agg['latency_ms']['p50'] / 1000:.1f}s | "
        f"${agg['cost_usd']['per_quote']} |"
    )


def write_summary(reports: dict[str, dict[str, Any]], stamp: str) -> Path:
    lines = [
        "# QuoteMind eval report",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()} · "
        f"{next(iter(reports.values()))['aggregate']['cases']} scored cases, "
        f"{next(iter(reports.values()))['aggregate']['skipped']} skipped",
        "",
        "| mode | task success | line F1 | SKU top-1 | price exact | needs human | p50 | $/quote |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines.extend(_summary_row(name, report) for name, report in reports.items())

    if "pipeline" in reports and "baseline" in reports:
        pipeline = reports["pipeline"]["aggregate"]
        baseline = reports["baseline"]["aggregate"]
        delta = (pipeline["task_success"] - baseline["task_success"]) * 100
        price_delta = (pipeline["price_exactness"] - baseline["price_exactness"]) * 100
        lines += [
            "",
            "## Headline (TASK-122)",
            "",
            f"**Task success: pipeline {pipeline['task_success']:.0%} vs "
            f"baseline {baseline['task_success']:.0%} — a {delta:+.0f} point delta.**",
            "",
            f"Price exactness: {pipeline['price_exactness']:.0%} vs "
            f"{baseline['price_exactness']:.0%} ({price_delta:+.0f} points). "
            "The pipeline's money comes from a deterministic engine; the baseline's comes from the "
            "model. This line is the argument for the architecture.",
        ]

    path = REPORTS / f"{stamp}_summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


async def main_async(mode: str, limit: int | None) -> None:
    settings = require_settings()
    facade = MemoryFacade.from_settings(settings)
    cases = load_cases(limit)
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    modes = ["pipeline", "baseline"] if mode == "both" else [mode]
    reports: dict[str, dict[str, Any]] = {}
    for name in modes:
        print(f"\n=== {name} ({len(cases)} cases) ===")
        report = await run_mode(name, cases, settings, facade)
        reports[name] = report
        path = REPORTS / f"{stamp}_{name}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  -> {path}")

    summary = write_summary(reports, stamp)
    print(f"\n{summary.read_text(encoding='utf-8')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="QuoteMind eval runner (TASK-121/122)")
    parser.add_argument("--mode", choices=["pipeline", "baseline", "both"], default="pipeline")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N cases")
    args = parser.parse_args()
    asyncio.run(main_async(args.mode, args.limit))


if __name__ == "__main__":
    main()
