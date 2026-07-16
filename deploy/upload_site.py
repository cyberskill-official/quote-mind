"""TASK-106: publish the dashboard to OSS static website hosting.

Kept, but not the live path. This account has Block Public Access enabled on the artifacts bucket,
so OSS refuses `Put public object acl` and the upload fails - correctly, since that bucket holds
customer quote PDFs served by short-lived presigned URLs. The deployed dashboard is served by the
API itself (`GET /`), same-origin with the API it calls. This script remains useful for an account
with a bucket dedicated to public static content.

Original purpose follows.

The dashboard is one file with two placeholders (__API_BASE__, __API_TOKEN__). They are substituted
here, at upload time, so the checked-in source stays free of any deployment secret. The page is the
only public object in the artifacts bucket - quotes, traces, and outbox messages stay private and
are reached through short-lived presigned URLs (TASK-091).

    python deploy/upload_site.py --api-base https://<fc-url>

Prints the public site URL.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import oss2

from quotemind.cloud.oss import ArtifactStore
from quotemind.config.settings import require_settings

SITE_KEY = "web/index.html"
SOURCE = Path(__file__).resolve().parent.parent / "src" / "quotemind" / "web" / "index.html"


def render(html: str, *, api_base: str, api_token: str) -> str:
    """Substitute the deployment placeholders. Nothing else in the page is templated."""
    return html.replace("__API_BASE__", api_base.rstrip("/")).replace("__API_TOKEN__", api_token)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload the QuoteMind dashboard to OSS")
    parser.add_argument("--api-base", required=True, help="public base URL of the QuoteMind API")
    args = parser.parse_args()

    settings = require_settings()
    bucket = ArtifactStore.from_settings(settings).artifacts
    page = render(
        SOURCE.read_text(encoding="utf-8"),
        api_base=args.api_base,
        api_token=settings.demo_api_token,
    )

    bucket.put_object(
        SITE_KEY,
        page.encode("utf-8"),
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-cache",
            # The page alone is public; quotes, traces and outbox objects stay private.
            "x-oss-object-acl": oss2.OBJECT_ACL_PUBLIC_READ,
        },
    )
    host = settings.oss_endpoint.replace("https://", "")
    print(f"uploaded {SITE_KEY} ({len(page)} bytes)")
    print(f"https://{settings.oss_bucket_artifacts}.{host}/{SITE_KEY}")


if __name__ == "__main__":  # pragma: no cover - operational script
    main()
