"""EP-11: cost accounting (TASK-112), the reasoning trace (TASK-111), and error taxonomy (TASK-113)."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from quotemind.config.models import MODEL_EMBED, MODEL_PARSER_TEXT, MODEL_PLANNER
from quotemind.obs.cost import cost_usd, load_prices
from quotemind.obs.errors import RETRY_DELAYS, ErrorCode, classify, is_transient, retry_model_call
from quotemind.obs.otel import (
    OP_CHAT,
    OP_EMBEDDINGS,
    OP_EXECUTE_TOOL,
    PROVIDER,
    genai_attributes,
    genai_span,
    span_name,
)
from quotemind.obs.trace import Tracer

# --- TASK-112: cost ---


def test_prices_cover_every_frozen_model() -> None:
    prices = load_prices()
    for model in (MODEL_PLANNER, MODEL_PARSER_TEXT, MODEL_EMBED, "qwen-vl-ocr"):
        assert prices.known(model), model
    assert prices.currency == "USD"


def test_cost_is_per_million_tokens_and_exact() -> None:
    # qwen-plus (the text parser): $0.40 in / $1.20 out per 1M tokens.
    assert cost_usd(MODEL_PARSER_TEXT, 1_000_000, 0) == Decimal("0.400000")
    assert cost_usd(MODEL_PARSER_TEXT, 0, 1_000_000) == Decimal("1.200000")
    assert cost_usd(MODEL_PARSER_TEXT, 500_000, 500_000) == Decimal("0.800000")
    # qwen3-max (the planner) is the expensive one.
    assert cost_usd(MODEL_PLANNER, 1_000_000, 0) == Decimal("1.200000")


def test_cost_of_an_unknown_model_is_zero_not_a_crash() -> None:
    # A new model must never take a quote down; it simply does not contribute to the total.
    prices = load_prices()
    assert not prices.known("some-future-model")
    assert cost_usd("some-future-model", 1000, 1000) == Decimal("0")


def test_embedding_output_is_free() -> None:
    assert cost_usd(MODEL_EMBED, 0, 10_000) == Decimal("0")
    assert cost_usd(MODEL_EMBED, 1_000_000, 0) == Decimal("0.070000")


def test_cost_is_decimal_not_float() -> None:
    assert isinstance(cost_usd(MODEL_PLANNER, 1234, 567), Decimal)


# --- TASK-110: OTel GenAI conventions ---


def test_span_names_follow_the_genai_convention() -> None:
    assert span_name(OP_CHAT, MODEL_PLANNER) == "chat qwen3-max"
    assert span_name(OP_EXECUTE_TOOL, "vector_search") == "execute_tool vector_search"
    assert span_name(OP_CHAT, None) == "chat"


def test_genai_attributes_are_the_registry_names() -> None:
    attributes = genai_attributes(
        OP_EMBEDDINGS, model=MODEL_EMBED, agent="CatalogMatcher", tokens_in=12
    )
    assert attributes["gen_ai.provider.name"] == PROVIDER
    assert attributes["gen_ai.operation.name"] == OP_EMBEDDINGS
    assert attributes["gen_ai.request.model"] == MODEL_EMBED
    assert attributes["gen_ai.agent.name"] == "CatalogMatcher"
    assert attributes["gen_ai.usage.input_tokens"] == 12
    assert "gen_ai.tool.name" not in attributes  # not a tool call, so no tool attribute


def test_genai_span_still_collects_usage_without_an_exporter() -> None:
    # No OTel SDK configured: the span is a no-op, but nothing raises and usage still accumulates.
    with genai_span(OP_CHAT, model=MODEL_PLANNER) as usage:
        usage.record(tokens_in=10, tokens_out=4)
    assert (usage.tokens_in, usage.tokens_out) == (10, 4)


# --- TASK-111: the trace document ---


def test_tracer_records_steps_with_cost_and_totals() -> None:
    tracer = Tracer(quote_id="Q1")
    with tracer.step("DocumentParser", "parse", model=MODEL_PARSER_TEXT) as step:
        step.usage(tokens_in=1_000_000, tokens_out=0)
        step.note("extracted 2 lines")
    with tracer.step("CatalogMatcher", "retrieve", tool="vector_search") as step:
        step.memory(["SKU-1", "SKU-2"])

    document = tracer.document()
    assert document.quote_id == "Q1"
    assert [step.seq for step in document.steps] == [1, 2]

    parse, retrieve = document.steps
    assert parse.agent == "DocumentParser"
    assert parse.model == MODEL_PARSER_TEXT
    assert parse.summary == "extracted 2 lines"
    assert parse.cost_usd == Decimal("0.400000")  # qwen-plus: $0.40 per 1M input tokens

    assert retrieve.tool == "vector_search"
    assert retrieve.memory_ids == ["SKU-1", "SKU-2"]
    assert retrieve.cost_usd == Decimal("0")  # a memory read costs no tokens
    assert retrieve.summary == "retrieve"  # falls back to the action when no note was left

    assert document.total_tokens_in == 1_000_000
    assert document.total_cost_usd == Decimal("0.400000")
    assert document.total_duration_ms >= 0


def test_trace_omits_prompt_bodies_unless_content_is_opted_in() -> None:
    off = Tracer(quote_id="Q1")
    with off.step("DocumentParser", "parse", model=MODEL_PARSER_TEXT) as step:
        step.content(prompt="Chào anh, báo giá giúp em", response='{"lines": []}')
    assert off.document().contents == []  # TASK-111: customer PII stays out of the trace by default

    on = Tracer(quote_id="Q1", include_content=True)
    with on.step("DocumentParser", "parse", model=MODEL_PARSER_TEXT) as step:
        step.content(prompt="Chào anh, báo giá giúp em", response='{"lines": []}')
    contents = on.document().contents
    assert len(contents) == 1
    assert contents[0].seq == 1
    assert contents[0].prompt == "Chào anh, báo giá giúp em"  # diacritics byte-exact


def test_a_failing_step_is_still_recorded_and_the_error_propagates() -> None:
    tracer = Tracer(quote_id="Q1")
    with pytest.raises(RuntimeError), tracer.step("CatalogMatcher", "select", model=MODEL_PLANNER):
        raise RuntimeError("boom")

    # The trace shows where it died, not merely that it did.
    assert tracer.document().steps[0].summary == "RuntimeError: boom"


def test_trace_round_trips_as_json() -> None:
    tracer = Tracer(quote_id="Q1")
    with tracer.step("DocumentParser", "parse", model=MODEL_PARSER_TEXT) as step:
        step.usage(tokens_in=10, tokens_out=5)
    raw = tracer.document().model_dump_json()
    assert '"quote_id":"Q1"' in raw
    assert '"model":"qwen-plus"' in raw


# --- TASK-113: error taxonomy and retry ---


def test_transient_failures_are_the_ones_worth_retrying() -> None:
    assert is_transient(TimeoutError("timed out"))
    assert is_transient(ConnectionError("connection reset"))
    assert is_transient(RuntimeError("429 Too Many Requests"))
    assert is_transient(RuntimeError("503 Service Unavailable"))
    # A bad schema will fail identically forever, so retrying it just wastes tokens.
    assert not is_transient(ValueError("invalid JSON in structured output"))


def test_classify_maps_to_the_taxonomy_and_defaults_to_the_failing_stage() -> None:
    assert classify(TimeoutError("x"), ErrorCode.PARSE_FAIL) is ErrorCode.TIMEOUT
    assert classify(RuntimeError("429 rate limit"), ErrorCode.MATCH_FAIL) is (
        ErrorCode.MODEL_UNAVAILABLE
    )
    assert classify(ValueError("bad json"), ErrorCode.PARSE_FAIL) is ErrorCode.PARSE_FAIL


def test_retry_backs_off_then_succeeds() -> None:
    attempts: list[int] = []
    slept: list[float] = []

    async def flaky() -> str:
        attempts.append(1)
        if len(attempts) < 3:
            raise TimeoutError("timed out")
        return "ok"

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    assert asyncio.run(retry_model_call(flaky, sleep=fake_sleep)) == "ok"
    assert len(attempts) == 3
    assert slept == list(RETRY_DELAYS)  # 1s then 4s, per TASK-113


def test_retry_gives_up_after_the_budget() -> None:
    calls: list[int] = []

    async def always_down() -> str:
        calls.append(1)
        raise ConnectionError("connection reset")

    async def fake_sleep(_seconds: float) -> None:
        return None

    with pytest.raises(ConnectionError):
        asyncio.run(retry_model_call(always_down, sleep=fake_sleep))
    assert len(calls) == len(RETRY_DELAYS) + 1  # the first try plus the retries


def test_a_permanent_error_is_not_retried() -> None:
    calls: list[int] = []

    async def bad_schema() -> str:
        calls.append(1)
        raise ValueError("invalid JSON in structured output")

    async def fake_sleep(_seconds: float) -> None:
        raise AssertionError("a permanent error must not sleep and retry")

    with pytest.raises(ValueError):
        asyncio.run(retry_model_call(bad_schema, sleep=fake_sleep))
    assert len(calls) == 1
