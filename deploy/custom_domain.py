"""Bind a custom domain to quotemind-api (P0 - see docs/deploy/custom-domain.md).

    python deploy/custom_domain.py --domain quotemind.cyberskill.world
    python deploy/custom_domain.py --domain quotemind.cyberskill.world --check

Why this exists at all: Function Compute injects `Content-Disposition: attachment` on every response
served from its default `*.fcapp.run` domain. `curl` ignores that header. A browser obeys it. So the
dashboard and /eval download instead of rendering, for everyone - including a judge - and every API
check we have ever run passed anyway, because none of them is a browser.

A custom domain removes the header. It also lifts the cross-domain-302 ban that forced the PDF route
to hand back a signed URL instead of redirecting to it (TASK-091).

This script does the half that does not need DNS: it creates the FC-side route. The CNAME is the
domain owner's to add, and the script prints exactly what to add and then verifies it.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from alibabacloud_fc20230330 import models as fc
from alibabacloud_fc20230330.client import Client as FcClient
from alibabacloud_sts20150401.client import Client as StsClient
from alibabacloud_tea_openapi import models as openapi

REGION = "ap-southeast-1"
FUNCTION = "quotemind-api"


def _config(endpoint: str) -> openapi.Config:
    try:
        key = os.environ["ALIBABA_CLOUD_ACCESS_KEY_ID"]
        secret = os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"]
    except KeyError as exc:
        sys.exit(f"{exc} is not set - source your .env first")
    return openapi.Config(access_key_id=key, access_key_secret=secret, endpoint=endpoint)


def account_id() -> str:
    sts = StsClient(_config(f"sts.{REGION}.aliyuncs.com"))
    return str(sts.get_caller_identity().body.account_id)


def cname_target(uid: str) -> str:
    return f"{uid}.{REGION}.fc.aliyuncs.com"


def _cert_config(cert: Path | None, key: Path | None, domain: str) -> fc.CertConfig | None:
    """FC will not accept `HTTPS` in `protocol` without a certificate - it is not optional there."""
    if cert is None or key is None:
        return None
    return fc.CertConfig(
        cert_name=domain.replace(".", "-"),
        certificate=cert.read_text(encoding="utf-8"),
        private_key=key.read_text(encoding="utf-8"),
    )


def create(domain: str, *, cert: Path | None = None, key: Path | None = None) -> None:
    client = FcClient(_config(f"{account_id()}.{REGION}.fc.aliyuncs.com"))

    route = fc.RouteConfig(
        routes=[
            fc.PathConfig(
                path="/*",  # the dashboard, /eval, /health and every API route are one app
                function_name=FUNCTION,
                qualifier="LATEST",
            )
        ]
    )

    # HTTP alone is a deliberate first step, not a shortcut. FC refuses `HTTPS` without a cert
    # ("CertConfig is required but not provided"), and a certificate needs its own domain-validation
    # round trip - which cannot even begin until the domain resolves somewhere. So: bind HTTP, prove
    # the page renders, then come back with a cert. The alternative is leaving the primary artifact
    # as a download for another day, which is worse than an http:// URL for a day.
    cert_config = _cert_config(cert, key, domain)
    protocol = "HTTP,HTTPS" if cert_config else "HTTP"

    try:
        client.create_custom_domain(
            fc.CreateCustomDomainRequest(
                body=fc.CreateCustomDomainInput(
                    domain_name=domain,
                    protocol=protocol,
                    route_config=route,
                    cert_config=cert_config,
                )
            )
        )
        print(f"created the custom domain: {domain}  ({protocol})")
    except Exception as exc:  # noqa: BLE001 - the SDK raises a bare Exception subclass
        message = str(exc)
        if "DomainNameAlreadyExists" in message or "already exist" in message.lower():
            client.update_custom_domain(
                domain,
                fc.UpdateCustomDomainRequest(
                    body=fc.UpdateCustomDomainInput(
                        protocol=protocol, route_config=route, cert_config=cert_config
                    )
                ),
            )
            print(f"the domain already existed; route and protocol updated: {domain}  ({protocol})")
        else:
            print(f"\nFC refused:\n  {message}\n")
            if "DomainNameNotResolved" in message:
                print("Add the CNAME below, wait for it to resolve, and run this again.")
            elif "CertConfig" in message:
                print("Pass --cert and --key to enable HTTPS, or omit them to bind HTTP only.")
            raise SystemExit(1) from exc


def check(domain: str) -> None:
    import socket  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    try:
        socket.gethostbyname(domain)
        print(f"  DNS      {domain} resolves")
    except OSError:
        print(f"  DNS      {domain} does NOT resolve yet - the CNAME has not propagated")
        return

    for scheme in ("http", "https"):
        url = f"{scheme}://{domain}/health"
        try:
            with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310
                disposition = response.headers.get("Content-Disposition")
                if disposition:
                    print(f"  {scheme.upper():8} still sends Content-Disposition: {disposition}")
                else:
                    print(f"  {scheme.upper():8} {response.status} - and NO attachment header")
        except Exception as exc:  # noqa: BLE001
            print(f"  {scheme.upper():8} not reachable yet ({type(exc).__name__})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True, help="e.g. quotemind.cyberskill.world")
    parser.add_argument("--check", action="store_true", help="only verify; create nothing")
    parser.add_argument("--cert", type=Path, help="PEM certificate chain; enables HTTPS")
    parser.add_argument("--key", type=Path, help="PEM private key; enables HTTPS")
    args = parser.parse_args()

    uid = account_id()
    target = cname_target(uid)

    if not args.check:
        create(args.domain, cert=args.cert, key=args.key)

    host = args.domain.split(".")[0]
    print("\nAdd this one record wherever the domain's DNS lives:\n")
    print("  Type   Name        Value")
    print(f"  CNAME  {host:<10}  {target}")
    print("\nThen verify:\n")
    check(args.domain)


if __name__ == "__main__":
    main()
