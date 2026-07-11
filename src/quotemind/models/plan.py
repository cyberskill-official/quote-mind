"""FR-131: the plan the orchestrator executed - or the reason it decided it did not need one."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanSubtask(BaseModel):
    """One step of the plan, and what actually became of it.

    `state` is AgentScope's, not ours: todo | in_progress | done | abandoned. A subtask still at
    `todo` when the plan finishes is the interesting case - it means the work was handed to a human,
    or the pipeline took a route the plan did not anticipate. Either way it is worth seeing.
    """

    name: str
    description: str
    expected_outcome: str
    state: str
    outcome: str | None = None


class PlanRecord(BaseModel):
    """A snapshot of the plan, taken before it is closed, for the trace and the dashboard.

    The snapshot matters: `PlanNotebook.finish_plan` clears `current_plan`, so a plan read after
    closing is no plan at all.
    """

    skipped: bool = False
    reason: str = ""  # why the fast path was taken (FR-131: "plan skipped, logged")
    name: str = ""
    description: str = ""
    expected_outcome: str = ""
    subtasks: list[PlanSubtask] = Field(default_factory=list)
    state: str = ""
    outcome: str | None = None


__all__ = ["PlanRecord", "PlanSubtask"]
