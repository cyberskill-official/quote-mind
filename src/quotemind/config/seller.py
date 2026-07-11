"""Demo seller identity (Appendix A.6).

Every value here is SAMPLE data for a fictional demo entity. The spec is explicit that the public
repository must not carry a real MST or real bank details, and it is right to be: a quote PDF
carries payment instructions, so a real account number in a public repo is an invitation to invoice
fraud. Real tenant identity belongs in tenant config at deploy time, never in source.

Lives in `config` (not `api`) so the eval harness can build quotes without importing the API layer.
"""

from __future__ import annotations

from typing import Any

SELLER_BLOCK: dict[str, Any] = {
    "name": "CyberSkill Demo Distribution JSC (SAMPLE)",
    "address": "SAMPLE - 1 Demo Street, District 1, Ho Chi Minh City, Vietnam",
    "mst": "0100000000",  # SAMPLE - not a real tax code
    "phone": "(+84) 900 000 000",  # SAMPLE
    "email": "quotes@demo.cyberskill.world",
    "bank": {
        "bank": "SAMPLE Commercial Joint Stock Bank",
        "beneficiary": "CYBERSKILL DEMO DISTRIBUTION JSC (SAMPLE)",
        "account": "0000000000",  # SAMPLE - not a real account
        "swift": "SAMPLEVX",  # SAMPLE
    },
}
