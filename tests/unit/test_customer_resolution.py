"""FR-043: an exact email match must not be shadowed by a name that fails to match.

Found in the live audit. Two RFQs from the same address, `mua.hang@thanhcong.vn`:

    "Cong ty Thanh Cong can bao gia ..."   -> resolved, dealer tier
    "Thanh Cong can bao gia ..."           -> UNKNOWN_CUSTOMER, list price

The candidate search was an `or` chain - hint, else company name, else the email domain - so the
email was consulted only when there was no company name at all. A name the text search could not
match therefore hid the strongest identifier on the document, and the customer was quoted at list
price with their own history never recalled.
"""

from __future__ import annotations

from typing import Any

from quotemind.models import CustomerProfile, Tier
from quotemind.tools.customer import resolve_customer


def _thanh_cong() -> CustomerProfile:
    return CustomerProfile(
        customer_id="cust_thanhcong",
        name="Công ty TNHH Thành Công",
        tier=Tier.DEALER,
        domains=["thanhcong.vn"],
        emails=["mua.hang@thanhcong.vn"],
        project_discount_pct=3.0,
    )


class FakeFacade:
    """Text search that only matches the full, diacritic-correct name - like the real one."""

    def __init__(self) -> None:
        self.searched: list[str] = []

    def search_customers_text(self, lookup: str) -> list[tuple[CustomerProfile, float]]:
        self.searched.append(lookup)
        if "thanhcong.vn" in lookup.lower() or "công ty" in lookup.lower():
            return [(_thanh_cong(), 0.9)]
        return []  # "Thanh Cong" alone finds nothing


def _candidates(
    facade: Any, *, hint: str | None, company: str | None, email: str | None
) -> list[CustomerProfile]:
    """The orchestrator's candidate gathering, as it now is: every signal, unioned."""
    lookups = [hint, company, email.split("@")[-1] if email else None]
    out: list[CustomerProfile] = []
    seen: set[str] = set()
    for lookup in lookups:
        if not lookup:
            continue
        for profile, _ in facade.search_customers_text(lookup):
            if profile.customer_id not in seen:
                seen.add(profile.customer_id)
                out.append(profile)
    return out


def test_a_name_that_does_not_match_no_longer_hides_the_email() -> None:
    facade = FakeFacade()
    candidates = _candidates(facade, hint=None, company="Thanh Cong", email="mua.hang@thanhcong.vn")

    # The old `or` chain stopped at the company name and never searched the domain.
    assert "thanhcong.vn" in facade.searched
    resolution = resolve_customer(candidates, email="mua.hang@thanhcong.vn", name="Thanh Cong")

    assert resolution.profile is not None
    assert resolution.profile.customer_id == "cust_thanhcong"
    assert resolution.tier is Tier.DEALER  # not list price
    assert resolution.unknown_customer is False


def test_the_name_path_still_works_when_it_does_match() -> None:
    facade = FakeFacade()
    candidates = _candidates(facade, hint=None, company="Công ty TNHH Thành Công", email=None)
    resolution = resolve_customer(candidates, email=None, name="Công ty TNHH Thành Công")
    assert resolution.profile is not None
    assert resolution.tier is Tier.DEALER


def test_a_genuinely_unknown_customer_is_still_unknown() -> None:
    # The fix must not make the system credulous: no signal matching still means no customer.
    facade = FakeFacade()
    candidates = _candidates(facade, hint=None, company="Ai Do", email="a@khongbiet.vn")
    resolution = resolve_customer(candidates, email="a@khongbiet.vn", name="Ai Do")
    assert resolution.profile is None
    assert resolution.unknown_customer is True
