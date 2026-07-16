"""TASK-043 customer resolution: email domain -> fuzzy name -> hint, else end_customer + unknown."""

from __future__ import annotations

from collections.abc import Sequence

from quotemind.models import CustomerProfile, Tier
from quotemind.tools import resolve_customer


def _customer(
    cid: str,
    name: str,
    tier: Tier,
    *,
    domains: Sequence[str] = (),
    emails: Sequence[str] = (),
) -> CustomerProfile:
    return CustomerProfile(
        customer_id=cid, name=name, tier=tier, domains=list(domains), emails=list(emails)
    )


def test_resolve_by_email_domain() -> None:
    candidates = [
        _customer("c1", "ABC Corp", Tier.DEALER, domains=["abc.com"]),
        _customer("c2", "XYZ", Tier.PROJECT, domains=["xyz.vn"]),
    ]
    result = resolve_customer(candidates, email="mua@abc.com")
    assert result.profile is not None and result.profile.customer_id == "c1"
    assert result.tier == Tier.DEALER
    assert result.unknown_customer is False


def test_resolve_by_fuzzy_name_is_accent_insensitive() -> None:
    candidates = [
        _customer("c1", "Công ty Thành Công", Tier.DEALER),
        _customer("c2", "Beta", Tier.END_CUSTOMER),
    ]
    result = resolve_customer(candidates, name="cong ty thanh cong")
    assert result.profile is not None and result.profile.customer_id == "c1"


def test_resolve_by_hint() -> None:
    candidates = [
        _customer("c1", "Alpha", Tier.DEALER, domains=["alpha.io"]),
        _customer("c2", "Beta", Tier.PROJECT),
    ]
    result = resolve_customer(candidates, hint="alpha")
    assert result.profile is not None and result.profile.customer_id == "c1"


def test_email_domain_beats_name() -> None:
    candidates = [
        _customer("c1", "Same Name", Tier.DEALER, domains=["one.com"]),
        _customer("c2", "Same Name", Tier.PROJECT, domains=["two.com"]),
    ]
    result = resolve_customer(candidates, email="x@two.com", name="Same Name")
    assert result.profile is not None and result.profile.customer_id == "c2"


def test_unresolved_defaults_to_end_customer() -> None:
    candidates = [_customer("c1", "Alpha", Tier.DEALER, domains=["alpha.io"])]
    result = resolve_customer(
        candidates, email="x@unknown.com", name="Totally Different", hint="zzz"
    )
    assert result.profile is None
    assert result.tier == Tier.END_CUSTOMER
    assert result.unknown_customer is True
