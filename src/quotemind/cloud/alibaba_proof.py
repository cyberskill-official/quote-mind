"""TASK-005 / SUB-02: proof of Alibaba Cloud usage, in one runnable file.

    python -m quotemind.cloud.alibaba_proof

The hackathon asks for "a link to a code file demonstrating use of Alibaba Cloud services and APIs".
This is that file. It is deliberately a *single* module with no clever indirection, so a judge can
read it top to bottom in two minutes and see exactly which Alibaba services QuoteMind depends on and
how it calls them. It exercises the real services against the real Singapore region - there is
nothing mocked here, and every PASS line below is a round-trip that actually happened.

    DashScope (Model Studio, Singapore)   chat completion + text embedding
    OSS (Object Storage Service)          put -> presigned GET -> HTTP fetch -> delete
    Tablestore                            create table -> put row -> get row -> delete row

Each check is written to be *self-verifying*: it does not just call the API and trust a 200, it
asserts on the content that came back. An embedding check that only asserted "no exception" would
pass even if the service returned a vector of the wrong dimension into a system whose index is
pinned at 1024 - which would then fail silently at retrieval time, months later. So the checks
assert the properties QuoteMind actually relies on.

Exits 0 only if every service passes. Anything else exits 1, because a partial proof is not a proof.
"""

from __future__ import annotations

import ssl
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

import certifi
import oss2
from openai import OpenAI
from oss2.credentials import StaticCredentialsProvider
from tablestore import (
    CapacityUnit,
    Condition,
    OTSClient,
    OTSServiceError,
    ReservedThroughput,
    Row,
    RowExistenceExpectation,
    TableMeta,
    TableOptions,
)

from ..config.models import EMBED_DIMENSIONS, MODEL_EMBED, MODEL_PLANNER
from ..config.settings import Settings, require_settings

PROOF_TABLE = "qm_proof"
PROOF_KEY = "proof/alibaba_proof.txt"


@dataclass
class Check:
    service: str
    detail: str
    passed: bool


def _report(checks: list[Check]) -> int:
    print()
    for check in checks:
        mark = "PASS" if check.passed else "FAIL"
        print(f"[{mark}] {check.service:<12} {check.detail}")
    failed = [check for check in checks if not check.passed]
    print()
    if failed:
        print(f"{len(failed)} of {len(checks)} checks FAILED")
        return 1
    print(f"all {len(checks)} Alibaba Cloud checks PASSED")
    return 0


# --- 1. DashScope: the model gateway (Model Studio, Singapore) -----------------------------------
def check_dashscope(settings: Settings) -> list[Check]:
    """Chat + embeddings against DashScope international, via the OpenAI-compatible endpoint."""
    client = OpenAI(api_key=settings.dashscope_api_key, base_url=settings.dashscope_base_url)
    checks: list[Check] = []

    # Chat. Asking for a fact with one right answer, so a garbled or empty response is visible.
    started = time.perf_counter()
    completion = client.chat.completions.create(
        model=MODEL_PLANNER,
        messages=[{"role": "user", "content": "Reply with exactly one word: OK"}],
        max_tokens=8,
    )
    answer = (completion.choices[0].message.content or "").strip()
    elapsed = int((time.perf_counter() - started) * 1000)
    usage = completion.usage
    checks.append(
        Check(
            "DashScope",
            f"chat {MODEL_PLANNER}: {answer!r} in {elapsed} ms "
            f"({usage.prompt_tokens if usage else 0} -> "
            f"{usage.completion_tokens if usage else 0} tokens)",
            passed="OK" in answer.upper(),
        )
    )

    # Embeddings. The dimension assertion is the point: the Tablestore vector index is pinned at
    # 1024, so a model returning any other width would corrupt retrieval rather than error.
    response = client.embeddings.create(
        model=MODEL_EMBED,
        input=["Laptop Dell Latitude 5450, Core i5, RAM 16GB"],
        dimensions=EMBED_DIMENSIONS,
    )
    vector = response.data[0].embedding
    checks.append(
        Check(
            "DashScope",
            f"embed {MODEL_EMBED}: {len(vector)} dims (index requires {EMBED_DIMENSIONS})",
            passed=len(vector) == EMBED_DIMENSIONS,
        )
    )
    return checks


# --- 2. OSS: object storage for RFQ inputs and quote PDFs ----------------------------------------
def check_oss(settings: Settings) -> list[Check]:
    """Full artifact round-trip: put -> presign -> fetch over plain HTTPS -> delete."""
    auth = oss2.ProviderAuthV4(
        StaticCredentialsProvider(
            access_key_id=settings.alibaba_cloud_access_key_id,
            access_key_secret=settings.alibaba_cloud_access_key_secret,
        )
    )
    bucket = oss2.Bucket(
        auth, settings.oss_endpoint, settings.oss_bucket_artifacts, region=settings.region
    )
    checks: list[Check] = []

    # Vietnamese payload on purpose: an encoding bug anywhere in the storage path shows up here
    # rather than in a customer's quote.
    payload = "QuoteMind proof - báo giá tiếng Việt có dấu ✓".encode()
    bucket.put_object(PROOF_KEY, payload)
    target = f"oss://{settings.oss_bucket_artifacts}/{PROOF_KEY}"
    checks.append(Check("OSS", f"put {target} ({len(payload)} B)", True))

    # A V4-signed URL is how the dashboard and the quote email reach a private object (TASK-091).
    url = bucket.sign_url("GET", PROOF_KEY, 120, slash_safe=True)
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(url, timeout=30, context=context) as response:  # noqa: S310
        fetched = response.read()
        status = response.status
    checks.append(
        Check(
            "OSS",
            f"presigned GET -> HTTP {status}, {len(fetched)} B, bytes match: {fetched == payload}",
            passed=status == 200 and fetched == payload,
        )
    )

    bucket.delete_object(PROOF_KEY)
    exists = bucket.object_exists(PROOF_KEY)
    checks.append(Check("OSS", f"delete -> object_exists={exists}", passed=not exists))
    return checks


# --- 3. Tablestore: the durable state and the agent memory ---------------------------------------
def check_tablestore(settings: Settings) -> list[Check]:
    """Create (idempotently) -> put -> get -> delete against a throwaway table."""
    client = OTSClient(
        settings.tablestore_endpoint,
        settings.alibaba_cloud_access_key_id,
        settings.alibaba_cloud_access_key_secret,
        settings.tablestore_instance,
    )
    checks: list[Check] = []

    try:
        client.create_table(
            TableMeta(PROOF_TABLE, [("proof_id", "STRING")]),
            TableOptions(),
            ReservedThroughput(CapacityUnit(0, 0)),
        )
        created = "created"
    except OTSServiceError as exc:
        if exc.get_error_code() != "OTSObjectAlreadyExist":
            raise
        created = "already exists"
    checks.append(Check("Tablestore", f"table {PROOF_TABLE}: {created}", True))

    proof_id = f"proof-{int(time.time())}"
    note = "Báo giá đã được kiểm tra số học tự động"  # diacritics survive the wire, or they do not
    client.put_row(
        PROOF_TABLE,
        Row([("proof_id", proof_id)], [("note", note), ("region", settings.region)]),
        Condition(RowExistenceExpectation.IGNORE),
    )

    _, row, _ = client.get_row(PROOF_TABLE, [("proof_id", proof_id)])
    columns: dict[str, Any] = {name: value for name, value, *_ in (row.attribute_columns or [])}
    read_back = columns.get("note")
    checks.append(
        Check(
            "Tablestore",
            f"put + get row {proof_id}: note round-tripped byte-exact: {read_back == note}",
            passed=read_back == note,
        )
    )

    client.delete_row(
        PROOF_TABLE,
        Row([("proof_id", proof_id)]),
        Condition(RowExistenceExpectation.IGNORE),
    )
    _, gone, _ = client.get_row(PROOF_TABLE, [("proof_id", proof_id)])
    checks.append(
        Check("Tablestore", f"delete row -> row is None: {gone is None}", passed=gone is None)
    )
    return checks


def main() -> int:
    settings = require_settings()
    print("QuoteMind - proof of Alibaba Cloud usage (TASK-005 / SUB-02)")
    print(f"  region        {settings.region}")
    print(f"  DashScope     {settings.dashscope_base_url}")
    print(f"  OSS           {settings.oss_endpoint}")
    print(f"  Tablestore    {settings.tablestore_endpoint}")
    print(f"  instance      {settings.tablestore_instance}")

    checks: list[Check] = []
    for name, probe in (
        ("DashScope", check_dashscope),
        ("OSS", check_oss),
        ("Tablestore", check_tablestore),
    ):
        try:
            checks.extend(probe(settings))
        except Exception as exc:  # noqa: BLE001 - a broken service is a FAIL line, not a traceback
            checks.append(Check(name, f"{type(exc).__name__}: {exc}", passed=False))

    return _report(checks)


if __name__ == "__main__":  # pragma: no cover - operational script
    sys.exit(main())
