"""Observability: cost accounting, OTel GenAI spans, the reasoning trace, and error taxonomy."""

from __future__ import annotations

from .cost import ModelPrices, cost_usd, load_prices
from .errors import RETRY_DELAYS, ErrorCode, classify, is_transient, retry_model_call
from .otel import (
    OP_CHAT,
    OP_EMBEDDINGS,
    OP_EXECUTE_TOOL,
    OP_INVOKE_AGENT,
    PROVIDER,
    Usage,
    genai_attributes,
    genai_span,
    span_name,
)
from .trace import StepContent, TraceDocument, Tracer

__all__ = [
    "OP_CHAT",
    "OP_EMBEDDINGS",
    "OP_EXECUTE_TOOL",
    "OP_INVOKE_AGENT",
    "PROVIDER",
    "RETRY_DELAYS",
    "ErrorCode",
    "ModelPrices",
    "StepContent",
    "TraceDocument",
    "Tracer",
    "Usage",
    "classify",
    "cost_usd",
    "genai_attributes",
    "genai_span",
    "is_transient",
    "load_prices",
    "retry_model_call",
    "span_name",
]
