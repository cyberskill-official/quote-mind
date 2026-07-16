"""TASK-131: the plan is real, or it honestly says it was skipped.

The failure mode a planner invites is theatre: a plan that is generated, never consulted, and always
reports itself complete. These tests exist to make that impossible - the plan's subtasks must be
closed by the pipeline that actually ran, and a subtask nobody closed must still say `todo`.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from quotemind.agents.planner import LOW_CONFIDENCE, MANY_LINES, QuotePlan, triviality
from quotemind.models import Buyer, DocType, Language, RFQExtraction, RFQLine


def _extraction(lines: int = 2, *, unreadable: int = 0, confidence: float = 0.9) -> RFQExtraction:
    items = [
        RFQLine(
            idx=index,
            raw_text=f"line {index}",
            description_normalized=f"line {index}",
            quantity=None if index <= unreadable else Decimal(1),
            unit="cái",
            unit_original="cái",
            confidence=confidence,
        )
        for index in range(1, lines + 1)
    ]
    return RFQExtraction(buyer=Buyer(company="Thành Công"), lines=items, language=Language.VI)


# --- TASK-131: what deserves a plan ---
def test_a_short_clean_paste_takes_the_fast_path_and_says_why() -> None:
    reason = triviality(_extraction(2), DocType.EMAIL_TEXT)
    assert reason is not None
    assert "2 line(s)" in reason  # the log line has to be worth reading


def test_a_long_rfq_is_planned() -> None:
    assert triviality(_extraction(MANY_LINES + 1), DocType.EMAIL_TEXT) is None


def test_a_scan_is_planned_even_when_it_is_short() -> None:
    # OCR is where lines get lost, so a short scan still earns a plan that a short paste does not.
    assert triviality(_extraction(2), DocType.PDF_SCAN) is None
    assert triviality(_extraction(2), DocType.IMAGE) is None


def test_an_unreadable_quantity_is_planned() -> None:
    assert triviality(_extraction(3, unreadable=1), DocType.EMAIL_TEXT) is None


def test_a_parser_that_is_unsure_earns_a_plan() -> None:
    unsure = _extraction(2, confidence=LOW_CONFIDENCE - 0.01)
    assert triviality(unsure, DocType.EMAIL_TEXT) is None


def test_a_no_match_line_cannot_gate_the_plan_and_that_is_not_an_oversight() -> None:
    # NO_MATCH is produced by the matcher. The plan exists to organise the matcher. Planning cannot
    # wait on the result of the thing it is planning, so the only flags available here are the ones
    # intake already knows about - this test pins that boundary so nobody "fixes" it by accident.
    clean = _extraction(4)  # a line of this may still fail to match; the plan cannot know yet
    assert triviality(clean, DocType.EMAIL_TEXT) is not None


# --- the plan the orchestrator drives ---
def test_the_skipped_plan_carries_its_reason_and_no_subtasks() -> None:
    plan = QuotePlan()
    record = asyncio.run(plan.open(_extraction(2), DocType.EMAIL_TEXT))
    assert record.skipped is True
    assert record.reason.startswith("fast path:")
    assert record.subtasks == []


def test_the_plan_records_only_what_the_pipeline_actually_closed() -> None:
    plan = QuotePlan()
    asyncio.run(plan.open(_extraction(MANY_LINES + 1), DocType.EMAIL_TEXT))

    # In execution order, which is the order the plan must list them in: PlanNotebook.finish_subtask
    # also advances the *next* subtask to in_progress, so a plan whose order disagrees with the
    # pipeline's un-completes work that was already done.
    asyncio.run(plan.done("resolve the customer", "tier dealer"))
    asyncio.run(plan.done("match the catalog", "11/11 matched"))
    # deliberately NOT closing the pricing/critic/gate subtasks
    record = asyncio.run(plan.close("done", "stopped early"))

    states = {task.name: task.state for task in record.subtasks}
    assert states["resolve the customer"] == "done"
    assert states["match the catalog"] == "done"

    # AgentScope advances the next subtask to `in_progress` when its predecessor closes - which is a
    # true statement about the pipeline, not an artefact: pricing is what would have run next.
    assert states["price deterministically"] == "in_progress"

    # And everything past it is still untouched. This is the honest record of a pipeline that
    # stopped early; a plan reporting these as `done` would be inventing work that never happened.
    assert states["re-check with the critic"] == "todo"
    assert states["stop at the human gate"] == "todo"


def test_the_unreadable_quantity_subtask_is_meant_to_end_unfinished() -> None:
    # Only a human can close this one. A plan that marked it done would be claiming the system had
    # resolved something it explicitly refused to guess at.
    plan = QuotePlan()
    asyncio.run(plan.open(_extraction(3, unreadable=2), DocType.EMAIL_TEXT))
    record = asyncio.run(plan.close("done", "at the gate"))

    confirm = next(t for t in record.subtasks if t.name == "confirm the unreadable quantities")
    assert confirm.state == "todo"
    assert "2 line(s)" in confirm.description


def test_the_plan_never_claims_credit_for_the_ocr_that_ran_before_it() -> None:
    # The plan is created *after* extraction. A "read the scan" subtask would be the plan taking
    # credit, on its first line, for work that finished before it existed.
    plan = QuotePlan()
    asyncio.run(plan.open(_extraction(2), DocType.PDF_SCAN))
    record = asyncio.run(plan.close("done", "at the gate"))
    assert all("scan" not in task.name for task in record.subtasks)


def test_closing_an_unknown_subtask_cannot_break_the_pipeline() -> None:
    plan = QuotePlan()
    asyncio.run(plan.open(_extraction(MANY_LINES + 1), DocType.EMAIL_TEXT))
    asyncio.run(plan.done("a subtask that does not exist", "whatever"))  # must not raise
    assert asyncio.run(plan.close("done", "fine")).state == "done"


def test_the_snapshot_survives_finishing_the_plan() -> None:
    # PlanNotebook.finish_plan clears current_plan. A record read after closing would be empty, so
    # the snapshot has to be taken first - this asserts the order was not quietly reversed.
    plan = QuotePlan()
    asyncio.run(plan.open(_extraction(MANY_LINES + 1), DocType.EMAIL_TEXT))
    record = asyncio.run(plan.close("done", "at the gate"))

    assert plan.notebook.current_plan is None
    assert len(record.subtasks) == 5
    assert record.outcome == "at the gate"
