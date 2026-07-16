"""Agent-layer guardrails: base-URL derivation (TASK-012) and the TASK-042 SKU whitelist."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from quotemind.agents import matcher
from quotemind.agents.matcher import MatchSelection, select_sku
from quotemind.agents.model import native_base_url
from quotemind.models import BilingualText, CatalogProduct, Category, StockStatus


class _Settings:
    dashscope_base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    dashscope_api_key = "sk-test"


def _product(sku: str) -> CatalogProduct:
    return CatalogProduct(
        sku=sku,
        brand="Dell",
        category=Category.LAPTOP,
        name=BilingualText(vi="Laptop Dell", en="Dell laptop"),
        unit="cái",
        list_price_vnd=20_000_000,
        dealer_price_vnd=18_000_000,
        cost_price_vnd=15_000_000,
        vat_rate=8,
        stock_status=StockStatus.IN_STOCK,
        lead_time_days=7,
        warranty_months=12,
    )


def test_native_base_url_derives_api_v1_from_compatible_base() -> None:
    assert native_base_url(_Settings()) == "https://dashscope-intl.aliyuncs.com/api/v1"


def test_native_base_url_passes_through_a_non_compatible_base() -> None:
    class Other:
        dashscope_base_url = "https://custom.example.com/api/v1"

    assert native_base_url(Other()) == "https://custom.example.com/api/v1"


def _fake_agent(metadata: dict[str, Any]) -> Any:
    class _Reply:
        def __init__(self) -> None:
            self.metadata = metadata

    class _Agent:
        async def __call__(self, *_args: Any, **_kwargs: Any) -> _Reply:
            return _Reply()

    return _Agent()


def test_select_sku_accepts_a_candidate_sku(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        matcher,
        "build_agent",
        lambda **_: _fake_agent({"sku": "DL-1", "confidence": 0.91, "specs_conflict": False}),
    )
    result = asyncio.run(select_sku("laptop", [_product("DL-1"), _product("DL-2")], _Settings()))
    assert result.sku == "DL-1"
    assert result.confidence == 0.91


def test_select_sku_discards_a_hallucinated_sku(monkeypatch: pytest.MonkeyPatch) -> None:
    # The model returns a SKU that is not in the candidate whitelist: code must reject it.
    monkeypatch.setattr(
        matcher,
        "build_agent",
        lambda **_: _fake_agent({"sku": "MADE-UP-999", "confidence": 0.99}),
    )
    result = asyncio.run(select_sku("laptop", [_product("DL-1")], _Settings()))
    assert result.sku is None
    assert result.confidence == 0.0
    assert "outside the candidate list" in result.reason_en


def test_select_sku_without_candidates_never_calls_the_model() -> None:
    result = asyncio.run(select_sku("laptop", [], _Settings()))
    assert result == MatchSelection(sku=None, confidence=0.0)
