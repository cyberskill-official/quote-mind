#!/usr/bin/env python3
"""List the live Alibaba Cloud resources QuoteMind runs on - a console view, in text.

    .venv/bin/python deploy/list_resources.py     (or: make resources)

This is the machine-readable twin of an Alibaba Cloud Workbench screenshot. It uses
the same ap-southeast-1 credentials the app runs on to enumerate the actual deployed
resources - Function Compute functions and their triggers, OSS buckets, Tablestore
tables - and the account they live in (STS GetCallerIdentity). Every line below is
read back live from Alibaba Cloud on each run; nothing here is hardcoded.
"""
from __future__ import annotations

import datetime as _dt
import itertools
import json
import os
from pathlib import Path


def load_env(path: str = ".env") -> None:
    env = Path(path)
    if not env.exists():
        return
    for raw in env.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


load_env()

AK_ID = os.environ["ALIBABA_CLOUD_ACCESS_KEY_ID"]
AK_SECRET = os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"]
REGION = os.environ.get("REGION", "ap-southeast-1")
OSS_ENDPOINT = os.environ.get("OSS_ENDPOINT", f"https://oss-{REGION}.aliyuncs.com")
TS_ENDPOINT = os.environ.get("TABLESTORE_ENDPOINT", "")
TS_INSTANCE = os.environ.get("TABLESTORE_INSTANCE", "")


def rule(title: str) -> None:
    print(f"\n=== {title} ===")


def pick(d: dict, *keys: str) -> dict:
    return {k: d[k] for k in keys if k in d and d[k] is not None}


def epoch(value) -> str:
    try:
        return _dt.datetime.fromtimestamp(int(value), _dt.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%SZ"
        )
    except (TypeError, ValueError):
        return str(value)


def caller_identity() -> str:
    from alibabacloud_sts20150401.client import Client as StsClient
    from alibabacloud_tea_openapi import models as open_api_models

    cfg = open_api_models.Config(access_key_id=AK_ID, access_key_secret=AK_SECRET)
    cfg.endpoint = f"sts.{REGION}.aliyuncs.com"
    body = StsClient(cfg).get_caller_identity().body
    rule("Account (STS GetCallerIdentity)")
    print(f"  account id    {body.account_id}")
    print(f"  arn           {body.arn}")
    print(f"  identity type {body.identity_type}")
    return body.account_id


def fc_triggers(client, fc_models, function_name: str) -> list[dict]:
    try:
        body = client.list_triggers(function_name, fc_models.ListTriggersRequest(limit=50)).body
        return [t.to_map() for t in (body.triggers or [])]
    except Exception as exc:  # noqa: BLE001 - a failed trigger list is a note, not a crash
        print(f"  trigger       (list failed: {type(exc).__name__}: {exc})")
        return []


def fc_functions(account_id: str) -> list[dict]:
    from alibabacloud_fc20230330 import models as fc_models
    from alibabacloud_fc20230330.client import Client as FcClient
    from alibabacloud_tea_openapi import models as open_api_models

    cfg = open_api_models.Config(access_key_id=AK_ID, access_key_secret=AK_SECRET)
    cfg.endpoint = f"{account_id}.{REGION}.fc.aliyuncs.com"
    client = FcClient(cfg)
    body = client.list_functions(fc_models.ListFunctionsRequest(limit=100)).body
    funcs = [f.to_map() for f in (body.functions or [])]
    rule(f"Function Compute 3.0 - {len(funcs)} function(s) in {REGION}")
    dump: list[dict] = []
    for f in funcs:
        print(f"\n  function      {f.get('functionName')}")
        print(f"  runtime       {f.get('runtime')}")
        print(f"  handler       {f.get('handler')}")
        print(f"  memory        {f.get('memorySize')} MB")
        print(f"  last modified {f.get('lastModifiedTime')}")
        print(f"  arn           {f.get('functionArn', '')}")
        trigs = fc_triggers(client, fc_models, f.get("functionName"))
        for t in trigs:
            print(f"  trigger       {t.get('triggerName')} [{t.get('triggerType')}]")
        dump.append({
            "function": pick(f, "functionName", "runtime", "handler", "cpu",
                             "memorySize", "diskSize", "lastModifiedTime", "functionArn"),
            "triggers": [pick(t, "triggerName", "triggerType", "qualifier") for t in trigs],
        })
    return dump


def oss_buckets() -> list[dict]:
    import oss2
    from oss2.credentials import StaticCredentialsProvider

    auth = oss2.ProviderAuthV4(StaticCredentialsProvider(AK_ID, AK_SECRET))
    listed = oss2.Service(auth, OSS_ENDPOINT, region=REGION).list_buckets(
        prefix="quotemind", max_keys=100
    ).buckets
    rule(f"OSS - {len(listed)} bucket(s) matching 'quotemind' in {REGION}")
    dump: list[dict] = []
    for b in listed:
        bucket = oss2.Bucket(auth, OSS_ENDPOINT, b.name, region=REGION)
        keys = [o.key for o in itertools.islice(oss2.ObjectIterator(bucket), 8)]
        print(f"\n  bucket        {b.name}")
        print(f"  location      {b.location}")
        print(f"  created       {epoch(b.creation_date)}")
        print(f"  storage       {getattr(b, 'storage_class', '')}")
        print(f"  sample keys   {keys if keys else '(none listed)'}")
        dump.append({"name": b.name, "location": b.location,
                     "storageClass": getattr(b, "storage_class", None), "sampleKeys": keys})
    return dump


def tablestore_tables() -> list[str]:
    from tablestore import OTSClient

    tables = list(OTSClient(TS_ENDPOINT, AK_ID, AK_SECRET, TS_INSTANCE).list_table())
    rule(f"Tablestore - instance '{TS_INSTANCE}', {len(tables)} table(s)")
    for name in tables:
        print(f"  table         {name}")
    return tables


def main() -> int:
    print("QuoteMind - live Alibaba Cloud resource inventory")
    print(f"  region        {REGION}")
    print(f"  OSS endpoint  {OSS_ENDPOINT}")
    print(f"  TS endpoint   {TS_ENDPOINT}")
    inventory: dict = {"region": REGION}
    account_id = caller_identity()
    inventory["accountId"] = account_id
    inventory["functionCompute"] = fc_functions(account_id)
    inventory["oss"] = oss_buckets()
    inventory["tablestore"] = tablestore_tables()
    rule("Raw inventory (JSON)")
    print(json.dumps(inventory, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - operational script
    raise SystemExit(main())
