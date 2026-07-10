# QuoteMind — Architecture Specification

**Document ID:** QM-ARCH-001 · **Version:** 1.0.0 · **Date:** 2026-07-10 · **Status:** Approved
**Parent spec:** QM-SPEC-001 v1.0.0 (PRD+SRS). This document elaborates §4 of the parent spec. On any conflict, the parent spec wins.
**Deliverables in this pack:** this document, `diagrams/architecture.mmd` + `architecture.png` (submission diagram, SUB-03), `diagrams/pipeline-sequence.mmd` + `pipeline-sequence.png`.

---

## 1. Purpose and audience

This document gives implementers (Claude Cowork agents) and hackathon judges a complete, layered view of how QuoteMind is put together: from the system-in-context level down to component contracts, data flow, deployment topology, and failure behavior. The rendered `architecture.png` satisfies the hackathon requirement for "an Architecture Diagram showing a clear visual representation of your system (e.g., how Qwen Cloud connects to your backend, database, and frontend)".

## 2. Architecture at a glance

QuoteMind is a serverless, event-driven, multi-agent pipeline with one durable pause point.

- **Two Function Compute functions** share one codebase: `quotemind-api` (HTTP) and `quotemind-ingest` (OSS trigger). Both call the same `run_quote(quote_id)` orchestrator entry.
- **Eight agents** (AgentScope 1.0 ReAct pattern) do the work; exactly one of them, the PricingEngine, is deterministic code wrapped as an agent so money math is provably correct and still appears as a traced pipeline step.
- **Qwen Cloud (DashScope international, Singapore)** supplies four model capabilities: reasoning/drafting (`qwen3-max`), fast classification and text extraction (`qwen-plus`), scanned-document vision (`qwen-vl-ocr`, fallback `qwen3-vl-plus`), and embeddings (`text-embedding-v4`, dim 1024).
- **Tablestore** is the single source of durable truth: agent sessions and messages (MemoryStore), catalog/customers/episodic/SOP knowledge with hybrid vector + full-text search (KnowledgeStore), plus plain tables for quote records, the audit hash-chain, and the quote-number counter.
- **OSS** holds binary artifacts: inbound RFQ files, rasterized pages, generated PDFs, trace JSON, and the stub outbox; it also statically hosts the dashboard SPA.
- **The HITL gate is a state, not a wait.** When a quote reaches `pending_approval`, the invocation ends. Approval hours later starts a fresh invocation that reloads state from Tablestore and continues. Nothing depends on a live process.

## 3. C4 Level 1 — System context

| Element | Type | Interaction |
|---|---|---|
| Buyer | Person (external) | Sends RFQs via API upload, OSS drop (simulating email attachment routing), or pasted email text. Receives the bilingual quote email. |
| Sales Manager | Person (internal) | Reviews drafts in the dashboard; approves, rejects, or revises with instructions; may waive blocking flags with audited reason. |
| Judge / API client | Person (external) | Reads the repo, calls `/health` and demo endpoints, watches the demo. |
| QuoteMind | Software system | Converts RFQs to approved, dispatched bilingual quotations. |
| Alibaba Cloud | External platform | DashScope (Qwen models), Function Compute, OSS, Tablestore, DirectMail. |

Trust boundary: everything inside Alibaba Cloud `ap-southeast-1`; the only public surfaces are the FC HTTP endpoint (Bearer-gated except `/health`), the OSS static site, and time-limited presigned URLs.

## 4. C4 Level 2 — Containers

See `architecture.png`. Containers and their contracts:

| # | Container | Runtime | Provides | Consumes |
|---|---|---|---|---|
| C-01 | `quotemind-api` | FC 3.0, Python 3.12, HTTP trigger | REST API-01..13; state machine; orchestrator entry | Tablestore, OSS, DashScope, DirectMail |
| C-02 | `quotemind-ingest` | FC 3.0, OSS object-created trigger (`quotemind-inbox`, prefix `rfq/`) | Quote registration from file drops; same orchestrator entry | OSS event payload, Tablestore |
| C-03 | Review dashboard | Static SPA on OSS website hosting | Queue, detail, trace, approval UI | C-01 REST + Bearer |
| C-04 | Agent runtime | AgentScope 1.0 in-process (C-01/C-02) | ReAct agents, Toolkit, MsgHub, PlanNotebook | DashScope via `DashScopeChatModel`; tools |
| C-05 | MCP servers | Python FastMCP, stdio, in-process | `catalog-mcp` (search/get product), `email-mcp` (send, stub inbox) | KnowledgeStore, DirectMail/stub |
| C-06 | Memory layer | `tablestore-for-agent-memory` 1.1.3 | MemoryStore sessions/messages; KnowledgeStore vector+FTS | Tablestore instance |
| C-07 | Object store | OSS buckets `quotemind-inbox`, `quotemind-artifacts` | Files, pages, PDFs, traces, outbox; presigned GET (≤10 min) | — |
| C-08 | Model gateway | DashScope intl OpenAI-compatible | chat/vision/embeddings | `DASHSCOPE_API_KEY` |
| C-09 | Email dispatch | DirectMail SMTP 465 (or stub) | Outbound quote email | Verified sender |
| C-10 | Observability | OTel SDK + trace persister | GenAI spans; `trace.json` per quote; cost accounting | stdout/OTLP; OSS |
| C-11 | Eval harness | pytest + CLI | 30-case metrics, baseline comparison, CI smoke | Fixtures, cassettes |

## 5. Component view — the agent pipeline

Order and responsibilities (see `pipeline-sequence.png`):

1. **Orchestrator (AGT-01, qwen3-max + PlanNotebook).** Owns the run and the state machine. Fast path for trivial quotes; planned path (PlanNotebook subtasks) when multi-document, >10 lines, or flags exist. Never touches money; never skips the critic.
2. **IntakeClassifier (AGT-02, qwen-plus).** language / doc_type / urgency / customer resolution via `lookup_customer` tool. Emits `IntakeResult`.
3. **DocumentParser (AGT-03).** Route by doc_type: text → qwen-plus structured extraction; pdf/image → rasterize (pypdfium2, 200 DPI, ≤10 pages, ≤2560 px) then qwen-vl-ocr per page, JSON-fenced output, page-merge with dedupe; xlsx → openpyxl deterministic with LLM only for ambiguous headers. Emits `RFQExtraction` with per-line confidence and source spans. Gate FR-034 stops empty/invalid extractions.
4. **CatalogMatcher (AGT-04).** Hybrid retrieval per line: `vector_search(top_k=8, tenant "catalog")` + `full_text_search`, reciprocal-rank fusion, then qwen3-max selects from candidates only. Confidence < 0.75 or spec conflict ⇒ `needs_confirmation` with ≤3 alternatives and a bilingual reason. Out-of-catalog ⇒ `no_match`, preserved for HITL.
5. **PricingEngine (AGT-05, deterministic).** Pure `Decimal` functions: tier price → discount → line totals → per-rate VAT (8% IT default, 10% telecom exclusion) → totals → margin vs floor. Zero LLM involvement; 100% branch-covered.
6. **QuoteDrafter (AGT-06, qwen3-max).** Fills only `BilingualText` fields around code-injected, read-only numbers; grounds terms in SOP memory; cites up to 3 episodic memories retrieved with `similarity × 0.5^(age/90d) × importance` scoring under a 1200-token budget. Numeric checksum on output; one retry then fail.
7. **CriticValidator (AGT-07).** Code recomputes every figure via the same engine (exact match required); code checks bilingual numeric parity and encoding; qwen3-max writes the bilingual review note and checks qualitative policy. Emits blocking/non-blocking flags.
8. **HITL gate.** Status `pending_approval`; invocation ends. Approve (with audited waivers if blocking flags), reject, or revise (instruction → Drafter loop, max 3).
9. **DispatchAgent (AGT-08).** Jinja2 → WeasyPrint bilingual PDF (Be Vietnam Pro embedded) → OSS → presigned URL → DirectMail SMTP (or stub `.eml` to OSS) → episodic memory write → audit close.

Cross-cutting: every step appends a MemoryStore `Message`, an `AuditEvent` (sha256 hash-chained), and OTel GenAI spans (`chat qwen3-max`, `execute_tool vector_search`, `invoke_agent CatalogMatcher`) with token and cost attributes.

## 6. Data architecture

**Stores and ownership**

| Store | Contents | Owner FRs |
|---|---|---|
| MemoryStore (`qm_*` SDK tables) | `Session(user_id, session_id=quote_id)`; per-step `Message` | FR-047, FR-081 |
| KnowledgeStore (table + search index, vector dim 1024, FTS on `text`) | tenants `catalog` (60 SKUs), `customers` (8), `episodic:{customer_id}` (grows), `sop` (10) | FR-040..046, 048 |
| `qm_quotes` (OTS wide-column, pk quote_id, index on status) | QuoteRecord incl. totals_json, flags, revision, idempotency hash | FR-024, 080 |
| `qm_audit` (pk quote_id+seq) | Hash-chained AuditEvent log | FR-094 |
| `qm_counters` | Atomic per-year quote numbering `QM-YYYY-NNNN` | FR-062 |
| OSS `quotemind-inbox` | `rfq/...` inbound files (trigger source) | FR-021 |
| OSS `quotemind-artifacts` | `quotes/*.pdf`, `pages/{quote_id}/*.png`, `traces/{quote_id}.json`, `outbox/*.eml` | FR-090..093, 111 |

**Memory lifecycle (Track-1 depth).** Write on decision (approve/edit/reject) with initial importance from outcome and deal size; retrieve top-3 by effective score; garbage-collect below effective ceiling 0.05; compact >50 memories per customer into an LLM-written profile document. All retrievals are cited in the trace and surfaced in the UI.

**Consistency model.** Single-writer per quote (orchestrator invocation) enforced by conditional update on `qm_quotes.status`; approval races resolve by state-machine legality (second writer gets 409). Audit chain gives tamper-evidence, not distributed consensus - adequate for demo scope and documented as such.

## 7. Deployment topology

```
Region ap-southeast-1 (Singapore)
├── Function Compute 3.0
│   ├── quotemind-api      (HTTP trigger, 1024 MB, 300 s, initializer: model check FR-012)
│   └── quotemind-ingest   (OSS trigger, same image/code)
├── OSS
│   ├── quotemind-inbox        (private; event → ingest)
│   └── quotemind-artifacts    (private; presigned GET ≤ 600 s; static site prefix /app for SPA)
├── Tablestore instance quotemind (serverless; MemoryStore/KnowledgeStore tables + search index)
├── DirectMail (verified sender; SMTP 465) — optional, stub fallback
└── Model Studio / DashScope intl endpoint (Singapore)
```

Deploy: `s deploy` from `deploy/s.yaml` (edition 3.0.0, component fc3) + `python deploy/provision.py` (idempotent buckets/tables/indexes). WeasyPrint native libs (Pango/Cairo) ship via FC layer; if the layer size limit bites, `deploy/Dockerfile.pdf` switches the function to a custom container (documented fallback, risk table item 3 in parent spec).

## 8. Security architecture

- Secrets only via FC environment variables; `.env.example` documents names; nothing secret in the repo.
- RAM user scoped to: OSS rw on the two buckets, OTS rw on instance `quotemind`, DirectMail send. No account-level keys in code paths.
- API auth: static Bearer (`DEMO_API_TOKEN`) on all `/api/*` except `/health` — demo-grade by design, roadmap notes real IAM.
- Buckets private; presigned URLs ≤ 10 minutes, `slash_safe=True`.
- PII posture: prompts/responses excluded from persisted traces unless `TRACE_CONTENT=1`; customer data stays in-region; 90-day purge script; `docs/privacy.md` maps categories/purpose/retention to Vietnam PDPL (effective 2026-01-01).
- Audit: hash-chained events make post-hoc tampering evident; waivers of blocking flags always carry actor + reason.

## 9. Failure model and degradation

| Failure | Behavior |
|---|---|
| Model transient error | Retry ×2 exponential backoff (1 s, 4 s); then error code (MODEL_UNAVAILABLE etc.), quote → `failed_*` with reason |
| Primary model missing at cold start | FR-012 substitutes frozen fallback (`qwen3-max`→`qwen-max`, `qwen-vl-ocr`→`qwen3-vl-plus`), logs WARN, `/health` reports it |
| One page fails vision | Partial extraction + flag; run continues (NFR-004) |
| Empty/invalid extraction | `needs_clarification`, never guess quantities (FR-034) |
| Draft numeric checksum mismatch | One redraft, then DRAFT_FAIL (guardrail AGT-06) |
| Critic recompute mismatch | `critic_failed`, blocking (FR-070) |
| DirectMail unavailable | `MAIL_TRANSPORT=stub` writes `.eml` to OSS, audited `sent_stub` (FR-093) |
| FC instance death mid-run | State machine + session messages allow re-entry; `pending_approval` is durable by construction (FR-081) |
| Revise loop | Hard cap 3, then `needs_manual` |

## 10. Rubric mapping of architectural choices

| Choice | Rubric axis served |
|---|---|
| All-first-party Alibaba stack (AgentScope + DashScope + Tablestore agent-memory + FC + OSS + DirectMail) | Technical Depth: "sophisticated use of QwenCloud APIs" |
| Deterministic pricing core + independent critic recompute | Technical Depth + Problem Value: production-readiness over toy demos |
| Importance-decay episodic memory with citations | Innovation (Track-1 techniques inside a business agent) |
| Planner/worker/critic + measured single-agent baseline | Innovation (Track-3 measurable gain) |
| Durable HITL across serverless invocations | Technical Depth (non-trivial state engineering) + Track-4 checkpoint requirement |
| Per-quote reasoning trace persisted and rendered | Presentation (visible decision trail) |
| Bilingual VI/EN pipeline end-to-end | Problem Value + Innovation (Qwen multilingual strength) |

## 11. Diagram pack usage

- `architecture.png` — the submission diagram (SUB-03). Embed at the top of README and `docs/architecture.md`; show at ~2:20 in the demo video.
- `pipeline-sequence.png` — supporting diagram for docs and the blog post; ideal for explaining the durable pause.
- Sources are Mermaid; re-render with: `mmdc -i <file>.mmd -o <file>.png -w 2200 -b white --scale 2` (repo pins mermaid-cli; CI regenerates on change so PNGs never drift from source).

## 12. Open items tracked against parent spec

1. Exact `agentscope` 1.0.x minor pin → set at bootstrap, record in `docs/verification-log.md` (parent §4.4).
2. `tablestore-for-agent-memory` constructor/init signatures → Appendix E check before EP-04 coding (parent risk table).
3. FC Python 3.12 availability in `ap-southeast-1` → confirm at deploy; fallback `python3.10` is code-compatible.
4. WeasyPrint layer vs container decision → resolve by Day 8 milestone.

*End of QM-ARCH-001 v1.0.0.*
