"""Issue a Let's Encrypt certificate for the custom domain, and bind it to Function Compute.

    python deploy/issue_cert.py --domain quotemind.cyberskill.world --email you@example.com

Nothing here is manual and nothing here needs DNS. The domain already resolves to Function Compute
over HTTP - that is what removed FC's forced `Content-Disposition: attachment` and turned the
dashboard from a download back into a page. Let's Encrypt's HTTP-01 challenge asks exactly one
question: *does this domain serve what you say it serves?* We are now in a position to answer it.

The flow:

  1. order a certificate for the domain
  2. Let's Encrypt hands us a token and a key authorization
  3. we write the key authorization to OSS under `acme/{token}`
  4. `GET /.well-known/acme-challenge/{token}` serves it (see api/app.py)
  5. Let's Encrypt fetches that URL over HTTP and validates
  6. we get a certificate, and hand it to FC, which flips the domain to HTTPS

The challenge lives in OSS rather than in an environment variable because an env var would mean a
function redeploy per challenge - and a redeploy inside an ACME validation window is a race nobody
should have to run. This way renewal is a `put_object` and a `curl`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from acme import challenges, client, crypto_util, messages
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from josepy import JWKRSA

from quotemind.cloud import ArtifactStore
from quotemind.config.settings import require_settings

DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"
USER_AGENT = "quotemind/1.0"
OUT = Path("deploy/certs")


def _account_key() -> JWKRSA:
    return JWKRSA(key=rsa.generate_private_key(public_exponent=65537, key_size=2048))


def _csr(domain: str) -> tuple[bytes, bytes]:
    """A fresh key and a CSR for it. The key never leaves this machine except into FC."""
    import cryptography.x509 as x509  # noqa: PLC0415

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return pem_key, csr.public_bytes(serialization.Encoding.PEM)


def _serves(url: str, expected: str, tries: int = 12) -> bool:
    """Do not hand the token to Let's Encrypt until we can fetch it ourselves."""
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
                if response.read().decode().strip() == expected:
                    print(f"  the challenge is being served (attempt {attempt + 1})")
                    return True
        except Exception:  # noqa: BLE001, S110 - OSS is eventually consistent; that is what the loop is for
            pass
        time.sleep(5)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--email", required=True, help="Let's Encrypt sends expiry warnings here")
    parser.add_argument(
        "--staging", action="store_true", help="use the staging CA (rate-limit safe)"
    )
    args = parser.parse_args()

    directory_url = (
        "https://acme-staging-v02.api.letsencrypt.org/directory" if args.staging else DIRECTORY
    )

    settings = require_settings()
    artifacts = ArtifactStore.from_settings(settings)

    print(f"ordering a certificate for {args.domain}")
    key = _account_key()
    net = client.ClientNetwork(key, user_agent=USER_AGENT)
    directory = client.ClientV2.get_directory(directory_url, net)
    acme = client.ClientV2(directory, net=net)
    acme.new_account(
        messages.NewRegistration.from_data(email=args.email, terms_of_service_agreed=True)
    )

    pem_key, pem_csr = _csr(args.domain)
    order = acme.new_order(pem_csr)

    for authorization in order.authorizations:
        http01 = next(
            c for c in authorization.body.challenges if isinstance(c.chall, challenges.HTTP01)
        )
        token = http01.chall.encode("token")
        answer = http01.chall.validation(key)

        print(f"  writing the challenge to OSS: acme/{token}")
        artifacts.put_acme_challenge(token, answer)

        url = f"http://{args.domain}/.well-known/acme-challenge/{token}"
        if not _serves(url, answer):
            sys.exit(
                f"the site is not serving {url}\n"
                "Is the ACME route deployed? It is in api/app.py, and it has to be LIVE."
            )

        print("  telling Let's Encrypt to validate")
        acme.answer_challenge(http01, http01.response(key))

    print("  waiting for the certificate")
    finalized = acme.poll_and_finalize(order)

    OUT.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = OUT / f"{args.domain}.crt", OUT / f"{args.domain}.key"
    cert_path.write_text(finalized.fullchain_pem, encoding="utf-8")
    key_path.write_text(pem_key.decode(), encoding="utf-8")
    key_path.chmod(0o600)
    print(f"  certificate: {cert_path}")

    parsed = crypto_util.parse_pem_chain(finalized.fullchain_pem)[0]
    print(f"  valid until: {parsed.not_valid_after_utc:%d %b %Y}")

    print("\nbinding it to Function Compute")
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "deploy/custom_domain.py",
            "--domain",
            args.domain,
            "--cert",
            str(cert_path),
            "--key",
            str(key_path),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
