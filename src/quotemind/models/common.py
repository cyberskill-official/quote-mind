"""Shared model primitives - QM-SPEC-001 section 7 (DM-04 and the shared enums)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel
from ulid import ULID


def new_ulid() -> str:
    """Return a fresh ULID string (section 7: ids are ULIDs unless stated)."""
    return str(ULID())


class BilingualText(BaseModel):
    """DM-04: every human-readable field carries both Vietnamese and English."""

    vi: str
    en: str


class Language(str, Enum):
    VI = "vi"
    EN = "en"
    # FR-022 classifies a *document* as vi/en/mixed. Per-line language (FR-035) only ever uses
    # vi/en; MIXED exists for IntakeResult.language, which the DM enum originally omitted.
    MIXED = "mixed"


class Channel(str, Enum):
    UPLOAD = "upload"
    OSS_DROP = "oss_drop"
    PASTE = "paste"


class DocType(str, Enum):
    EMAIL_TEXT = "email_text"
    PDF_DIGITAL = "pdf_digital"
    PDF_SCAN = "pdf_scan"
    EXCEL = "excel"
    IMAGE = "image"  # FR-022 enumerates image; the DM enum originally omitted it


class Urgency(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Tier(str, Enum):
    END_CUSTOMER = "end_customer"
    DEALER = "dealer"
    PROJECT = "project"


class Currency(str, Enum):
    VND = "VND"
    USD = "USD"


class Category(str, Enum):
    LAPTOP = "laptop"
    DESKTOP = "desktop"
    MONITOR = "monitor"
    NETWORK = "network"
    SERVER = "server"
    SOFTWARE_LICENSE = "software_license"
    SERVICE = "service"
    ACCESSORY = "accessory"
    TELECOM_SERVICE = "telecom_service"


class StockStatus(str, Enum):
    IN_STOCK = "in_stock"
    LOW = "low"
    OUT_OF_STOCK = "out_of_stock"


class MatchStatus(str, Enum):
    MATCHED = "matched"
    NEEDS_CONFIRMATION = "needs_confirmation"
    NO_MATCH = "no_match"


class LineSource(str, Enum):
    MATCHED = "matched"
    SUBSTITUTED = "substituted"
    NO_MATCH = "no_match"


class Outcome(str, Enum):
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class SopTopic(str, Enum):
    PAYMENT = "payment"
    DELIVERY = "delivery"
    WARRANTY = "warranty"
    VALIDITY = "validity"
    SUBSTITUTION = "substitution"
