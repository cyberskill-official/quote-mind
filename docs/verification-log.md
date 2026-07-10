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

## 2026-07-11 - PR-4 Appendix E.1 (tablestore-for-agent-memory 1.1.3 surface)

Verified against the installed wheel. The real module layout differs from the spec's assumed
paths (Appendix E notes "adjust to real paths"):
- MemoryStore: tablestore_for_agent_memory.memory.memory_store
- KnowledgeStore: tablestore_for_agent_memory.knowledge.knowledge_store
- Records: base.base_memory_store (Session, Message); base.base_knowledge_store (Document, DocumentHit)
- Filters: base.filter (Filters.eq / text_match / logical_and / vector_query, ...)
- Response[T]: base.common (hits, next_token)

Signatures the adapter relies on:
- KnowledgeStore(tablestore_client, vector_dimension, enable_multi_tenant=False, ...); put_document,
  get_document(id, tenant_id), vector_search(query_vector, top_k, tenant_id, ...),
  full_text_search(query, tenant_id, limit, ...), delete_document(id, tenant_id).
- MemoryStore(tablestore_client, ...); put_session, get_session(user_id, session_id),
  list_recent_sessions, put_message, list_messages(session_id, ...).
- Document(document_id, tenant_id='__default', text, embedding, metadata=scalars only) - each
  aggregate is stored as payload_json (str) plus filterable scalar fields.

E.2 (live model availability probe) and E.3 (AgentScope structured-output smoke) need a
DASHSCOPE_API_KEY and paid calls; NOT run here, pending operator credentials.
