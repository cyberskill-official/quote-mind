"""Persisted reasoning trace (FR-111).

Every model call, tool call and memory retrieval on a quote's path becomes an ordered TraceStep
(DM-14) with tokens, cost and duration. The document is written to
oss://quotemind-artifacts/traces/{quote_id}.json and rendered by the dashboard's trace panel.

Prompt and response bodies are excluded by default - an RFQ contains a real customer's details, and
a trace is not the place to leak them. Set TRACE_CONTENT=1 to capture them for debugging.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from ..models import TraceStep
from .cost import cost_usd
from .otel import OP_CHAT, OP_EMBEDDINGS, OP_EXECUTE_TOOL, genai_span


class StepContent(BaseModel):
    """Only populated when TRACE_CONTENT=1 (FR-111)."""

    seq: int
    prompt: str | None = None
    response: str | None = None


class TraceDocument(BaseModel):
    """The whole trace for one quote, with roll-ups the dashboard shows at the top."""

    model_config = ConfigDict(protected_namespaces=())

    quote_id: str
    generated_at: datetime
    steps: list[TraceStep] = Field(default_factory=list)
    contents: list[StepContent] = Field(default_factory=list)
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost_usd: Decimal = Decimal("0")
    total_duration_ms: int = 0


class StepRecorder:
    """Handed to the caller inside a `Tracer.step(...)` block."""

    def __init__(self) -> None:
        self.tokens_in = 0
        self.tokens_out = 0
        self.summary = ""
        self.memory_ids: list[str] = []
        self.prompt: str | None = None
        self.response: str | None = None

    def usage(self, tokens_in: int = 0, tokens_out: int = 0) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out

    def note(self, summary: str) -> None:
        self.summary = summary

    def memory(self, ids: list[str]) -> None:
        self.memory_ids.extend(ids)

    def content(self, *, prompt: str | None = None, response: str | None = None) -> None:
        """Recorded only if the Tracer was built with include_content=True."""
        self.prompt = prompt
        self.response = response


class Tracer:
    """Collects the ordered steps for one quote."""

    def __init__(self, quote_id: str, *, include_content: bool = False) -> None:
        self.quote_id = quote_id
        self.include_content = include_content
        self.steps: list[TraceStep] = []
        self.contents: list[StepContent] = []

    @contextmanager
    def step(
        self,
        agent: str,
        action: str,
        *,
        tool: str | None = None,
        model: str | None = None,
        operation: str | None = None,
    ) -> Iterator[StepRecorder]:
        """Time one step, emit its GenAI span, and append the TraceStep with its cost."""
        recorder = StepRecorder()
        resolved_operation = operation or (
            OP_EXECUTE_TOOL if tool else OP_EMBEDDINGS if action == "embed" else OP_CHAT
        )
        started = time.perf_counter()
        failure: str | None = None
        try:
            with genai_span(resolved_operation, model=model, agent=agent, tool=tool) as usage:
                yield recorder
                usage.record(recorder.tokens_in, recorder.tokens_out)
        except Exception as exc:
            # A crash must not erase the evidence of what led to it: record the step, then re-raise.
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            seq = len(self.steps) + 1
            self.steps.append(
                TraceStep(
                    seq=seq,
                    agent=agent,
                    action=action,
                    tool=tool,
                    model=model,
                    tokens_in=recorder.tokens_in,
                    tokens_out=recorder.tokens_out,
                    cost_usd=(
                        cost_usd(model, recorder.tokens_in, recorder.tokens_out)
                        if model
                        else Decimal(0)
                    ),
                    duration_ms=duration_ms,
                    summary=failure or recorder.summary or action,
                    memory_ids=recorder.memory_ids,
                )
            )
            if self.include_content and (recorder.prompt or recorder.response):
                self.contents.append(
                    StepContent(seq=seq, prompt=recorder.prompt, response=recorder.response)
                )

    def document(self) -> TraceDocument:
        """Roll the steps up into the persisted document."""
        return TraceDocument(
            quote_id=self.quote_id,
            generated_at=datetime.now(timezone.utc),
            steps=self.steps,
            contents=self.contents,
            total_tokens_in=sum(step.tokens_in for step in self.steps),
            total_tokens_out=sum(step.tokens_out for step in self.steps),
            total_cost_usd=sum((step.cost_usd for step in self.steps), Decimal(0)),
            total_duration_ms=sum(step.duration_ms for step in self.steps),
        )
