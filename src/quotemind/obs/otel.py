"""OpenTelemetry GenAI spans (FR-110).

Span names and attributes follow the GenAI semantic conventions: `chat qwen3-max`,
`execute_tool vector_search`, `invoke_agent CatalogMatcher`. The OTel SDK is optional - without it
the span context manager is a no-op, so nothing on the quote path depends on an exporter being
configured. The name/attribute builders are pure, so the convention itself is unit-testable.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

PROVIDER = "dashscope"

OP_CHAT = "chat"
OP_EMBEDDINGS = "embeddings"
OP_EXECUTE_TOOL = "execute_tool"
OP_INVOKE_AGENT = "invoke_agent"


def span_name(operation: str, target: str | None) -> str:
    """`{operation} {model|tool|agent}` per the GenAI conventions."""
    return f"{operation} {target}" if target else operation


def genai_attributes(
    operation: str,
    *,
    model: str | None = None,
    agent: str | None = None,
    tool: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> dict[str, Any]:
    """The attribute set for one GenAI span."""
    attributes: dict[str, Any] = {
        "gen_ai.provider.name": PROVIDER,
        "gen_ai.operation.name": operation,
    }
    if model:
        attributes["gen_ai.request.model"] = model
    if agent:
        attributes["gen_ai.agent.name"] = agent
    if tool:
        attributes["gen_ai.tool.name"] = tool
    if tokens_in:
        attributes["gen_ai.usage.input_tokens"] = tokens_in
    if tokens_out:
        attributes["gen_ai.usage.output_tokens"] = tokens_out
    return attributes


@dataclass
class Usage:
    """Filled in by the caller once the call returns; written onto the span on exit."""

    tokens_in: int = 0
    tokens_out: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def record(self, tokens_in: int = 0, tokens_out: int = 0) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out


def _tracer() -> Any | None:
    try:
        from opentelemetry import trace  # noqa: PLC0415
    except ImportError:
        return None
    return trace.get_tracer("quotemind")


@contextmanager
def genai_span(
    operation: str,
    *,
    model: str | None = None,
    agent: str | None = None,
    tool: str | None = None,
) -> Iterator[Usage]:
    """Emit a GenAI span if the OTel SDK is installed; else a no-op that still collects usage."""
    usage = Usage()
    tracer = _tracer()
    if tracer is None:
        yield usage
        return

    target = tool or model or agent
    with tracer.start_as_current_span(span_name(operation, target)) as span:
        try:
            yield usage
        finally:
            for key, value in genai_attributes(
                operation,
                model=model,
                agent=agent,
                tool=tool,
                tokens_in=usage.tokens_in,
                tokens_out=usage.tokens_out,
            ).items():
                span.set_attribute(key, value)
