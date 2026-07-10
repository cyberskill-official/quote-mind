"""Public model surface - DM-01..14, the Status machine, and shared enums (frozen)."""

from __future__ import annotations

from .audit import (
    GENESIS_HASH,
    Actor,
    AuditEvent,
    compute_event_hash,
    make_event,
    verify_chain,
)
from .catalog import CatalogProduct, CustomerProfile
from .common import (
    BilingualText,
    Category,
    Channel,
    Currency,
    DocType,
    Language,
    LineSource,
    MatchStatus,
    Outcome,
    SopTopic,
    StockStatus,
    Tier,
    Urgency,
    new_ulid,
)
from .critic import CriticReport, RecomputeDiff
from .eval import EvalCase, EvalInput, EvalLabelLine, EvalLabels
from .extraction import Buyer, RFQExtraction, RFQLine, SourceSpan
from .intake import CustomerMatch, EmailMeta, IntakeResult
from .matching import MatchAlternative, MatchResult
from .memory import EpisodicQuoteMemory, ItemBrief, SOPSnippet
from .quote import (
    MarginInfo,
    Quote,
    QuoteLine,
    QuoteTerms,
    UsdReference,
    VatBreakdownEntry,
)
from .quote_record import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    IllegalTransitionError,
    QuoteRecord,
    Status,
    assert_transition,
    can_transition,
)
from .trace import TraceStep

__all__ = [
    "GENESIS_HASH",
    "LEGAL_TRANSITIONS",
    "TERMINAL_STATES",
    "Actor",
    "AuditEvent",
    "BilingualText",
    "Buyer",
    "CatalogProduct",
    "Category",
    "Channel",
    "CriticReport",
    "Currency",
    "CustomerMatch",
    "CustomerProfile",
    "DocType",
    "EmailMeta",
    "EpisodicQuoteMemory",
    "EvalCase",
    "EvalInput",
    "EvalLabelLine",
    "EvalLabels",
    "IllegalTransitionError",
    "IntakeResult",
    "ItemBrief",
    "Language",
    "LineSource",
    "MarginInfo",
    "MatchAlternative",
    "MatchResult",
    "MatchStatus",
    "Outcome",
    "Quote",
    "QuoteLine",
    "QuoteRecord",
    "QuoteTerms",
    "RFQExtraction",
    "RFQLine",
    "RecomputeDiff",
    "SOPSnippet",
    "SopTopic",
    "SourceSpan",
    "Status",
    "StockStatus",
    "Tier",
    "TraceStep",
    "Urgency",
    "UsdReference",
    "VatBreakdownEntry",
    "assert_transition",
    "can_transition",
    "compute_event_hash",
    "make_event",
    "new_ulid",
    "verify_chain",
]
