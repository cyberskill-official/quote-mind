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

## 2026-07-11 - PR-4 live verification (Appendix E.2/E.3 on real DashScope)

Model plane (DashScope international / Singapore) - PASS:
- E.2 model availability (openai-compatible base .../compatible-mode/v1): qwen3-max OK, qwen-plus OK,
  qwen3-vl-plus OK, qwen-max OK, text-embedding-v4 OK (dim=1024 confirmed). qwen-vl-ocr is reachable
  (it returned a 400 about message role because a text ping is the wrong shape for a vision-OCR model,
  not an availability error), so no TASK-012 fallback is needed.
- E.3 AgentScope 1.0.9 structured output: ReActAgent(qwen-plus) + DashScopeChatFormatter with
  structured_model returned metadata={'ok': True}. PASS.
- Finding: AgentScope's DashScopeChatModel uses the native dashscope API base, which for Singapore is
  https://dashscope-intl.aliyuncs.com/api/v1 (NOT the openai compatible-mode base). The agent layer
  must set base_http_api_url to that. A harmless DeprecationWarning notes DashScope converts tool
  choice 'required' to 'auto'.

Cloud storage plane - BLOCKED on account setup (not code):
- OSS create_bucket -> 403 UserDisable (EC 0003-00000801). Account-level: OSS not activated, overdue
  payment, or a security/verification hold. V4 signing and region were correct; the request reached OSS.
- Tablestore list_table -> OTSAuthFailed "The instance is not found". The AccessKey authenticated; the
  TABLESTORE_INSTANCE / TABLESTORE_ENDPOINT does not resolve to an existing instance (name/region or
  endpoint mismatch, or the instance is not fully created).
Provision (TASK-004) will complete once OSS is activated and the Tablestore instance name/endpoint match.

## 2026-07-11 - PR-4 Tablestore live verification (memory adapter)

Root cause of the earlier "instance not found": .env kept the .env.example default
TABLESTORE_INSTANCE=quotemind while the real instance is quotemind-demo. Corrected to
quotemind-demo (the endpoint was already correct).

Live against the real ap-southeast-1 instance:
- MemoryFacade.from_settings(...).init_tables() created the session, message, and knowledge tables.
  The session/message search indexes are skipped by the SDK because no search schema is supplied;
  QuoteMind uses point reads for those and the knowledge vector/FTS index for retrieval.
- put_customer -> get_customer round-trip returned an equal CustomerProfile. The memory adapter is
  live-verified: DM models write to and read back from real Tablestore correctly.

Still pending: OSS remains 403 UserDisable (account activation). provision.py creates the OSS buckets
before Tablestore, so the full TASK-004 run completes once OSS is activated.
