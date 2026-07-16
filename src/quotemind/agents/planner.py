"""TASK-131: the orchestrator's plan, kept in AgentScope's PlanNotebook.

A plan here is not decoration. It is built from the document that actually arrived, its subtasks are
closed as the pipeline actually completes them, and the snapshot that reaches the trace is the real
end state - including any subtask still sitting at `todo`, which means the pipeline took a route the
plan did not anticipate. A plan that always reports itself complete would be worse than no plan: it
would be a confident lie in the one artifact a reviewer opens to find out what happened.

Trivial quotes skip the plan and say so (TASK-131: "trivial quotes may take the fast path, plan
skipped, logged"). Planning a two-line paste would burn tokens to restate a fixed sequence.
"""

from __future__ import annotations

from agentscope.plan import PlanNotebook, SubTask

from ..models import DocType, PlanRecord, PlanSubtask, RFQExtraction

# TASK-131's own thresholds: multi-document, more than ten lines, or flags at intake.
MANY_LINES = 10
LOW_CONFIDENCE = 0.7


def triviality(extraction: RFQExtraction, doc_type: DocType) -> str | None:
    """Why this quote needs no plan - or None when it does.

    Returns the *reason*, not a bare bool, because "skipped" with no reason is the kind of log line
    that tells you nothing at 2am.

    On the word "flags" in TASK-131: the flags this can see are the ones that exist at *intake*. A
    NO_MATCH line or a margin breach cannot gate the plan, because they are produced by the matcher
    and the critic - which is the work the plan exists to organise. Planning cannot wait for the
    result of the thing it is planning. So the signals used here are the ones already on the table:
    how many lines arrived, whether they came off a scan, whether any quantity was unreadable, and
    how sure the parser was.
    """
    reasons: list[str] = []
    if len(extraction.lines) > MANY_LINES:
        reasons.append(f"{len(extraction.lines)} lines (> {MANY_LINES})")
    if doc_type in (DocType.PDF_SCAN, DocType.IMAGE):
        reasons.append("scanned source needs OCR")

    unreadable = sum(1 for line in extraction.lines if line.quantity is None)
    if unreadable:
        reasons.append(f"{unreadable} line(s) with an unreadable quantity")

    unsure = sum(1 for line in extraction.lines if line.confidence < LOW_CONFIDENCE)
    if unsure:
        reasons.append(f"{unsure} line(s) the parser was unsure of")

    if reasons:
        return None  # non-trivial: these are the reasons a plan IS needed
    return f"{len(extraction.lines)} line(s), {doc_type.value}, nothing ambiguous"


def _subtasks(extraction: RFQExtraction, doc_type: DocType) -> list[SubTask]:
    """What is left to do, from the moment the plan is created.

    Note what is *not* here: reading the scan. By the time the orchestrator plans, the OCR has
    already run - extraction is its input. A subtask claiming credit for work that finished before
    the plan existed would be the plan lying in the reviewer's favour on its very first line.
    """
    tasks: list[SubTask] = []

    unreadable = sum(1 for line in extraction.lines if line.quantity is None)
    if unreadable:
        # This one is *meant* to end the plan still at `todo`. The pipeline cannot close it; only a
        # human can. An unfinished subtask on a finished plan is the honest record of a handoff.
        tasks.append(
            SubTask(
                name="confirm the unreadable quantities",
                description=f"{unreadable} line(s) arrived with no legible quantity.",
                expected_outcome="A human confirms each one. The system never guesses a quantity.",
            )
        )

    # This is the *execution* order, not a tidy reading order, and that is load-bearing:
    # PlanNotebook.finish_subtask(i) also moves subtask i+1 to `in_progress`. A list whose order
    # disagreeing with the pipeline's un-completes work already done. That is not hypothetical:
    # "match the catalog" was listed first, and the plan then reported the customer resolution as
    # still running after it had finished.
    tasks.extend(
        [
            SubTask(
                name="resolve the customer",
                description="Identify the buyer and their pricing tier.",
                expected_outcome="A customer profile and tier, or UNKNOWN_CUSTOMER raised.",
            ),
            SubTask(
                name="match the catalog",
                description=f"Resolve {len(extraction.lines)} requested line(s) to catalog SKUs.",
                expected_outcome="A SKU per line, or an explicit needs_confirmation.",
            ),
            SubTask(
                name="price deterministically",
                description="Compute line totals, VAT and the grand total in exact Decimal dong.",
                expected_outcome="Totals no model has touched.",
            ),
            SubTask(
                name="re-check with the critic",
                description="Independently recompute the arithmetic and check the guardrails.",
                expected_outcome="Zero recompute diffs, or the quote is blocked.",
            ),
            SubTask(
                name="stop at the human gate",
                description="Persist at pending_approval and wait for a person.",
                expected_outcome="Nothing is sent without a human decision.",
            ),
        ]
    )
    return tasks


class QuotePlan:
    """Drives a PlanNotebook alongside the pipeline, and snapshots it for the trace."""

    def __init__(self, notebook: PlanNotebook | None = None) -> None:
        self.notebook = notebook or PlanNotebook()
        self.record = PlanRecord()
        self._index: dict[str, int] = {}

    async def open(self, extraction: RFQExtraction, doc_type: DocType) -> PlanRecord:
        """Create the plan - or record, with a reason, that this quote did not need one."""
        skip_reason = triviality(extraction, doc_type)
        if skip_reason is not None:
            self.record = PlanRecord(skipped=True, reason=f"fast path: {skip_reason}")
            return self.record

        tasks = _subtasks(extraction, doc_type)
        self._index = {task.name: index for index, task in enumerate(tasks)}
        await self.notebook.create_plan(
            name=f"Quote {len(extraction.lines)} line(s) from {doc_type.value}",
            description="Turn this RFQ into a priced, checked quote waiting for a human.",
            expected_outcome="A quote at pending_approval with zero critic recompute diffs.",
            subtasks=tasks,
        )
        return self.record

    async def done(self, name: str, outcome: str) -> None:
        """Close one subtask. Unknown names are ignored: the plan must never break the pipeline."""
        index = self._index.get(name)
        if index is None or self.notebook.current_plan is None:
            return
        await self.notebook.finish_subtask(index, outcome)

    async def close(self, state: str, outcome: str) -> PlanRecord:
        """Snapshot the plan, then finish it. The order matters - finish_plan clears it."""
        plan = self.notebook.current_plan
        if plan is None:  # trivial quote, or already closed
            return self.record

        self.record = PlanRecord(
            skipped=False,
            name=plan.name,
            description=plan.description,
            expected_outcome=plan.expected_outcome,
            state=state,
            outcome=outcome,
            subtasks=[
                PlanSubtask(
                    name=task.name,
                    description=task.description,
                    expected_outcome=task.expected_outcome,
                    state=task.state,
                    outcome=task.outcome,
                )
                for task in plan.subtasks
            ],
        )
        await self.notebook.finish_plan(state, outcome)  # type: ignore[arg-type]
        return self.record


__all__ = ["MANY_LINES", "QuotePlan", "triviality"]
