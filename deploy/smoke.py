"""Prove the deployed site still works - from outside it, the way a client meets it.

    python deploy/smoke.py                                   # the live domain
    python deploy/smoke.py --url http://localhost:9000       # a local uvicorn

Every check in `tests/` runs against the code. This one runs against the *deployment*, and the
distinction has cost us twice:

  * Function Compute injects `Content-Disposition: attachment` on every response from its default
    `*.fcapp.run` domain. `curl` ignores that header; a browser obeys it. So the dashboard
    downloaded instead of rendering, for everyone, for days - while every API check passed, because
    no API check is a browser. `no_attachment_header` below is the regression guard. If FC ever
    starts sending it again, or the custom domain lapses, this fails loudly instead of silently
    turning the primary artifact back into a download.

  * The suite that found that was posting a FIXED RFQ string. Intake is idempotent (FR-024): the
    same text returns the same quote. So from the second run onward it was not exercising the
    pipeline at all - it was re-reading the quote the previous run had left behind, and asserting
    against that. It passed. It was testing nothing. Hence `nonce`: every run posts an RFQ the
    system has genuinely never seen.

The theme both share: a check is only worth what it *would have caught*. Run this after every
deploy.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any

import certifi

LIVE = "https://quotemind.cyberskill.world"
SETTLED = {"pending_approval", "critic_failed", "needs_clarification", "needs_manual"}

# Verify against a CA bundle we ship, not whatever the machine happens to trust. macOS framework
# Pythons have no root store until someone runs `Install Certificates.command`, so the default here
# is a check that fails on a perfectly valid certificate - which is the worst kind of check, because
# it teaches you to ignore it. This still fails on a BAD certificate; it just no longer fails on a
# good one because the client was under-equipped.
_TRUST = ssl.create_default_context(cafile=certifi.where())

_passed = 0
_failed: list[str] = []


def check(name: str, got: object, want: object) -> None:
    global _passed
    if got == want:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed.append(name)
        print(f"  FAIL  {name}: got {got!r}, want {want!r}")


def _request(url: str, token: str | None, payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers)  # noqa: S310
    with urllib.request.urlopen(request, timeout=120, context=_TRUST) as response:  # noqa: S310
        return json.loads(response.read())


def _status(url: str, token: str | None) -> tuple[int, dict[str, str]]:
    request = urllib.request.Request(url)  # noqa: S310
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=60, context=_TRUST) as response:  # noqa: S310
            return response.status, dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers)


def _settle(base: str, token: str, quote_id: str) -> str:
    for _ in range(25):
        time.sleep(6)
        status = str(_request(f"{base}/api/quotes/{quote_id}", token)["status"])
        if status in SETTLED:
            return status
    return "timed_out"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=LIVE)
    args = parser.parse_args()
    base = args.url.rstrip("/")

    token = os.environ.get("DEMO_API_TOKEN")
    if not token:
        sys.exit("DEMO_API_TOKEN is not set - source your .env first")

    print(f"\n=== {base} ===")
    health = _request(f"{base}/health", None)
    print(f"  deployed: {health['git_sha']}")
    check("the model probe found no substitutions", len(health["unverified"]), 0)

    print("\n=== a browser gets a page, not a download (the P0) ===")
    for path in ("/", "/eval"):
        status, headers = _status(f"{base}{path}", None)
        check(f"GET {path}", status, 200)
        check(f"{path} sends no Content-Disposition", headers.get("Content-Disposition"), None)

    print("\n=== the door is locked ===")
    check("/api without a token is 401", _status(f"{base}/api/quotes", None)[0], 401)
    check("/api with the token is 200", _status(f"{base}/api/quotes", token)[0], 200)

    # FR-024: intake is idempotent on the source text. A fixed string here would hand us back the
    # PREVIOUS run's quote and assert against it - green, and testing nothing.
    nonce = int(time.time())
    print(f"\n=== the whole pipeline, on an RFQ it has never seen (ref {nonce}) ===")
    rfq = (
        "Cong ty Thanh Cong can bao gia 4 may chu Dell PowerEdge R650. "
        f"Email: mua.hang@thanhcong.vn (ref {nonce})"
    )
    quote_id = str(_request(f"{base}/api/rfq", token, {"text": rfq})["quote_id"])
    check("it reaches the gate", _settle(base, token, quote_id), "pending_approval")

    quote = _request(f"{base}/api/quotes/{quote_id}", token)
    critic = quote["critic"]
    check("FR-070 the recompute finds zero diffs", len(critic["recompute_diffs"]), 0)
    check("FR-073 the critic wrote a narrative", bool(critic.get("narrative")), True)
    check("FR-056 the lead time is flagged", "LEAD_TIME" in quote["flags"], True)
    check("FR-131 a plan was recorded", bool(quote.get("plan")), True)

    print("\n=== FR-134: a cancellation is not a rejection ===")
    cancelled = _request(
        f"{base}/api/quotes/{quote_id}/cancel", token, {"comment": "khach rut yeu cau"}
    )
    check("cancel ends the quote", cancelled["status"], "rejected")

    events = _request(f"{base}/api/quotes/{quote_id}/audit", token)["events"]
    names = [e["event"] for e in events]
    check("the audit says human.cancel", "human.cancel" in names, True)
    check("the audit does NOT say human.rejected", "human.rejected" in names, False)

    # FR-094. We walk the chain ourselves rather than asking the API whether it is happy with
    # itself - a tamper-evident log that only the server can check is not tamper-evident.
    print("\n=== FR-094: the chain verifies, and we are the ones verifying it ===")
    intact = all(events[i]["prev_hash"] == events[i - 1]["hash"] for i in range(1, len(events)))
    check(f"the hash chain is intact across {len(events)} events", intact, True)

    print(f"\n{'=' * 40}\n  {_passed} passed, {len(_failed)} failed")
    if _failed:
        for name in _failed:
            print(f"    - {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
