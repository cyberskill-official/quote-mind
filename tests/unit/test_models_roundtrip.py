"""EV-02: every DM model round-trips through model_dump / model_validate."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel

from quotemind.models import (
    GENESIS_HASH,
    Actor,
    BilingualText,
    Buyer,
    CatalogProduct,
    Category,
    Channel,
    CriticReport,
    CustomerMatch,
    CustomerProfile,
    DocType,
    EpisodicQuoteMemory,
    EvalCase,
    EvalInput,
    EvalLabelLine,
    EvalLabels,
    IntakeResult,
    ItemBrief,
    Language,
    LineSource,
    MarginInfo,
    MatchResult,
    MatchStatus,
    Outcome,
    Quote,
    QuoteLine,
    QuoteRecord,
    QuoteTerms,
    RFQExtraction,
    RFQLine,
    SOPSnippet,
    SopTopic,
    SourceSpan,
    Status,
    StockStatus,
    Tier,
    TraceStep,
    Urgency,
    UsdReference,
    VatBreakdownEntry,
    make_event,
    new_ulid,
)

_NOW = datetime(2026, 7, 11, 3, 0, tzinfo=timezone.utc)
_BT = BilingualText(vi="Báo giá", en="Quotation")


def _samples() -> list[BaseModel]:
    return [
        _BT,
        QuoteRecord(
            quote_id=new_ulid(),
            quote_number="QM-2026-0007",
            status=Status.RECEIVED,
            channel=Channel.PASTE,
            language=Language.VI,
        ),
        IntakeResult(
            language=Language.VI,
            doc_type=DocType.EMAIL_TEXT,
            urgency=Urgency.NORMAL,
            customer_match=CustomerMatch(
                customer_id="cust_thanhcong", method="mst", confidence=0.9
            ),
        ),
        RFQExtraction(
            buyer=Buyer(company="Công ty TNHH Thành Công", mst="0301234567"),
            lines=[
                RFQLine(
                    raw_text="Laptop Dell Latitude 5450 - 20 cái",
                    description_normalized="Dell Latitude 5450",
                    quantity=Decimal("20"),
                    unit="cái",
                    unit_original="cái",
                    confidence=0.95,
                    source_span=SourceSpan(start=0, end=34),
                )
            ],
            language_per_line=[Language.VI],
        ),
        CatalogProduct(
            sku="DELL-LAT-5450",
            brand="Dell",
            category=Category.LAPTOP,
            name=BilingualText(
                vi="Máy tính xách tay Dell Latitude 5450", en="Dell Latitude 5450 laptop"
            ),
            unit="chiếc",
            list_price_vnd=32_000_000,
            dealer_price_vnd=30_000_000,
            cost_price_vnd=28_000_000,
            vat_rate=8,
            stock_status=StockStatus.IN_STOCK,
            lead_time_days=7,
            warranty_months=36,
        ),
        CustomerProfile(
            customer_id="cust_thanhcong",
            name="Công ty TNHH Thành Công",
            tier=Tier.DEALER,
            project_discount_pct=2.0,
        ),
        EpisodicQuoteMemory(
            memory_id=new_ulid(),
            quote_number="QM-2026-0007",
            summary=_BT,
            items_brief=[ItemBrief(sku="DELL-LAT-5450", qty=Decimal("20"), unit_price=30_000_000)],
            outcome=Outcome.APPROVED,
            importance=0.8,
            created_at=_NOW,
        ),
        SOPSnippet(
            topic=SopTopic.PAYMENT,
            text=BilingualText(vi="100% trước giao hàng", en="100% before delivery"),
        ),
        MatchResult(
            line_ref=0, status=MatchStatus.MATCHED, sku="DELL-LAT-5450", match_confidence=0.97
        ),
        Quote(
            quote_id=new_ulid(),
            quote_number="QM-2026-0007",
            date="2026-07-11",
            validity_days=14,
            lines=[
                QuoteLine(
                    idx=1,
                    sku="DELL-LAT-5450",
                    description=BilingualText(vi="Dell Latitude 5450", en="Dell Latitude 5450"),
                    unit=BilingualText(vi="chiếc", en="unit"),
                    qty=Decimal("20"),
                    unit_price_vnd=30_000_000,
                    line_total_vnd=600_000_000,
                    vat_rate=8,
                    vat_amount_vnd=48_000_000,
                    source=LineSource.MATCHED,
                )
            ],
            subtotal_vnd=600_000_000,
            vat_breakdown=[VatBreakdownEntry(rate=8, base=600_000_000, amount=48_000_000)],
            total_vnd=648_000_000,
            total_in_words_vi="Sáu trăm bốn mươi tám triệu đồng",
            usd_reference=UsdReference(
                rate=25_400,
                subtotal=Decimal("23622.05"),
                total=Decimal("25511.81"),
                as_of="2026-07-11",
            ),
            terms=QuoteTerms(
                payment=BilingualText(vi="50/50", en="50/50"),
                delivery=BilingualText(vi="2 tuần", en="2 weeks"),
                warranty=BilingualText(vi="36 tháng", en="36 months"),
            ),
            notes=BilingualText(vi="", en=""),
            margin=MarginInfo(blended_pct=6.5, per_line=[6.5]),
        ),
        CriticReport(passed=True, note=BilingualText(vi="Đã kiểm tra", en="Checked")),
        make_event(
            quote_id="q1",
            seq=1,
            actor=Actor(kind="system"),
            event="received",
            prev_hash=GENESIS_HASH,
        ),
        EvalCase(
            case_id="vi_text_003",
            input=EvalInput(text="Kính gửi Quý công ty"),
            labels=EvalLabels(
                lines=[
                    EvalLabelLine(
                        description_canon="Dell Latitude 5450",
                        sku="DELL-LAT-5450",
                        qty=Decimal("20"),
                    )
                ],
                customer_id="cust_thanhcong",
            ),
            tags=["vi", "text"],
        ),
        TraceStep(
            seq=1, agent="IntakeClassifier", action="classify", summary="detected vi/email_text"
        ),
    ]


def test_all_models_roundtrip() -> None:
    for model in _samples():
        restored = type(model).model_validate(model.model_dump())
        assert restored == model


def test_bilingual_diacritics_survive_json() -> None:
    dumped = _BT.model_dump_json()
    assert "Báo giá" in dumped  # ensure_ascii disabled at the JSON layer
    assert BilingualText.model_validate_json(dumped) == _BT
