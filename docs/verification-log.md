# Verification log

Records dependency pins and Appendix E surface checks, per QM-SPEC-001 "How to read"
item 6 and QM-REPO-001 §7 (`make verify`).

## 2026-07-11 — PR-1 dependency pins (resolved from PyPI)

Python target: 3.12 only (`requires-python = ">=3.12"`), per operator decision.

| Package | Pin | Notes |
|---|---|---|
| agentscope | ==1.0.9 | latest stable 1.0.x; requires Python >=3.11 (finding below) |
| tablestore-for-agent-memory | ==1.1.3 | confirmed present; requires >=3.9 |
| tablestore | >=6.4.7 | latest 6.4.8 |
| oss2 | >=2.19,<3 | latest 2.19.1 |
| openai | >=1.55,<3 | direct DashScope calls |
| weasyprint | ==68.* | resolves 68.1; 69.0 exists but spec pins 68 |
| mcp | >=1.28,<2 | spec "latest 1.x"; 2.0 is alpha, avoided |
| opentelemetry-sdk | >=1.30 | GenAI semconv opt-in via env |
| pypdfium2 | >=5.9 | raster fallback |
| openpyxl | >=3.1 | deterministic xlsx |
| pydantic | >=2.9 | v2 |
| pydantic-settings | >=2.7 | settings |
| fastapi | >=0.115 | web function |
| uvicorn | >=0.30 | local dev server |
| jinja2 | >=3.1 | PDF templates |
| python-ulid | >=3.0 | ULID ids |
| PyYAML | >=6 | model_prices.yaml |

Finding (logged, no change needed): agentscope 1.0.9 requires Python >=3.11, so the
spec's optional FC `python3.10` fallback (§4.4, open item 3) is not viable while
agentscope is a dependency. The chosen `3.12 only` target avoids this. If a region
without 3.12 ever forces 3.10, agentscope's floor blocks it and must be revisited.

Appendix E surface checks (tablestore-for-agent-memory MemoryStore/KnowledgeStore
signatures, live model availability probe, AgentScope structured-output smoke) are
scheduled for PR-4/PR-5 and are NOT run at PR-1.

Environment note: the PR-1 offline gate ran in a Python 3.10 sandbox with the light
test toolchain (no paid-API calls). The full `make setup && make test` on Python 3.12
runs in CI and on the FC runtime.
