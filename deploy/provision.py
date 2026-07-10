"""FR-004 provisioning: idempotently create OSS buckets and Tablestore tables/indexes.

Run with real Alibaba Cloud credentials in the environment:

    python deploy/provision.py

Creating a bucket that already exists and is owned by the caller is treated as success, so a
second run reports "already exists" for every resource and exits 0 (FR-004 AC). This script
performs live cloud calls and is not exercised by the offline test suite.
"""

from __future__ import annotations

import sys

import oss2
from oss2 import exceptions as oss2_exceptions
from oss2 import models as oss2_models

from quotemind.config.settings import Settings, require_settings
from quotemind.memory.store import MemoryFacade

_EXISTS_CODES = {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}


def _ensure_bucket(auth: oss2.ProviderAuthV4, endpoint: str, name: str, region: str) -> str:
    bucket = oss2.Bucket(auth, endpoint, name, region=region)
    try:
        bucket.create_bucket(oss2_models.BUCKET_ACL_PRIVATE)
    except oss2_exceptions.ServerError as exc:
        if exc.code in _EXISTS_CODES:
            return f"already exists {name}"
        raise
    return f"created {name} (private)"


def provision(settings: Settings) -> list[str]:
    auth = oss2.ProviderAuthV4(
        oss2.StaticCredentialsProvider(
            settings.alibaba_cloud_access_key_id,
            settings.alibaba_cloud_access_key_secret,
        )
    )
    report = [
        _ensure_bucket(auth, settings.oss_endpoint, settings.oss_bucket_inbox, settings.region),
        _ensure_bucket(auth, settings.oss_endpoint, settings.oss_bucket_artifacts, settings.region),
    ]
    MemoryFacade.from_settings(settings).init_tables()
    report.append("tablestore tables and indexes initialized (vector dim 1024)")
    return report


def main() -> int:
    for line in provision(require_settings()):
        print("provision:", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
