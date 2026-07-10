# QuoteMind

Autonomous RFQ-to-quote autopilot for Vietnamese IT reselling. CyberSkill's entry for the
Qwen Cloud Hackathon, Track 4 (Autopilot Agent).

![Track 4](https://img.shields.io/badge/Qwen%20Hackathon-Track%204%20Autopilot-45210E)
![License](https://img.shields.io/badge/license-Apache--2.0-F4BA17)
![Python](https://img.shields.io/badge/python-3.12-blue)

QuoteMind ingests an RFQ (Vietnamese or English text, PDF, scan, or Excel), extracts line
items, matches a seeded catalog, prices deterministically with 2026 Vietnamese VAT, drafts a
bilingual quote, and stops at a human approval gate before dispatch. The authoritative
specification lives in [`docs/spec/`](docs/spec/) (QM-SPEC-001); the repository blueprint is
QM-REPO-001.

## Quickstart

Requires Python 3.12.

```bash
cp .env.example .env      # fill in your keys (never commit .env)
make setup                # install the package + dev toolchain
make test                 # offline unit tests (no paid-API calls)
make dev                  # local API on http://localhost:9000  (GET /health)
```

`make setup` installs the light core plus the dev toolchain, which is all PR-1 needs.
The full runtime stack (agents, memory, cloud, parse, pdf, obs) is pinned in
`pyproject.toml` as extras and installed as later phases need it; `make setup-all` installs
everything.

## Build status

Bootstrapped in the PR order from the blueprint (QM-REPO-001 section 9):

- PR-1 (this): scaffold, config, structured logging, `/health`, bearer auth. Done.
- PR-2: data models and the quote state machine.
- PR-3: deterministic pricing and the amount-in-words converter.
- PR-4: memory adapter over `tablestore-for-agent-memory` (Appendix E verified).
- PR-5: Alibaba Cloud deployment proof and `deploy/s.yaml`.

The Alibaba Cloud deployment-proof module (SUB-02) arrives in PR-5:
`python -m quotemind.cloud.alibaba_proof`.

## License and tracking

Apache-2.0; see [`LICENSE`](LICENSE). Progress and decisions are in
[`BUILD_LOG.md`](BUILD_LOG.md); dependency pins in
[`docs/verification-log.md`](docs/verification-log.md); the FR-to-test map in
[`docs/traceability.csv`](docs/traceability.csv).
