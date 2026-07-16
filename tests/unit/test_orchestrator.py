"""TASK-130: the whole pipeline, with the model and the cloud both mocked - no network at all."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from quotemind import orchestrator
from quotemind.agents.matcher import MatchSelection
from quotemind.models import (
    BilingualText,
    Buyer,
    CatalogProduct,
    Category,
    CustomerProfile,
    MatchStatus,
    RFQExtraction,
    RFQLine,
    StockStatus,
    Tier,
)
from quotemind.orchestrator import quote_from_text

_LAPTOP = CatalogProduct(
    sku="DELL-LAT-5450",
    brand="Dell",
    category=Category.LAPTOP,
    name=BilingualText(vi="Laptop Dell Latitude 5450", en="Dell Latitude 5450 laptop"),
    unit="cái",
    list_price_vnd=22_000_000,
    dealer_price_vnd=19_800_000,
    cost_price_vnd=17_500_000,
    vat_rate=8,
    stock_status=StockStatus.IN_STOCK,
    lead_time_days=7,
    warranty_months=12,
)
_MONITOR = CatalogProduct(
    sku="DELL-P2723DE",
    brand="Dell",
    category=Category.MONITOR,
    name=BilingualText(vi="Màn hình Dell P2723DE 27 inch", en="Dell P2723DE 27 inch monitor"),
    unit="cái",
    list_price_vnd=7_200_000,
    dealer_price_vnd=6_400_000,
    cost_price_vnd=5_700_000,
    vat_rate=8,
    stock_status=StockStatus.IN_STOCK,
    lead_time_days=3,
    warranty_months=12,
)
_CUSTOMER = CustomerProfile(
    customer_id="cust_thanhcong",
    name="Công ty TNHH Thành Công",
    emails=["mua.hang@thanhcong.vn"],
    domains=["thanhcong.vn"],
    tier=Tier.DEALER,
    project_discount_pct=3.0,
)


class _Settings:
    dashscope_api_key = "sk-test"
    dashscope_base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    quote_validity_days = 14
    margin_floor_pct = 5
    fx_usd_vnd = 25_400


def _line(description: str, qty: int | None) -> RFQLine:
    return RFQLine(
        raw_text=description,
        description_normalized=description,
        quantity=None if qty is None else Decimal(qty),
        unit="cái",
        unit_original="cái",
        confidence=0.95,
    )


def _extraction(lines: list[RFQLine]) -> RFQExtraction:
    return RFQExtraction(
        buyer=Buyer(company="Công ty TNHH Thành Công", email="mua.hang@thanhcong.vn"),
        lines=lines,
    )


def _facade() -> MagicMock:
    facade = MagicMock()
    facade.search_catalog_vector.return_value = [(_LAPTOP, 0.91), (_MONITOR, 0.62)]
    facade.search_catalog_text.return_value = [(_LAPTOP, 0.80), (_MONITOR, 0.55)]
    facade.search_customers_text.return_value = [(_CUSTOMER, 0.99)]
    return facade


def _patch(monkeypatch: pytest.MonkeyPatch, extraction: RFQExtraction) -> None:
    async def fake_extract(_text: str, _settings: Any, **_kwargs: Any) -> RFQExtraction:
        return extraction

    async def fake_select(
        description: str, candidates: list[CatalogProduct], _settings: Any, **_kwargs: Any
    ) -> MatchSelection:
        if not candidates:
            return MatchSelection(sku=None, confidence=0.0)
        wanted = "DELL-P2723DE" if "màn hình" in description.lower() else "DELL-LAT-5450"
        skus = {product.sku for product in candidates}
        return MatchSelection(sku=wanted if wanted in skus else None, confidence=0.93)

    monkeypatch.setattr(orchestrator, "extract_text_rfq", fake_extract)
    monkeypatch.setattr(orchestrator, "select_sku", fake_select)
    monkeypatch.setattr(orchestrator, "embed_text", lambda *_a, **_k: [0.0] * 1024)


def test_pipeline_produces_a_critic_clean_quote(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(
        monkeypatch,
        _extraction([_line("Laptop Dell Latitude 5450", 10), _line("Màn hình Dell 27 inch", 5)]),
    )
    result = asyncio.run(
        quote_from_text(
            "Kính gửi, chúng tôi cần báo giá...",
            settings=_Settings(),
            facade=_facade(),
            seller_block={"name": "CyberSkill JSC"},
            sequence=7,
            on_date=date(2026, 7, 11),
        )
    )

    # Customer resolved from the email domain -> dealer tier drives the unit price.
    assert result.resolution is not None
    assert result.resolution.unknown_customer is False
    assert result.resolution.tier == Tier.DEALER

    assert result.quote is not None
    quote = result.quote
    assert quote.quote_number == "QM-2026-0007"
    assert [line.sku for line in quote.lines] == ["DELL-LAT-5450", "DELL-P2723DE"]
    assert quote.lines[0].unit_price_vnd == 19_800_000  # dealer price
    assert quote.lines[0].line_total_vnd == 198_000_000
    assert [match.status for match in result.matches] == [MatchStatus.MATCHED, MatchStatus.MATCHED]

    # The critic independently recomputes every number and finds nothing wrong.
    assert result.critic is not None
    assert result.critic.recompute_diffs == []
    assert result.critic.passed is True

    assert result.html is not None
    assert "QM-2026-0007" in result.html
    assert "Bằng chữ" in result.html


def test_missing_quantity_stops_at_the_extraction_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _extraction([_line("Laptop Dell Latitude 5450", None)]))
    result = asyncio.run(
        quote_from_text(
            "cần laptop",
            settings=_Settings(),
            facade=_facade(),
            seller_block={"name": "CyberSkill JSC"},
            sequence=1,
        )
    )
    assert result.clarification_reasons == ["MISSING_QUANTITY"]
    assert result.quote is None
    assert result.matches == []  # TASK-034: never proceeds to matching


def test_no_match_lines_are_not_priced(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _extraction([_line("Máy pha cà phê công nghiệp", 2)]))

    async def no_pick(*_a: Any, **_k: Any) -> MatchSelection:
        return MatchSelection(sku=None, confidence=0.0)

    monkeypatch.setattr(orchestrator, "select_sku", no_pick)
    result = asyncio.run(
        quote_from_text(
            "cần máy pha cà phê",
            settings=_Settings(),
            facade=_facade(),
            seller_block={"name": "CyberSkill JSC"},
            sequence=2,
        )
    )
    assert result.matches[0].status == MatchStatus.NO_MATCH
    assert result.quote is None
    assert result.clarification_reasons == ["NO_LINE_ITEMS"]
