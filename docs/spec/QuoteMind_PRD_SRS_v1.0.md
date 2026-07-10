# QuoteMind — Unified Product Requirements Document (PRD) & Software Requirements Specification (SRS)

**Autonomous RFQ-to-Quote Autopilot for IT Reselling — Qwen Cloud Hackathon, Track 4 (Autopilot Agent)**

---

## Document control

| Field | Value |
|---|---|
| Document ID | QM-SPEC-001 |
| Version | 1.0.0 |
| Status | Approved for implementation |
| Date | 2026-07-10 |
| Owner | Stephen Cheng (Trịnh Thái Anh), CEO, CyberSkill Software Solutions Consultancy and Development JSC |
| Author | CyberSkill product engineering (AI-assisted) |
| Audience | AI coding agents (Claude Cowork) and human reviewers |
| Consumption model | This document is the single source of truth. It is designed to be decomposed into feature requests (FRs). Each FR-XXX below is atomic and independently implementable once its listed dependencies are met. |
| Language of record | English (product UI and generated quotes are bilingual Vietnamese/English) |
| License of resulting code | Apache-2.0 (hackathon requires a visible open-source license) |

### Change log

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-07-10 | Initial approved specification |

### How to read this document (instructions for Claude Cowork)

1. Requirements are numbered `FR-NNN` (functional), `NFR-NNN` (non-functional), `AGT-NN` (agent behavior specs), `DM-NN` (data model), `API-NN` (API contracts), `EV-NN` (evaluation), `SUB-NN` (hackathon submission compliance).
2. Every FR has: priority (`P0` = must ship for demo, `P1` = should ship, `P2` = stretch), a normative statement ("The system shall..."), acceptance criteria in Given/When/Then form, and dependencies.
3. Implement in epic order EP-01 → EP-13 unless the dependency graph says otherwise. The critical path is EP-01 → EP-03 → EP-04 → EP-05 → EP-06 → EP-09 (one vertical slice), then EP-07, EP-08, EP-10 through EP-13.
4. The section "DO-NOT-CHANGE registry" lists identifiers, schemas, and contracts that must never be renamed or restructured without a spec version bump. Treat them as frozen.
5. Code examples in this spec are normative for signatures and naming, illustrative for bodies.
6. Where the spec says "confirm against installed wheel", the implementing agent must run the verification snippet in Appendix E before writing dependent code, and record the result in `docs/verification-log.md`.

---

## 1. Introduction

### 1.1 Purpose

This document specifies QuoteMind, an autonomous multi-agent system that converts inbound customer requests for quotation (RFQs) into approved, dispatched, bilingual (Vietnamese/English) sales quotations for an IT hardware and software reselling business. It merges the PRD (why, for whom, what) and the SRS (exactly what to build, to what contract, with what quality gates) into one machine-consumable specification.

QuoteMind is CyberSkill's entry for the Qwen Cloud Hackathon, Track 4 (Autopilot Agent). Track 4 rewards agents that "automate real-world business workflows end-to-end", "handle ambiguous inputs, invoke external tools, and incorporate human-in-the-loop checkpoints at critical decision points", with "emphasis on production-readiness over toy demos". Every architectural decision below serves both the judging rubric (Technical Depth 30%, Innovation 30%, Problem Value 25%, Presentation 15%) and post-hackathon reuse as a CyberSkill client offering.

### 1.2 Scope

**In scope (v1.0, hackathon build):**

- Ingestion of RFQs from three channels: direct upload via dashboard/API, OSS bucket drop (simulating email-attachment routing), and raw email text paste.
- Parsing of RFQ content in Vietnamese and English from: plain text email bodies, PDF documents (digital and scanned/photographed), and Excel attachments.
- Structured extraction of line items (product description, quantity, unit, target specs, requested delivery).
- Fuzzy catalog matching against a seeded IT product catalog with hybrid vector plus full-text retrieval and customer-tier pricing.
- Deterministic pricing computation: unit prices, discounts by customer tier, VAT per Vietnamese 2026 rules (8% default for IT goods under Nghị định 174/2025/NĐ-CP, configurable per line), VND primary currency with optional USD dual display.
- Bilingual quote drafting and rendering to a professional PDF (báo giá conventions) with CyberSkill-style visual identity.
- A critic/validation agent that independently recomputes totals and checks policy (margin floor, VAT category, missing items).
- Human-in-the-loop approval gate with persistent state across serverless invocations: approve, reject, or revise-with-instructions.
- Dispatch: PDF stored on OSS, presigned URL issued, email sent via DirectMail SMTP, full audit trail written.
- Three-layer agent memory on Alibaba Cloud Tablestore: episodic (past quotes per customer), semantic (catalog knowledge), and session/working memory, with importance-scored decay ("forgetting") and retrieval under a fixed context budget.
- Multi-agent orchestration (planner, workers, critic) on AgentScope with a measured efficiency comparison against a single-agent baseline.
- Observability: OpenTelemetry GenAI spans, per-quote reasoning trace visible in the dashboard, cost and token accounting.
- Evaluation harness: 30-item labeled RFQ test set, automated metrics, CI gate.
- Review dashboard (frontend) showing queue, quote detail, line-item confidence, reasoning trace, and approval controls.
- All hackathon submission artifacts' technical prerequisites (public repo, license, deployment-proof code file, architecture diagram source).

**Out of scope (v1.0):**

- Live IMAP/POP3 mailbox polling (simulated by OSS drop and paste; the email MCP server ships with a stub inbox).
- Real ERP/CRM integrations (catalog and customers are seeded; the MCP server boundary is where a real integration would attach).
- Payment, ordering, invoicing, or e-invoice (hóa đơn điện tử) issuance. A báo giá is pre-contract; no tax-authority integration is required or built.
- Multi-tenant SaaS billing, user management beyond a single demo token, SSO.
- Automated FX rate feeds (rate is configuration; a live feed is a documented roadmap item).
- Fine-tuning of models.

### 1.3 Product context in one paragraph

A Vietnamese IT reseller receives RFQs all day: a Vietnamese-language email asking for "20 laptop Dell Latitude 5450, RAM 32GB", a scanned công văn PDF from a state-owned enterprise, an English Excel sheet from a foreign firm's Hanoi office. Today a sales rep reads each one, hunts the catalog, checks the customer's discount tier, computes VAT, formats a báo giá in Word, gets a manager to eyeball it, and emails it back: a half-day round trip per quote with real money lost to price typos and slow responses. QuoteMind collapses that loop to minutes: agents parse any of those inputs, match products, price deterministically, draft the bilingual quote, and stop at a human approval gate where the manager sees the draft, the agent's reasoning, and the margin check before one click sends it.

### 1.4 Definitions and abbreviations

| Term | Definition |
|---|---|
| RFQ | Request for quotation: inbound customer document or message asking for prices |
| Báo giá | Vietnamese sales quotation document |
| Quote | The structured object QuoteMind produces; rendered as a bilingual PDF |
| Line item | One product row in an RFQ or quote |
| MST | Mã số thuế: Vietnamese enterprise tax code |
| ĐVT | Đơn vị tính: unit of measure |
| Tier | Customer pricing tier: `end_customer`, `dealer`, `project` |
| HITL | Human-in-the-loop approval checkpoint |
| KnowledgeStore / MemoryStore | Storage abstractions of the `tablestore-for-agent-memory` SDK |
| FC | Alibaba Cloud Function Compute 3.0 |
| OSS | Alibaba Cloud Object Storage Service |
| DashScope | Alibaba Cloud Model Studio inference API (international: Singapore) |
| CDS | CyberSkill Design System (visual tokens for the dashboard and PDF) |
| Cowork | Claude Cowork, the AI agent that will decompose this spec into FRs and implement |

### 1.5 References

- Qwen Cloud Hackathon brief (client-supplied requirements and judging criteria images, 2026-07)
- CyberSkill internal research report: "Track Recommendation & Technical Foundation" (2026-07-10)
- CyberSkill internal research report: "QuoteMind Technical Reference" (2026-07-10)
- AgentScope 1.0 documentation (docs.agentscope.io); AgentScope Runtime cookbook
- Alibaba Cloud Model Studio, Function Compute 3.0, OSS, Tablestore, DirectMail documentation
- Nghị quyết 204/2025/QH15 and Nghị định 174/2025/NĐ-CP (VAT 8% reduction through 2026-12-31)
- OpenTelemetry GenAI semantic conventions (Development status)

---

## 2. Product overview

### 2.1 Vision

Every Vietnamese SME reseller answers every RFQ within minutes, in the customer's language, at the correct price, with management control preserved. QuoteMind is the reference implementation: an autopilot that does the work and a cockpit that keeps the human in command.

### 2.2 Problem statement

1. **Speed loses deals.** RFQ response time in IT distribution is a primary win/loss factor; manual quoting takes hours to a day.
2. **Manual pricing leaks margin.** Wrong tier, stale rates, VAT category mistakes (8% vs 10%), and arithmetic slips directly cost money.
3. **Bilingual overhead doubles the work.** Vietnamese resellers serving foreign buyers produce two documents or a bilingual one by hand.
4. **Knowledge lives in one rep's head.** What this customer bought, what discount they got, which substitutions they accepted: none of it is institutional memory.

### 2.3 Personas

| ID | Persona | Description | Primary needs |
|---|---|---|---|
| PER-01 | Sales Manager "Chị Linh" | Approves quotes, owns margin | See draft + reasoning + margin check fast; edit terms; one-click approve; trust the numbers |
| PER-02 | Sales Rep "Anh Minh" | Handles inbound RFQs | Stop retyping line items; get a correct draft to review instead of a blank page |
| PER-03 | Customer (buyer) | Sends RFQs in VI or EN | Fast, professional, correctly priced bilingual quote |
| PER-04 | Hackathon Judge | Evaluates against rubric | See sophisticated Qwen/Alibaba API use, clean architecture, real problem value, visible reasoning, measurable results |
| PER-05 | Cowork implementation agent | Builds from this spec | Unambiguous contracts, frozen names, verifiable acceptance criteria |

### 2.4 Core user journeys

**UJ-01 — Happy path, Vietnamese text RFQ (demo beat 1).**
Customer email text (Vietnamese) pasted or dropped → IntakeClassifier detects language and channel → DocumentParser extracts 3 line items with confidences → CatalogMatcher resolves SKUs (one fuzzy match flagged) → PricingEngine computes tiered prices + 8% VAT → QuoteDrafter composes bilingual quote → CriticValidator passes → HITL: Chị Linh reviews trace, approves → PDF rendered, stored, emailed → audit trail complete. Target wall-clock to draft: under 90 seconds.

**UJ-02 — Scanned PDF công văn (demo beat 2).**
Scanned Vietnamese PDF dropped in OSS bucket → OSS trigger fires parser with `qwen-vl-ocr` page images → table extracted despite skew → rest as UJ-01. Demonstrates multimodal robustness.

**UJ-03 — Ambiguity and HITL revision (demo beat 3).**
RFQ requests an out-of-catalog item and a below-margin-floor discount ("giá dự án") → CatalogMatcher proposes nearest substitute with `needs_confirmation` → CriticValidator flags margin below floor → HITL shows both flags → Linh types a revision instruction ("substitute approved, hold 8% margin, add 2-week lead time note") → QuoteDrafter revises → approve → dispatch. Demonstrates ambiguous-input handling and human checkpoints, the two behaviors Track 4 names explicitly.

**UJ-04 — Returning customer memory (demo beat 4).**
Second RFQ from the same customer → episodic memory retrieves last quote's discount and accepted substitution → QuoteDrafter references it ("as per your March quote, Latitude 5450 substituted for 5440") → shows memory retrieval in the trace. Demonstrates the Track 1 fold-in.

**UJ-05 — Baseline comparison (demo beat 5, evaluation).**
Eval harness runs the 30-RFQ set through (a) the full multi-agent pipeline and (b) a single monolithic ReAct agent baseline → dashboard/eval report shows success rate, extraction F1, price correctness, latency, tokens. Demonstrates the Track 3 fold-in with the "measurable efficiency gain" number.

### 2.5 What makes this submission win (design theses)

1. **All-native Alibaba stack as a feature.** AgentScope (Alibaba's own agent framework) + DashScope Qwen models + Tablestore agent-memory SDK + FC + OSS + DirectMail. Judges scoring "sophisticated use of QwenCloud APIs" see first-party depth no LangChain port shows.
2. **Deterministic money.** LLMs never do arithmetic on prices. Pricing and VAT are pure functions with unit tests; the critic recomputes independently. This is the "production-readiness" argument in one sentence.
3. **Memory and multi-agent depth folded into a business problem.** Track 1's forgetting/retrieval and Track 3's measured multi-agent gain are implemented as necessities of a real workflow, not as demos of themselves.
4. **Bilingual by construction.** Vietnamese-first parsing, VND formatting, báo giá conventions, and side-by-side VI/EN output showcase Qwen's multilingual strength in a way most submissions will not.
5. **Visible reasoning.** Every quote carries a machine-readable trace (per-agent steps, tool calls, memory hits, token cost) rendered in the dashboard and shown in the video. Winning submissions in comparable hackathons won on the visible decision trail.

---

## 3. Goals, non-goals, success metrics

### 3.1 Goals

| ID | Goal | Metric | Target |
|---|---|---|---|
| G-01 | End-to-end autopilot works on real-shaped inputs | Eval task success rate (correct items + correct price + valid PDF) | ≥ 80% on the 30-RFQ set |
| G-02 | Extraction quality | Line-item extraction F1 | ≥ 0.95 clean text; ≥ 0.85 scanned |
| G-03 | Catalog resolution | Top-1 SKU match accuracy on labeled set | ≥ 0.90 |
| G-04 | Money is always right | Price/VAT computation correctness (deterministic path) | 100% (unit-tested) |
| G-05 | Fast enough to demo live | p50 RFQ→draft latency | ≤ 90 s (text), ≤ 150 s (scanned PDF) |
| G-06 | Multi-agent gain is measurable | Δ success rate and Δ human-edit-need vs single-agent baseline | Reported; pipeline ≥ +10 pts success |
| G-07 | Cost sanity | Model cost per quote (list prices) | ≤ US$0.05 typical |
| G-08 | Submission completeness | All SUB-NN requirements pass checklist | 100% |

### 3.2 Non-goals

- Replacing the sales manager. The HITL gate is a feature, not a limitation; no auto-send in v1.0.
- Legal-grade contract generation. A báo giá is an offer document; terms are templated and editable.
- Model training or evaluation of Qwen itself.
- Production hardening beyond demo-grade auth (single bearer token) — documented as roadmap.

### 3.3 Success metrics for the hackathon (rubric mapping)

| Rubric axis | Weight | QuoteMind evidence |
|---|---|---|
| Technical Depth & Engineering | 30% | AgentScope ReAct multi-agent + PlanNotebook; Tablestore MemoryStore/KnowledgeStore hybrid retrieval; qwen-vl-ocr document pipeline; deterministic pricing core; interrupt/resume HITL across serverless invocations; MCP tool servers; OTel GenAI tracing |
| Innovation & AI Creativity | 30% | Memory with importance-decay forgetting inside a business autopilot; critic that independently recomputes money; bilingual quote synthesis; measured multi-agent vs single-agent delta |
| Problem Value & Impact | 25% | Authentic Vietnamese SME pain; minutes vs half-day; margin protection; direct productization path for CyberSkill clients |
| Presentation & Documentation | 15% | Reasoning trace UI; architecture diagram; eval report; 3-minute demo following the five beats above; this spec in-repo |

---

## 4. System context and architecture

### 4.1 C4 Level 1 — System context

```
                          ┌──────────────────────────────┐
   RFQ email text /       │                              │      Bilingual quote PDF
   PDF / Excel / scan     │          QuoteMind           │      + email dispatch
  ───────────────────────▶│  (RFQ-to-Quote Autopilot)    │─────────────────────────▶ Customer
                          │                              │
   Buyer (VI/EN)          └──────┬───────────┬───────────┘
                                 │           │
                    reviews &    │           │  models, storage,
                    approves     │           │  email, memory
                                 ▼           ▼
                          Sales Manager   Alibaba Cloud
                          (HITL gate)     (DashScope Qwen · FC · OSS ·
                                           Tablestore · DirectMail)
```

External actors: Buyer (sends RFQ, receives quote), Sales Manager (approves via dashboard), Alibaba Cloud platform services, Hackathon judge (reads repo, watches demo, may call the live endpoint).

### 4.2 C4 Level 2 — Containers

| Container | Tech | Responsibility |
|---|---|---|
| C-01 API & Orchestrator function | FC 3.0, Python 3.12 (fallback 3.10), FastAPI-style web function | HTTP API, runs the AgentScope pipeline, persists state, serves dashboard JSON |
| C-02 Ingest trigger function | FC 3.0, OSS object-created trigger | Fires pipeline when an RFQ file lands in `quotemind-inbox` bucket |
| C-03 Review dashboard | Static SPA (vanilla TS + Vite or React), served from OSS static hosting | Queue, quote detail, trace viewer, approve/reject/revise |
| C-04 Agent runtime | AgentScope 1.0.x inside C-01/C-02 | ReAct agents, Toolkit, MsgHub pipeline, PlanNotebook |
| C-05 MCP tool servers | Python `mcp` (FastMCP), embedded (stdio) for demo | `catalog-mcp` (product lookup), `email-mcp` (send/stub-inbox) |
| C-06 Memory layer | Tablestore via `tablestore-for-agent-memory` | MemoryStore (sessions/messages), KnowledgeStore (catalog + episodic quotes, vector + FTS) |
| C-07 Object store | OSS `quotemind-inbox`, `quotemind-artifacts` buckets | Inbound files; generated PDFs; presigned URLs |
| C-08 Model gateway | DashScope international (Singapore), OpenAI-compatible mode | qwen3-max, qwen-plus, qwen-vl-ocr / qwen3-vl-plus, text-embedding-v4 |
| C-09 Email dispatch | DirectMail SMTP (Singapore region) via smtplib | Outbound quote email with PDF link |
| C-10 Observability | OpenTelemetry SDK → console/OTLP; trace JSON persisted per quote | GenAI spans, cost accounting, trace for UI |
| C-11 Eval harness | pytest + CLI runner | 30-RFQ labeled set, metrics, baseline comparison, CI gate |

### 4.3 Component flow (happy path)

```
[Channel: upload / OSS drop / paste]
        │
        ▼
 IntakeClassifier (qwen-plus) ── language, channel, doc type, customer hint
        │
        ▼
 DocumentParser (qwen-vl-ocr for images/scans; qwen-plus for text; openpyxl for xlsx)
        │        └── structured_model=RFQExtraction (Pydantic)
        ▼
 CatalogMatcher ── KnowledgeStore.vector_search + full_text_search (hybrid), tier lookup
        │        └── per-line: matched SKU, confidence, needs_confirmation?
        ▼
 PricingEngine (DETERMINISTIC python) ── tier price, discounts, VAT/line, totals, margin
        │
        ▼
 QuoteDrafter (qwen3-max) ── bilingual quote object + notes, references episodic memory
        │
        ▼
 CriticValidator (qwen3-max + deterministic recompute) ── blocks or passes with flags
        │
        ▼
 HITL Approval Gate ── state persisted (Tablestore); dashboard approve/reject/revise
        │  approve                        revise ──▶ QuoteDrafter (loop, max 3)
        ▼
 DispatchAgent ── WeasyPrint PDF → OSS → presigned URL → DirectMail send → audit
```

### 4.4 Technology stack (normative)

| Layer | Choice | Pinned version | Notes |
|---|---|---|---|
| Language | Python | 3.12 (FC runtime `python3.12`; fall back `python3.10` if region lacks 3.12) | single language backend |
| Agent framework | `agentscope` | `1.0.x` (pin exact minor at bootstrap; record in verification log) | ReActAgent, Toolkit, MsgHub, PlanNotebook, UserAgent |
| Runtime services | direct SDK path (NOT agentscope-runtime) | n/a | Decision D-02 below |
| Memory SDK | `tablestore-for-agent-memory` | `==1.1.3` | MemoryStore, KnowledgeStore |
| Tablestore SDK | `tablestore` | `>=6.4.7` | OTSClient |
| Object storage | `oss2` | latest 2.x | ProviderAuthV4, sign_url slash_safe=True |
| Models | DashScope intl OpenAI-compatible | see 4.6 | via `openai` python client `>=1.x` for direct calls; AgentScope DashScopeChatModel for agents |
| Embeddings | `text-embedding-v4` | dim **1024** frozen | Matryoshka dims exist; 1024 is the project constant |
| PDF | `weasyprint` | `==68.*` | + Jinja2 templates; Be Vietnam Pro via @font-face url() |
| Excel parse | `openpyxl` | latest | deterministic, no LLM for cell reads |
| MCP | `mcp` (FastMCP) | latest 1.x | stdio transport in-process for demo |
| Observability | `opentelemetry-sdk`, GenAI semconv | latest | `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` |
| Frontend | Vite + TypeScript (React allowed) | latest | CDS tokens: Umber #45210E, Ochre #F4BA17, Be Vietnam Pro, APCA Lc ≥ 75 |
| IaC/deploy | Serverless Devs `s` CLI, `s.yaml` edition 3.0.0 | latest | region `ap-southeast-1` |
| CI | GitHub Actions | n/a | lint (ruff), type (mypy loose), unit, eval-smoke |

### 4.5 Architecture decisions (ADR summary)

| ID | Decision | Rationale | Alternative rejected |
|---|---|---|---|
| D-01 | AgentScope 1.0 as the agent framework | First-party Alibaba framework scores API sophistication; ReAct + hooks + structured output suffice | LangGraph (generic, weaker story), Qwen-Agent (thinner orchestration) |
| D-02 | Use `tablestore-for-agent-memory` SDK directly; do NOT depend on `agentscope-runtime` Tablestore services | Runtime's Tablestore integration is documented only for runtime ≤1.0.5 and Runtime is being absorbed into AgentScope 2.0; direct SDK is stable and demonstrable | agentscope-runtime==1.0.5 service classes (version-drift risk) |
| D-03 | Pricing/VAT is deterministic Python, never LLM arithmetic | Correctness guarantee; unit-testable; the critic recomputes with the same pure functions | LLM computes totals (unacceptable error class) |
| D-04 | HITL state machine persisted in Tablestore, resumable across FC invocations | Serverless functions are stateless; approval may come hours later | In-memory wait / long-running function (times out) |
| D-05 | qwen-vl-ocr primary for scans, qwen3-vl-plus fallback; PDF pages rasterized to images | OCR-tuned model for Vietnamese documents; page-image path is universally supported | Direct-PDF upload (newer OCR variants only; region availability uncertain) |
| D-06 | Bilingual quote is one document, VI primary column/EN secondary | Vietnamese governing-language convention; single artifact simpler to approve | Two separate PDFs |
| D-07 | MCP servers run in-process via stdio for the demo | Zero extra infrastructure; still demonstrates the MCP boundary honestly | Hosted SSE MCP endpoints (more infra, little demo value) |
| D-08 | Frontend is a static SPA on OSS calling the FC HTTP API | No server to manage; OSS static hosting is another native-service proof point | SSR app on SAE (heavier) |
| D-09 | Currency: VND is the ledger currency; USD display computed from configured rate `FX_USD_VND` | Deterministic, auditable; avoids live-feed dependency in demo | Live FX API (roadmap) |
| D-10 | Apache-2.0 license | Hackathon requires visible OSS license; Apache-2.0 is enterprise-friendly | MIT (fine too; Apache chosen for patent grant) |

### 4.6 Model routing table (frozen constants — see DO-NOT-CHANGE)

| Constant | Model ID | Used by | Params |
|---|---|---|---|
| `MODEL_PLANNER` | `qwen3-max` | Orchestrator/PlanNotebook reasoning | `enable_thinking=True` (stream), temp 0.2 |
| `MODEL_CLASSIFIER` | `qwen-plus` | IntakeClassifier | temp 0.0, JSON structured output |
| `MODEL_PARSER_TEXT` | `qwen-plus` | DocumentParser (text/email) | temp 0.0, structured_model |
| `MODEL_PARSER_VISION` | `qwen-vl-ocr` (fallback `qwen3-vl-plus`) | DocumentParser (scans/images) | max_tokens 4096 |
| `MODEL_DRAFTER` | `qwen3-max` | QuoteDrafter | temp 0.3 |
| `MODEL_CRITIC` | `qwen3-max` | CriticValidator narrative checks | temp 0.0 |
| `MODEL_EMBED` | `text-embedding-v4` | Embedding pipeline | `dimensions=1024` |

Model IDs live in `src/quotemind/config/models.py` as constants; a bootstrap script verifies each ID against the live Singapore catalog and fails fast with a clear message if unavailable (FR-012).

### 4.7 Environment configuration (frozen names)

All secrets/config via environment variables; `.env.example` in repo; never commit real keys.

| Env var | Purpose | Example |
|---|---|---|
| `DASHSCOPE_API_KEY` | Model Studio API key | `sk-...` |
| `DASHSCOPE_BASE_URL` | OpenAI-compatible base | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |
| `ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET` | RAM user for OSS/Tablestore/FC | |
| `TABLESTORE_ENDPOINT` | e.g. `https://quotemind.ap-southeast-1.ots.aliyuncs.com` | |
| `TABLESTORE_INSTANCE` | `quotemind` | |
| `OSS_ENDPOINT` | `https://oss-ap-southeast-1.aliyuncs.com` | |
| `OSS_BUCKET_INBOX` | `quotemind-inbox` | |
| `OSS_BUCKET_ARTIFACTS` | `quotemind-artifacts` | |
| `DIRECTMAIL_SMTP_HOST` / `DIRECTMAIL_SMTP_PORT` | `smtpdm-ap-southeast-1.aliyun.com` / `465` | |
| `DIRECTMAIL_USER` / `DIRECTMAIL_PASSWORD` | verified sender + SMTP password | |
| `MAIL_FROM` | `quotes@demo.cyberskill.world` | |
| `DEMO_API_TOKEN` | Bearer token for dashboard/API | random 32+ chars |
| `FX_USD_VND` | configured rate | `25400` |
| `MARGIN_FLOOR_PCT` | critic policy | `5` |
| `QUOTE_VALIDITY_DAYS` | default validity | `14` |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | `gen_ai_latest_experimental` | |
| `QM_ENV` | `local` / `fc` | switches sandbox/paths |

Region is `ap-southeast-1` (Singapore) for every service. If DirectMail sender verification cannot complete in time, `MAIL_TRANSPORT=stub` writes the email to the audit log and OSS instead (FR-093 fallback), keeping the demo deterministic.


---

## 5. Functional requirements

Requirements are grouped into epics EP-01…EP-13. Priorities: P0 must ship for the demo; P1 should ship; P2 stretch. Every FR is atomic for Cowork decomposition.

### EP-01 — Repository, infrastructure and scaffolding

**FR-001 (P0) Repository scaffold.** The system shall provide a public Git repository with the frozen layout defined in Appendix D, an Apache-2.0 `LICENSE` at root, a `README.md` with quickstart, and `pyproject.toml` pinning the versions in §4.4.
- AC: Given a fresh clone, When `make setup && make test` runs on Python 3.12, Then dependencies install and the unit suite passes with zero network calls to paid APIs.
- Dep: none.

**FR-002 (P0) Configuration module.** The system shall load all configuration exclusively from environment variables via `src/quotemind/config/settings.py` (pydantic-settings), with `.env.example` documenting every variable in §4.7 and hard failure on missing P0 variables at startup.
- AC: Given `DASHSCOPE_API_KEY` unset, When the API function cold-starts, Then it exits with a single-line actionable error naming the variable.
- Dep: FR-001.

**FR-003 (P0) Serverless Devs deployment descriptor.** The system shall include `deploy/s.yaml` (edition 3.0.0, component `fc3`) defining: function `quotemind-api` (HTTP trigger, `python3.12`, memory 1024 MB, timeout 300 s, `initializer` handler) and function `quotemind-ingest` (OSS object-created trigger on `quotemind-inbox`, prefix `rfq/`), both in `ap-southeast-1`, with environment variables injected from deployment config.
- AC: Given valid credentials, When `s deploy` runs, Then both functions deploy and `GET {api}/health` returns `{"status":"ok","version":...}`.
- Dep: FR-001, FR-002.

**FR-004 (P0) Provisioning script.** The system shall provide `deploy/provision.py` that idempotently creates: OSS buckets `quotemind-inbox` and `quotemind-artifacts` (private ACL), the Tablestore instance's required tables/indexes via MemoryStore/KnowledgeStore initialization (vector dim 1024), and prints a provisioning report.
- AC: Given a clean account, When the script runs twice, Then the second run reports "already exists" for every resource and exits 0.
- Dep: FR-002.

**FR-005 (P0) Deployment-proof module.** The system shall include `src/quotemind/cloud/alibaba_proof.py`: a single, well-commented module that exercises DashScope (chat + embedding), OSS (put/get/presign), and Tablestore (put/get) in one runnable `python -m quotemind.cloud.alibaba_proof` flow, existing to satisfy the hackathon's "link to a code file demonstrating use of Alibaba Cloud services and APIs".
- AC: Given deployed credentials, When the module runs, Then it prints PASS lines for DashScope, OSS, Tablestore and exits 0.
- Dep: FR-002, FR-004.

**FR-006 (P0) Local dev mode.** The system shall run the full pipeline locally (`make dev`) with `QM_ENV=local`, using the same code paths (real DashScope + real Tablestore/OSS) so demo rehearsal equals production behavior.
- AC: Given local env vars, When `make dev` starts and a sample RFQ posts to `localhost:9000/api/rfq`, Then a draft quote reaches `pending_approval`.
- Dep: FR-003 equivalents local.

**FR-007 (P1) CI pipeline.** GitHub Actions shall run ruff, mypy (non-strict), unit tests, and the eval smoke subset (5 RFQs, mocked models) on every PR; failing gates block merge.
- Dep: FR-001, EP-12.

**FR-008 (P0) Structured logging.** All functions shall log JSON lines (timestamp, level, quote_id, agent, event) to stdout for FC log collection.
- Dep: FR-001.

**FR-009 (P0) Health and version endpoints.** `GET /health` returns status, git SHA, model constants; unauthenticated.
- Dep: FR-003.

**FR-010 (P0) Auth middleware.** All `/api/*` routes except `/health` shall require `Authorization: Bearer $DEMO_API_TOKEN`; 401 otherwise.
- AC: Given no token, When `GET /api/quotes`, Then 401 with JSON error body.
- Dep: FR-003.

**FR-011 (P1) Seed command.** `python -m quotemind.seed` shall load Appendix A seed data (catalog 60 SKUs, 8 customers, 6 historical quotes, SOP snippets) into KnowledgeStore/MemoryStore and OSS sample files.
- Dep: FR-004, EP-04.

**FR-012 (P0) Model availability bootstrap check.** On cold start (initializer), the system shall verify each constant in §4.6 against the live model list (1-token dry call or models endpoint) and log WARN + activate documented fallback (`qwen3-max`→`qwen-max`; `qwen-vl-ocr`→`qwen3-vl-plus`) if a primary is unavailable.
- AC: Given `qwen-vl-ocr` unavailable, When cold start completes, Then parser uses fallback and `/health` reports the substitution.
- Dep: FR-002.

### EP-02 — Intake and channels

**FR-020 (P0) Direct upload endpoint.** `POST /api/rfq` shall accept multipart (file: pdf/xlsx/png/jpg, ≤15 MB) or JSON `{"text": "...", "customer_hint": "...", "channel":"paste"}` and return `202 {"quote_id": "...", "status":"received"}` immediately, processing asynchronously.
- AC: Given a 3-line Vietnamese text RFQ, When posted, Then within 90 s `GET /api/quotes/{id}` shows status `pending_approval`.
- Dep: FR-010, EP-03..06.

**FR-021 (P0) OSS drop channel.** Objects created under `oss://quotemind-inbox/rfq/` shall trigger `quotemind-ingest`, which registers a new quote (source_uri set) and invokes the same pipeline.
- AC: Given `rfq/sample_scan.pdf` uploaded, When the trigger fires, Then a quote record exists with `channel="oss_drop"` and parsing starts.
- Dep: FR-003, FR-004.

**FR-022 (P0) Intake classification.** The IntakeClassifier agent (AGT-02) shall determine: `language` (vi/en/mixed), `doc_type` (email_text|pdf_digital|pdf_scan|image|xlsx), `customer_match` (known customer id via email/domain/name lookup, else null), `urgency` (normal|urgent keyword heuristic), emitting `IntakeResult` (DM-02) with confidences.
- AC: Given the Appendix A sample set, When classified, Then language accuracy = 100% and doc_type accuracy ≥ 95%.
- Dep: FR-020/021, AGT-02.

**FR-023 (P1) Email text channel with headers.** When JSON includes `email_meta` (from, subject, date), the system shall use `from` domain for customer matching and store meta in the quote record.
- Dep: FR-020.

**FR-024 (P0) Idempotency.** Re-posting an identical payload (sha256 of content) within 24 h shall return the existing quote_id with `status` rather than creating a duplicate.
- Dep: FR-020, DM-01.

**FR-025 (P1) Oversize/unsupported handling.** Files >15 MB or unsupported types shall yield `422` (upload) or a quote in status `failed_intake` with a human-readable reason (OSS path).
- Dep: FR-020/021.

### EP-03 — Document parsing and extraction

**FR-030 (P0) Text RFQ extraction.** For `email_text`, DocumentParser (AGT-03) shall extract `RFQExtraction` (DM-03) using `MODEL_PARSER_TEXT` with AgentScope `structured_model=` (Pydantic), including per-line `confidence` ∈ [0,1] and `source_span` (character offsets).
- AC: Given eval text RFQs, When parsed, Then line-item F1 ≥ 0.95 and every emitted line has confidence and span.
- Dep: FR-022, AGT-03, DM-03.

**FR-031 (P0) PDF rasterization.** Digital and scanned PDFs shall be rasterized page-by-page (pypdfium2, 200 DPI, max 10 pages, downscale to ≤2560 px long edge) to PNGs stored under `oss://quotemind-artifacts/{quote_id}/pages/`.
- AC: Given a 3-page scan, When rasterized, Then 3 PNGs exist and each ≤ 2560 px long edge.
- Dep: FR-021.

**FR-032 (P0) Vision extraction.** For scans/images, the parser shall call `MODEL_PARSER_VISION` per page (OpenAI-compatible content array: image_url items + instruction), instructing JSON-only output conforming to `RFQExtraction`; fenced ```json blocks shall be stripped; per-page results merged with de-duplication by (description, quantity).
- AC: Given the 5 labeled scans, When extracted, Then F1 ≥ 0.85 and Vietnamese diacritics in descriptions are preserved byte-exact against labels.
- Dep: FR-031, AGT-03.

**FR-033 (P0) Excel extraction.** `.xlsx` shall be parsed deterministically with openpyxl: header-row detection (fuzzy match on {stt, tên hàng, mô tả, description, qty, số lượng, đvt, unit}), then LLM normalization of ambiguous headers only. No LLM reads numeric cells.
- AC: Given the 5 labeled xlsx files, When parsed, Then quantity fields match labels 100%.
- Dep: FR-020, AGT-03.

**FR-034 (P0) Extraction validation gate.** An `RFQExtraction` with zero line items, or any line missing description or quantity, shall set quote status `needs_clarification` with reason codes; it shall not proceed to matching.
- AC: Given an empty-body RFQ, When parsed, Then status = `needs_clarification`, reason `NO_LINE_ITEMS`.
- Dep: FR-030/032/033.

**FR-035 (P1) Mixed-language handling.** Lines in a different language than the document majority shall still extract; `RFQExtraction.language_per_line` records vi/en per line for the drafter.
- Dep: FR-030.

**FR-036 (P2) Multi-RFQ splitting.** If one document contains clearly separate requests (two công văn in one PDF), the parser shall split into multiple quotes linked by `batch_id`.
- Dep: FR-032.

### EP-04 — Catalog, customers and memory (Track-1 fold-in)

**FR-040 (P0) Knowledge schema.** The system shall persist catalog products, customer profiles, historical quotes (episodic), and SOP snippets in KnowledgeStore documents with `tenant_id` routing: `catalog`, `customers`, `episodic:{customer_id}`, `sop`; metadata fields per DM-05..08.
- Dep: FR-004.

**FR-041 (P0) Embedding pipeline.** All KnowledgeStore documents shall be embedded with `MODEL_EMBED` at `dimensions=1024`; embedding calls batched ≤10 texts; the vector dimension is frozen project-wide.
- AC: Given the 60-SKU catalog, When seeded, Then every document has a 1024-dim embedding.
- Dep: FR-040.

**FR-042 (P0) Hybrid catalog matching.** CatalogMatcher (AGT-04) shall, per extracted line: (1) `vector_search(query_vector, top_k=8, tenant_id="catalog")`; (2) `full_text_search` on normalized description; (3) fuse candidates (reciprocal-rank fusion), then LLM-select best SKU with justification; emit `MatchResult` (DM-09) with `match_confidence` and `needs_confirmation` when confidence < 0.75 or specs conflict.
- AC: Given labeled lines, When matched, Then top-1 accuracy ≥ 0.90; every `needs_confirmation` carries an alternative candidate list (≤3).
- Dep: FR-041, AGT-04.

**FR-043 (P0) Customer resolution and tiers.** The system shall resolve customer by (email domain → name fuzzy → hint) against `customers` tenant; unresolved defaults to tier `end_customer` with flag `unknown_customer=true`.
- Dep: FR-040.

**FR-044 (P0) Episodic memory write.** On quote approval or rejection, the system shall write an episodic document: summary (LLM, ≤120 words, bilingual keys), items, prices, decision, human edits, embedding; metadata: `customer_id`, `created_at`, `importance` (initial per FR-046), `outcome`.
- Dep: FR-040, EP-08.

**FR-045 (P0) Episodic retrieval.** Before drafting, the system shall retrieve top-3 episodic memories for the resolved customer (vector search on current RFQ summary, tenant `episodic:{customer_id}`), inject them into the drafter context under a fixed budget (≤1200 tokens), and record which memories were used in the trace.
- AC: Given UJ-04 (returning customer), When drafting, Then the draft references the prior substitution and the trace lists the retrieved memory ids.
- Dep: FR-044, AGT-06.

**FR-046 (P0) Importance scoring and decay (forgetting).** Each episodic memory shall carry `importance ∈ [0,1]`: initial = f(outcome: approved 0.7 / edited 0.8 / rejected 0.9; value: +0.1 if total > 100M VND, cap 1.0). Effective retrieval score = `similarity × recency_decay × importance`, `recency_decay = 0.5^(age_days/half_life)` with `half_life=90` days. A maintenance task (`python -m quotemind.memory.gc`) shall hard-delete memories with effective ceiling < 0.05 and compact per-customer memories beyond 50 into an LLM-written profile summary document.
- AC: Given a 200-day-old low-importance memory and a fresh one of equal similarity, When retrieved, Then the fresh one ranks first; Given gc runs on seeded aged data, Then pruned count > 0 and a compaction summary document exists.
- Dep: FR-044/045.

**FR-047 (P0) Session/working memory.** Each quote shall have a MemoryStore `Session(user_id=customer_id or "anonymous", session_id=quote_id)`; every agent step appends a `Message` (role, content, agent name in metadata) enabling resume and audit.
- Dep: FR-004.

**FR-048 (P1) SOP (procedural) memory.** Drafter and critic shall retrieve top-2 SOP snippets (tenant `sop`) relevant to the quote (payment terms templates, delivery norms, warranty language) instead of hardcoding prose.
- Dep: FR-040.

**FR-049 (P1) Context budget guard.** Total injected memory (episodic + SOP + catalog snippets) shall never exceed 2500 tokens; overflow drops lowest-effective-score items and logs `memory_truncated=true`.
- Dep: FR-045/048.

### EP-05 — Pricing engine (deterministic)

**FR-050 (P0) Pure pricing functions.** `src/quotemind/pricing/engine.py` shall expose pure functions: `unit_price(product, tier) -> Decimal`, `line_total(qty, unit_price, discount_pct) -> Decimal`, `vat_amount(line_total, vat_rate) -> Decimal`, `quote_totals(lines) -> Totals`; all money as `Decimal` quantized to 0 VND (whole đồng); no floats, no LLM.
- AC: Property-based tests (hypothesis) hold: totals equal sum of parts; VND totals are integers; 100% branch coverage on engine.
- Dep: none (pure).

**FR-051 (P0) Tier pricing rules.** unit_price shall be: `end_customer` = list_price; `dealer` = dealer_price; `project` = dealer_price × (1 − project_discount_pct/100) with per-customer `project_discount_pct` (default 3). Missing dealer_price falls back to list_price with flag.
- Dep: FR-050, DM-05/06.

**FR-052 (P0) VAT rules (Vietnam 2026).** Default VAT per line = product.vat_rate; catalog seeds IT hardware/software at **8%** (Nghị định 174/2025/NĐ-CP reduction valid through 2026-12-31); allowed values {0,5,8,10}; any line whose category ∈ {telecom_service} shall force 10% and add flag `VAT_EXCLUDED_CATEGORY`. The engine shall expose `vat_policy_note(date)` returning the legal-basis string for the quote footer.
- AC: Given a telecom accessory service line, When priced, Then VAT = 10% and the flag is present; Given date 2027-01-01 in config, Then default becomes 10% with note updated (config `VAT_DEFAULT_OVERRIDE` respected).
- Dep: FR-050.

**FR-053 (P0) Margin computation.** Each line and the quote shall carry `margin_pct = (sell − cost)/sell × 100` using `cost_price`; quotes with any line margin < `MARGIN_FLOOR_PCT` or blended margin < floor shall be flagged `MARGIN_BELOW_FLOOR` (blocking flag for critic).
- Dep: FR-050.

**FR-054 (P0) Currency handling.** Ledger currency VND. When RFQ language = en or customer.preferred_currency = USD, the quote shall include USD reference column: `usd = vnd / FX_USD_VND`, rounded to 2 dp, marked "reference only, invoice in VND"; FX rate and its config timestamp printed in footer.
- Dep: FR-050.

**FR-055 (P0) Number formatting.** VND rendered as `1.234.567 đ` (dot thousands, đ suffix); USD as `$1,234.56`; amount-in-words (bằng chữ) generated in Vietnamese for the grand total via deterministic converter with unit tests (e.g. 1.234.000 → "Một triệu hai trăm ba mươi bốn nghìn đồng").
- AC: 30 tabulated conversion cases pass, including edge cases (mốt/tư/lăm, linh/lẻ, tỷ boundaries).
- Dep: FR-050.

**FR-056 (P1) Availability and lead time.** Lines matched to `stock_status=out_of_stock` shall carry lead_time_note from catalog and flag `LEAD_TIME`; drafter must surface it in notes.
- Dep: FR-042.

### EP-06 — Quote drafting (bilingual)

**FR-060 (P0) Quote assembly.** QuoteDrafter (AGT-06) shall assemble `Quote` (DM-10) from MatchResults + PricingEngine outputs: header (seller block from config: CyberSkill demo reseller identity incl. MST, address, bank block), customer block, line table, totals, validity (`QUOTE_VALIDITY_DAYS`), payment/delivery/warranty terms (from SOP memory), notes. The LLM writes only natural-language fields (notes, term phrasing, substitution explanations); every number is copied verbatim from PricingEngine output and verified by checksum (FR-070).
- AC: Given any eval RFQ, When drafted, Then every numeric field in Quote equals the engine output exactly (automated diff).
- Dep: EP-04, EP-05, AGT-06.

**FR-061 (P0) Bilingual content.** Every human-readable field shall exist in both `vi` and `en` (`BilingualText` type, DM-04). Vietnamese is the governing text; the drafter generates the missing language faithfully rather than literally.
- AC: Language QA rubric (EV-06) scores ≥ 4/5 on both languages for 10 sampled quotes.
- Dep: FR-060.

**FR-062 (P0) Quote numbering.** Quote numbers shall be `QM-YYYY-NNNN` (zero-padded, per-year sequence via Tablestore atomic counter row); frozen format.
- Dep: DM-01.

**FR-063 (P0) Substitution transparency.** For any `needs_confirmation` or substituted line, the drafter shall include a bilingual note naming the requested item, the offered item, and the reason; the HITL UI must show these prominently (FR-082).
- Dep: FR-042.

**FR-064 (P1) Revision instructions.** On `revise` (FR-084), the drafter shall re-draft honoring the human instruction, re-run pricing if quantities/discounts changed, and increment `revision` (max 3, then status `needs_manual`).
- Dep: FR-060, EP-08.

**FR-065 (P1) Tone and style constraints.** Vietnamese output: trang trọng business register, correct diacritics; English: plain professional; no marketing superlatives; templates hold fixed skeletons so the LLM fills slots rather than freestyles.
- Dep: FR-060.

### EP-07 — Critic and validation

**FR-070 (P0) Independent recomputation.** CriticValidator (AGT-07) shall recompute every line total, VAT amount, subtotal, and grand total from raw inputs using the same pure engine functions, and reject the draft (`status=critic_failed`, blocking) on any mismatch > 0 VND.
- AC: Given a tampered draft with one wrong total, When the critic runs, Then status = `critic_failed` with the offending line id.
- Dep: FR-050, FR-060.

**FR-071 (P0) Policy checks.** The critic shall evaluate and attach flags: `MARGIN_BELOW_FLOOR` (blocking), `VAT_EXCLUDED_CATEGORY` mismatch (blocking), `UNKNOWN_CUSTOMER` (non-blocking), `NEEDS_CONFIRMATION` lines present (non-blocking), missing mandatory quote fields (blocking), validity/payment terms outside SOP bounds (non-blocking).
- AC: Given UJ-03 input, When validated, Then flags contain `MARGIN_BELOW_FLOOR` and `NEEDS_CONFIRMATION`, and status = `pending_approval` with `blocking=false` only after the margin issue is resolved or explicitly waived at HITL.
- Dep: FR-053, FR-060.

**FR-072 (P0) Bilingual consistency check.** The critic shall verify vi/en field pairs agree on all numbers, SKUs, and dates (regex/numeric diff, not LLM), and that Vietnamese text contains no mojibake (encoding validation).
- Dep: FR-061.

**FR-073 (P1) Critic narrative.** The critic shall produce a concise bilingual review note (≤80 words per language) summarizing what it checked and why it passed/failed, stored in the trace and shown at HITL.
- Dep: FR-070/071.

**FR-074 (P2) Auto-fix loop.** For non-blocking formatting defects only (missing note, term phrasing), the critic may send one revision request to the drafter before HITL; never for money or policy.
- Dep: FR-064.

### EP-08 — Human-in-the-loop approval

**FR-080 (P0) Approval state machine.** Quote status shall follow: `received → parsing → matching → pricing → drafting → validating → pending_approval → {approved → dispatching → sent | rejected | revising → drafting}` plus terminal `failed_*` and `needs_clarification`, `needs_manual`. Transitions persisted in Tablestore (DM-01) with actor, timestamp, and reason; illegal transitions rejected.
- AC: State-machine unit tests cover every legal and illegal transition.
- Dep: DM-01.

**FR-081 (P0) Durable pause and resume.** `pending_approval` shall survive process death: the pipeline run ends at the gate; a later approval API call starts a new FC invocation that loads Session + Quote from Tablestore and resumes dispatch. No in-memory waiting.
- AC: Given a quote pending, When the function instance is killed and approval posted 10 minutes later, Then dispatch completes and the audit trail shows both invocations.
- Dep: FR-047, FR-080.

**FR-082 (P0) Review payload.** `GET /api/quotes/{id}` shall return the full quote, per-line confidences and flags, substitution notes, critic note, margin summary, memory citations, and the reasoning trace reference: everything PER-01 needs on one screen.
- Dep: EP-06/07, EP-11.

**FR-083 (P0) Approve/reject.** `POST /api/quotes/{id}/approve` and `/reject` (body: optional comment) shall transition state, record actor="human", and on approve trigger dispatch. Blocking flags require `{"waive_flags":["MARGIN_BELOW_FLOOR"], "reason":"..."}` to approve; waivers are audited.
- AC: Given a blocking flag and no waiver, When approve posts, Then 409 with the flag list.
- Dep: FR-080/081.

**FR-084 (P0) Revise with instructions.** `POST /api/quotes/{id}/revise` (body: `{"instruction": "..."} `, vi or en) shall enqueue re-drafting per FR-064 and return to `pending_approval` on success.
- AC: UJ-03 flow passes end-to-end.
- Dep: FR-064.

**FR-085 (P1) Approval timeout reminder.** Quotes pending > 4 h shall emit a log event and dashboard badge (no email nagging in v1).
- Dep: FR-080.

### EP-09 — Document generation and dispatch

**FR-090 (P0) Bilingual PDF rendering.** The system shall render the approved quote to PDF via Jinja2 → WeasyPrint using the layout in Appendix C: A4, CyberSkill-styled header (Umber #45210E band, Ochre #F4BA17 accents), seller/customer blocks, bilingual line table (STT | Mô tả/Description | ĐVT/Unit | SL/Qty | Đơn giá/Unit price | Thành tiền/Amount), totals with VAT lines per rate, bằng chữ line, terms, bank block, signature area, footer with vat_policy_note + FX note + page numbers. Font: Be Vietnam Pro embedded via @font-face url() (bundled TTFs); Vietnamese diacritics must render correctly.
- AC: Given the golden quote fixture, When rendered, Then the PDF matches the approved visual snapshot (pixel-diff tolerance ≤ 2%) and copy-pasted text preserves diacritics.
- Dep: FR-060, Appendix C.

**FR-091 (P0) Artifact storage and presigned URL.** The PDF shall be stored at `oss://quotemind-artifacts/quotes/{quote_number}.pdf` (private) and exposed via V4 presigned GET URL (`sign_url('GET', key, 600, slash_safe=True)`); `GET /api/quotes/{id}/pdf` returns 302 to a fresh URL.
- Dep: FR-090.

**FR-092 (P0) Email dispatch.** On approval, DispatchAgent shall send a bilingual email (subject `Báo giá / Quotation {quote_number} — {seller}`, body template with greeting in customer language first, link note, validity) via DirectMail SMTP (SSL 465) with the presigned link (and PDF attached if ≤ 3 MB).
- AC: Given `MAIL_TRANSPORT=smtp` with verified sender, When approved, Then the message is accepted by SMTP and message-id is audited.
- Dep: FR-091.

**FR-093 (P0) Stub transport fallback.** With `MAIL_TRANSPORT=stub`, the email (headers+body) shall be written to `oss://quotemind-artifacts/outbox/{quote_number}.eml` and audited as `sent_stub`, keeping demos deterministic without DirectMail approval.
- Dep: FR-092.

**FR-094 (P0) Audit trail.** Every state transition, agent step summary, tool call, human action, waiver, and dispatch event shall append an immutable `AuditEvent` row (DM-12); `GET /api/quotes/{id}/audit` returns the ordered log.
- Dep: FR-080.

### EP-10 — Review dashboard (frontend)

**FR-100 (P0) Queue view.** The dashboard shall list quotes (status, customer, total, flags, age) with filters by status; polling every 5 s (no websockets needed).
- Dep: API-01..; FR-082.

**FR-101 (P0) Quote detail view.** Shall display: bilingual line table with per-line confidence chips and flag badges, totals panel with margin (visible only in internal view), substitution notes, critic note, memory citations ("Referenced: quote QM-2026-0007"), and PDF preview link.
- Dep: FR-082.

**FR-102 (P0) Action bar.** Approve (with waiver modal when blocking flags), Reject (comment), Revise (instruction textarea, vi/en) wired to API-06..08.
- Dep: FR-083/084.

**FR-103 (P0) Reasoning trace panel.** A collapsible timeline rendering the trace JSON (EP-11): agent nodes, tool calls with duration and token counts, memory retrievals, model ids: the demo's money shot.
- Dep: FR-110..112.

**FR-104 (P1) Eval report page.** Renders the latest eval run: metric table (pipeline vs baseline), per-case pass/fail grid.
- Dep: EP-12.

**FR-105 (P1) CDS styling.** Umber/Ochre palette, Be Vietnam Pro, sentence-case headings, APCA Lc ≥ 75 body contrast; light theme only.
- Dep: FR-100.

**FR-106 (P0) Static hosting.** Built SPA deployed to OSS static website hosting; `deploy/` includes the upload step; API base URL injected at build.
- Dep: FR-003.

### EP-11 — Observability and reasoning trace

**FR-110 (P0) OTel GenAI spans.** All model, tool, and agent invocations shall emit OpenTelemetry spans per GenAI semantic conventions: span name `{operation} {model}` (e.g. `chat qwen3-max`, `execute_tool vector_search`, `invoke_agent CatalogMatcher`), attributes `gen_ai.provider.name="dashscope"`, `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.agent.name`, `gen_ai.tool.name`, `gen_ai.usage.input_tokens/output_tokens`; exporter console (local) and OTLP endpoint if configured.
- Dep: all agents.

**FR-111 (P0) Persisted trace document.** Each quote shall persist `trace.json` to OSS: ordered steps {agent, action, tool, model, tokens_in/out, cost_usd, duration_ms, summary, memory_ids}; prompt/response bodies excluded by default (PII), included only when `TRACE_CONTENT=1`.
- Dep: FR-110.

**FR-112 (P0) Cost accounting.** Token usage per model shall be multiplied by a checked-in price table (`config/model_prices.yaml`, list prices with as-of date) to produce per-quote `cost_usd` shown in trace and eval.
- Dep: FR-110.

**FR-113 (P1) Error taxonomy.** Failures shall map to codes {PARSE_FAIL, MATCH_FAIL, PRICE_FAIL, DRAFT_FAIL, CRITIC_FAIL, DISPATCH_FAIL, TIMEOUT, MODEL_UNAVAILABLE} with retry policy: model/tool calls retried ×2 exponential backoff (1 s, 4 s) on transient errors; deterministic steps never retried.
- Dep: FR-008.

### EP-12 — Evaluation harness (Track-3 measurable gain)

**FR-120 (P0) Labeled dataset.** `eval/dataset/` shall contain 30 RFQ cases with ground-truth labels (DM-13): 10 vi text, 5 en text, 5 vi scanned PDF, 3 en digital PDF, 5 xlsx (3 vi / 2 en), 2 adversarial (ambiguous specs, out-of-catalog). Fixtures are synthetic but realistic (Appendix A generator).
- Dep: Appendix A.

**FR-121 (P0) Metrics runner.** `python -m quotemind.eval.run --mode pipeline|baseline` shall compute per-case and aggregate: line-item extraction P/R/F1, SKU top-1 accuracy, price exactness, e2e task success (items ∧ price ∧ valid PDF ∧ no blocking critic fail), human-intervention-needed rate, p50/p95 latency, tokens, cost; output `eval/reports/{ts}_{mode}.json` + markdown summary.
- Dep: FR-120.

**FR-122 (P0) Single-agent baseline.** `baseline` mode shall run one monolithic ReActAgent (same models, same tools flattened, no planner/critic/memory injection) for a fair comparison; identical metrics collected.
- AC: Report renders a side-by-side table; pipeline − baseline success delta is printed as the headline number.
- Dep: FR-121.

**FR-123 (P0) CI smoke eval.** CI shall run 5 designated cases with recorded/mocked model responses (vcr-style cassettes) asserting extraction and pricing metrics don't regress below thresholds.
- Dep: FR-121, FR-007.

**FR-124 (P1) Golden PDF snapshot test.** One approved fixture rendered and pixel-diffed (≤2%) against the checked-in golden PNG.
- Dep: FR-090.

### EP-13 — Orchestration (Track-3 architecture)

**FR-130 (P0) Pipeline orchestrator.** `src/quotemind/orchestrator.py` shall wire agents via AgentScope: sequential_pipeline for the main path, MsgHub for shared context between Drafter and Critic, DashScopeMultiAgentFormatter in multi-agent scopes, and a top-level `run_quote(quote_id)` entry both functions call.
- Dep: AGT-01..08.

**FR-131 (P0) Planner with PlanNotebook.** The Orchestrator agent shall use PlanNotebook to decompose non-trivial quotes (multi-doc, >10 lines, or flags) into subtasks and record plan state in the trace; trivial quotes may take the fast path (plan skipped, logged).
- Dep: FR-130.

**FR-132 (P0) Tool registry.** All tools shall be registered on a single `Toolkit` per agent from `src/quotemind/tools/`: async functions returning `ToolResponse`, Google-style docstrings driving schemas; MCP-backed tools registered via `toolkit.register_mcp_client` (catalog-mcp, email-mcp; stdio).
- Dep: agents.

**FR-133 (P0) Structured outputs everywhere.** Every LLM boundary that yields data shall use AgentScope `structured_model=` with the Pydantic models in DM; free-text outputs allowed only for notes/narratives.
- Dep: DM.

**FR-134 (P1) Interrupt hook.** Orchestrator shall expose `handle_interrupt` mapping to the HITL gate semantics so an in-flight run can be cancelled cleanly from the API (`POST /api/quotes/{id}/cancel`).
- Dep: FR-080.

### SUB — Hackathon submission compliance (technical prerequisites)

**SUB-01 (P0).** Repo public, Apache-2.0 LICENSE detectable in GitHub About. (FR-001)
**SUB-02 (P0).** README links `src/quotemind/cloud/alibaba_proof.py` under a heading "Proof of Alibaba Cloud Deployment" with the deployed endpoint URL. (FR-005)
**SUB-03 (P0).** `docs/architecture.md` + rendered `docs/architecture.png` (Mermaid source in repo) showing Qwen Cloud ↔ backend ↔ database ↔ frontend. (Artifact 2)
**SUB-04 (P0).** `docs/demo-script.md` and the ~3-minute public video (YouTube, "Not made for kids") following the five demo beats in §2.4. (Artifact 5)
**SUB-05 (P0).** Text description ≤ 500 words in `docs/submission-description.md` and pasted to the form. (Artifact 6)
**SUB-06 (P0).** Track declaration: "Track 4: Autopilot Agent" in README badge and submission form.
**SUB-07 (P1).** Blog post draft in `docs/blog/` (separate prize).


---

## 6. Agent behavior specifications

Each agent is a first-class, versioned requirement. Prompts below are normative starting texts stored in `src/quotemind/prompts/{agent}.md`; changes require a spec minor bump. All agents: AgentScope `ReActAgent` unless stated; formatter `DashScopeChatFormatter` (single) or `DashScopeMultiAgentFormatter` (inside MsgHub); memory = session-scoped `InMemoryMemory` hydrated from MemoryStore on resume.

### AGT-01 Orchestrator (Planner)

| Field | Value |
|---|---|
| Model | `MODEL_PLANNER` (qwen3-max, thinking on, temp 0.2) |
| Role | Owns the run; decides fast path vs planned path; sequences workers; enforces state machine |
| Tools | `get_quote_state`, `set_quote_state`, `run_agent(name)` (internal dispatch), PlanNotebook auto-tools |
| Input | quote_id, IntakeResult |
| Output | terminal pipeline state; plan trace |
| Guardrails | May not call pricing math or edit money fields; may not skip CriticValidator; max 12 reasoning iterations |
| Escalation | Any worker hard-failure twice → status `needs_manual` with reason |

System prompt (normative core):
```
You are the Orchestrator of QuoteMind, an RFQ-to-quote autopilot for a Vietnamese IT reseller.
Your job is to drive one quote from intake to pending_approval by delegating to worker agents:
Parser, CatalogMatcher, Pricing (deterministic tool), Drafter, Critic.
Rules:
1. Never compute or alter prices yourself; pricing is a deterministic tool.
2. Never skip the Critic. Never mark approved; only a human approves.
3. Use the plan notebook when the RFQ has multiple documents, more than 10 lines,
   or any needs_confirmation/blocking flag; otherwise take the fast path and say so.
4. Log a one-sentence rationale for every delegation.
5. If a worker fails twice, stop and set needs_manual with a clear reason.
Answer tool calls precisely; keep narrations under 40 words.
```

### AGT-02 IntakeClassifier

| Field | Value |
|---|---|
| Model | `MODEL_CLASSIFIER` (qwen-plus, temp 0) |
| Tools | `lookup_customer(email_domain,name_hint)` |
| Output | `IntakeResult` via structured_model |
| Guardrails | Must not attempt extraction; unknown language → `mixed`; confidence per field |

Prompt core:
```
Classify this inbound RFQ. Return only the structured object.
Detect: language (vi|en|mixed) of the main request; doc_type; urgency (urgent if
words like "gấp", "khẩn", "urgent", "asap" appear); customer via the lookup tool
(use sender domain first, then names in signature). Do not extract line items.
```

### AGT-03 DocumentParser

| Field | Value |
|---|---|
| Model | text: `MODEL_PARSER_TEXT`; vision: `MODEL_PARSER_VISION` |
| Tools | none (pure model calls orchestrated by code); xlsx path is code-only |
| Output | `RFQExtraction` |
| Guardrails | JSON only; never invent quantities: missing qty → null + low confidence; preserve original description verbatim in `raw_text`; normalize units to canonical set (cái, bộ, chiếc, cuộn, gói, license, tháng, năm, pcs, set, unit) with original kept |
| Vision specifics | one call per page image; instruction demands a ```json fenced object; merger dedupes by (normalized description, qty) |

Vision prompt core (per page):
```
You are reading page {n}/{total} of a Vietnamese or English request-for-quotation.
Extract every product line item you can see. For each: raw_text (verbatim),
description_normalized, quantity (number or null), unit (verbatim), specs (key:value),
requested_delivery (if stated), confidence 0-1.
Also capture buyer identity fields if visible (company, tax code MST, contact, email).
Return ONLY a fenced json object matching the RFQExtraction schema. Preserve all
Vietnamese diacritics exactly. Never guess numbers that are unreadable; use null.
```

### AGT-04 CatalogMatcher

| Field | Value |
|---|---|
| Model | `MODEL_DRAFTER` class model for selection reasoning (qwen3-max, temp 0) |
| Tools | `catalog_vector_search(text, top_k)`, `catalog_fts(text)`, `get_product(sku)` (all via catalog-mcp) |
| Output | `MatchResult[]` |
| Guardrails | Must pick from returned candidates only (no invented SKUs); confidence < 0.75 or spec conflict ⇒ needs_confirmation with ≤3 alternatives and bilingual reason; out-of-catalog ⇒ `no_match` line preserved for HITL |

Prompt core:
```
Match each extracted RFQ line to exactly one catalog product from the candidates
your tools return, or mark no_match. Judge by product type, brand, model number,
and hard specs (RAM, storage, size, license term). Spec downgrades are never
silent: if the best candidate differs from the request, set needs_confirmation
and explain the difference in one sentence, Vietnamese and English.
```

### AGT-05 PricingEngine (deterministic, agent-wrapped)

Not an LLM reasoner. A code service invoked as a tool `price_quote(match_results, customer, config) -> PricedQuote`. The "agent" wrapper exists only so pricing appears as a first-class traced step (`invoke_agent PricingEngine` span). Guardrail: any exception → PRICE_FAIL, never partial totals.

### AGT-06 QuoteDrafter

| Field | Value |
|---|---|
| Model | `MODEL_DRAFTER` (qwen3-max, temp 0.3) |
| Tools | `get_sop(topic)`, `get_episodic(customer_id, query)` (memory), `get_priced_quote(quote_id)` |
| Output | `Quote` via structured_model (numbers pre-filled by code; LLM fills BilingualText fields) |
| Guardrails | Numeric fields are injected read-only; drafter output failing numeric checksum is discarded and retried once, then DRAFT_FAIL. References at most the 3 provided episodic memories, cited by quote number. Tone per FR-065 |

Prompt core:
```
Draft the customer-facing language of this quotation in Vietnamese and English.
You receive the fully priced quote object; every number is final: copy them exactly.
Write: opening note, per-line substitution/lead-time notes where flagged, payment,
delivery and warranty terms grounded in the SOP snippets provided, and a closing.
If episodic memories are provided, reference relevant precedent naturally
("như báo giá QM-2026-0007..."). Formal Vietnamese first, faithful English second.
```

### AGT-07 CriticValidator

| Field | Value |
|---|---|
| Model | `MODEL_CRITIC` (qwen3-max, temp 0) + deterministic recompute in code |
| Tools | `recompute_quote(quote_id)` (pure engine), `get_policy()` |
| Output | `CriticReport` (pass/fail, flags[], bilingual note) |
| Guardrails | Numeric verdicts come only from recompute tool output; LLM writes the narrative and checks qualitative policy (terms present, tone, bilingual parity list from FR-072 code check results). A pass requires: recompute exact, no blocking flags unresolved |

### AGT-08 DispatchAgent

Code-first with LLM only for the email body courtesy text (temp 0.2, 120-word cap). Tools: `render_pdf`, `store_artifact`, `presign`, `send_email`. Guardrail: runs only from `approved`; single send per quote enforced by state machine.

### Agent-level evaluation criteria

| Agent | Metric | Target | Source |
|---|---|---|---|
| AGT-02 | classification accuracy | ≥95% | EV runner |
| AGT-03 | extraction F1 | per G-02 | EV runner |
| AGT-04 | SKU top-1 | ≥0.90 | EV runner |
| AGT-05 | price exactness | 100% | unit + EV |
| AGT-06 | numeric checksum pass on first try | ≥95% | trace stats |
| AGT-07 | catches seeded tampering | 100% (10 seeded faults) | EV fault-injection |
| AGT-08 | dispatch success | 100% (stub) | EV |

---

## 7. Data model

All Pydantic models live in `src/quotemind/models/` (frozen module path). Money = `Decimal`; timestamps = timezone-aware UTC ISO-8601; ids = ULIDs unless stated.

**DM-01 QuoteRecord** (Tablestore wide-column table `qm_quotes`, pk: `quote_id`): quote_number, status, channel, source_uri, customer_id?, language, created_at, updated_at, revision:int, flags:[str], totals_json, batch_id?, sha256_payload (idempotency, FR-024), actor_last. Secondary index on status.

**DM-02 IntakeResult**: language, doc_type, urgency, customer_match{customer_id?, method, confidence}, email_meta?.

**DM-03 RFQExtraction**: buyer{company?, mst?, contact?, email?}, lines:[RFQLine], language_per_line:[vi|en], notes_raw?. **RFQLine**: raw_text, description_normalized, quantity:Decimal?, unit, unit_original, specs:dict, requested_delivery?, confidence:float, source_span{page?,start,end}.

**DM-04 BilingualText**: `{vi:str, en:str}` — used for every human-readable field.

**DM-05 CatalogProduct** (KnowledgeStore tenant `catalog`; document_id=sku): sku, brand, category (laptop|desktop|monitor|network|server|software_license|service|accessory|telecom_service), name:BilingualText, specs:dict, unit, list_price_vnd:int, dealer_price_vnd:int, cost_price_vnd:int, vat_rate:int, stock_status(in_stock|low|out_of_stock), lead_time_days:int, warranty_months:int, text (embedded blob for retrieval), metadata mirrors filterable fields.

**DM-06 CustomerProfile** (tenant `customers`): customer_id, name, mst?, emails:[], domains:[], tier(end_customer|dealer|project), project_discount_pct:float, preferred_currency(VND|USD), preferred_language(vi|en), address, contact.

**DM-07 EpisodicQuoteMemory** (tenant `episodic:{customer_id}`): memory_id, quote_number, summary:BilingualText, items_brief:[{sku,qty,unit_price}], outcome(approved|edited|rejected), human_edits?, importance:float, created_at; embedding of summary.vi+en.

**DM-08 SOPSnippet** (tenant `sop`): topic(payment|delivery|warranty|validity|substitution), text:BilingualText, embedding.

**DM-09 MatchResult**: line_ref:int, status(matched|needs_confirmation|no_match), sku?, match_confidence, alternatives:[{sku,reason:BilingualText}] ≤3, reason:BilingualText?.

**DM-10 Quote**: quote_id, quote_number, seller_block (from config), customer_block, date, validity_days, lines:[QuoteLine], subtotal_vnd, vat_breakdown:[{rate,base,amount}], total_vnd, total_in_words_vi, usd_reference?{rate,subtotal,total,as_of}, terms{payment,delivery,warranty}:BilingualText, notes:BilingualText, flags, margin{blended_pct, per_line:[..] internal-only}, revision. **QuoteLine**: idx, sku?, description:BilingualText, unit:BilingualText, qty:Decimal, unit_price_vnd:int, discount_pct:float, line_total_vnd:int, vat_rate:int, vat_amount_vnd:int, note?:BilingualText, source(matched|substituted|no_match).

**DM-11 CriticReport**: passed:bool, blocking:[flag], non_blocking:[flag], recompute_diffs:[], note:BilingualText.

**DM-12 AuditEvent** (table `qm_audit`, pk quote_id + seq): ts, actor(agent:{name}|human|system), event, payload_json, prev_hash, hash (sha256 chain for tamper-evidence).

**DM-13 EvalCase**: case_id, input(file|text), labels{lines:[{description_canon, sku, qty}], customer_id?, expected_flags:[]}, tags.

**DM-14 TraceStep**: seq, agent, action, tool?, model?, tokens_in, tokens_out, cost_usd, duration_ms, summary, memory_ids:[].

Tablestore physical mapping: MemoryStore-managed tables for sessions/messages (SDK defaults, prefix `qm_`); KnowledgeStore-managed table+search index (vector dim 1024, FTS on `text`, filterable metadata per DM-05..08); plain OTS tables `qm_quotes`, `qm_audit`, `qm_counters` (quote numbering). Table names frozen.

---

## 8. API contracts

Base: FC HTTP trigger URL, prefix `/api`, JSON UTF-8, Bearer auth (FR-010). Errors: `{"error":{"code","message","details?"}}` with proper status.

| ID | Method & path | Request | Response | Notes |
|---|---|---|---|---|
| API-01 | POST /api/rfq | multipart file+fields OR JSON{text, customer_hint?, email_meta?} | 202 {quote_id,status} | FR-020, idempotent by content hash |
| API-02 | GET /api/quotes?status=&limit=&cursor= | — | {items:[QuoteSummary], next_cursor?} | queue |
| API-03 | GET /api/quotes/{id} | — | full review payload (FR-082) | |
| API-04 | GET /api/quotes/{id}/audit | — | {events:[AuditEvent]} | |
| API-05 | GET /api/quotes/{id}/trace | — | {steps:[TraceStep]} | |
| API-06 | POST /api/quotes/{id}/approve | {comment?, waive_flags?, reason?} | 200 {status} / 409 flags | FR-083 |
| API-07 | POST /api/quotes/{id}/reject | {comment} | 200 {status} | |
| API-08 | POST /api/quotes/{id}/revise | {instruction} | 202 {status:"revising"} | FR-084 |
| API-09 | GET /api/quotes/{id}/pdf | — | 302 presigned URL | FR-091 |
| API-10 | POST /api/quotes/{id}/cancel | — | 200 | FR-134 |
| API-11 | GET /health | — | {status,version,models} | no auth |
| API-12 | POST /api/demo/seed | {} | 200 seeding report | guarded by token; idempotent |
| API-13 | GET /api/eval/latest | — | latest eval report json | FR-104 |

OpenAPI 3.1 file generated to `docs/openapi.json` in CI (P1).

---

## 9. Non-functional requirements

**NFR-001 (P0) Latency.** p50 RFQ→pending_approval ≤ 90 s (text) / 150 s (scan); approve→email dispatched ≤ 30 s. Measured by EV runner.
**NFR-002 (P0) Determinism of money.** Identical inputs yield byte-identical priced outputs (Decimal, no wall-clock in math besides quote date field).
**NFR-003 (P0) Cost.** Typical text RFQ ≤ US$0.05 model cost; scan ≤ US$0.15 (trace-verified).
**NFR-004 (P0) Resilience.** Transient model/tool failures retried per FR-113; a single page's vision failure degrades to partial extraction with flag, not run failure.
**NFR-005 (P0) Statelessness.** No pipeline state outside Tablestore/OSS; any FC instance can serve any request.
**NFR-006 (P0) Security.** Secrets only via env; buckets private; presigned URLs ≤ 10 min; bearer token on all mutating routes; RAM user least-privilege (OSS rw two buckets, OTS rw one instance, DirectMail send).
**NFR-007 (P0) Privacy/PDPL.** Customer personal data stored only in Tablestore/OSS (both in-region), trace excludes message bodies by default (FR-111); `docs/privacy.md` documents data categories, purpose, retention (90-day demo purge script) aligned with Vietnam PDPL (effective 2026-01-01).
**NFR-008 (P0) i18n correctness.** UTF-8 end-to-end; Vietnamese collation-safe search normalization (NFC); VND/date formats per locale (dd/mm/yyyy).
**NFR-009 (P1) Accessibility.** Dashboard body text APCA Lc ≥ 75; keyboard-operable action bar.
**NFR-010 (P1) Code quality.** ruff clean; mypy (basic) clean; pricing engine 100% branch coverage; overall unit coverage ≥ 70%.
**NFR-011 (P0) Reproducibility.** `make demo` seeds + runs UJ-01..04 against a fresh environment with zero manual steps besides env vars.
**NFR-012 (P1) Availability.** Demo-grade: FC default scaling; no SLA; documented.

---

## 10. Evaluation and testing requirements

**EV-01 (P0)** Unit: pricing (property-based), bằng chữ converter, state machine, formatters, audit hash chain.
**EV-02 (P0)** Contract: Pydantic schema round-trips; API responses validate against OpenAPI.
**EV-03 (P0)** Integration: pipeline over 5 cassette-mocked cases in CI (FR-123).
**EV-04 (P0)** Full eval: 30-case runner, pipeline vs baseline (FR-121/122); thresholds = §3.1 targets; report committed to `eval/reports/`.
**EV-05 (P0)** Fault injection: 10 tampered drafts → critic catch rate 100% (AGT-07).
**EV-06 (P1)** Language QA: 10 sampled quotes scored 1–5 by rubric (fluency, register, faithfulness) per language; ≥4 average. Scored by a separate qwen3-max judge prompt with the rubric embedded; human spot-check 3.
**EV-07 (P1)** Load sanity: 5 concurrent RFQs complete without cross-talk (session isolation).
**EV-08 (P0)** Demo rehearsal checklist: UJ-01..05 executed on the deployed stack, timed, screen-recorded once before the final video.

---

## 11. Traceability matrix (condensed)

| Need (rubric/user) | FRs | Eval |
|---|---|---|
| Ambiguous input handling (Track 4) | FR-034, 042, 063, 071, UJ-03 | EV-04 adversarial cases |
| External tool invocation (Track 4) | FR-132, MCP tools, FR-092 | EV-03 |
| HITL checkpoints (Track 4) | FR-080..085, 102 | EV-04, EV-08 |
| Production-readiness | D-03, FR-050..055, 070, 094, NFR-002/005/006 | EV-01, EV-05 |
| Memory: storage/retrieval/forgetting (Track 1 fold-in) | FR-040..049 | EV-04 (UJ-04 case), unit gc tests |
| Multi-agent measurable gain (Track 3 fold-in) | FR-130..133, 121/122 | EV-04 headline delta |
| Qwen API sophistication | §4.6 routing, FR-032 vision, FR-041 embeddings, structured outputs FR-133 | trace/report |
| Alibaba deployment proof | FR-003/004/005, SUB-02 | manual + health |
| Bilingual value | FR-061, 055, 090, EV-06 | EV-06 |
| Visible reasoning (Presentation) | FR-103, 110..112 | EV-08 |

Full FR→test mapping is maintained in `docs/traceability.csv` (generated, P1).

---

## 12. DO-NOT-CHANGE registry (frozen contracts)

1. Model constant names and file: `src/quotemind/config/models.py` (§4.6).
2. Env var names (§4.7).
3. Pydantic model names/fields DM-01..14 and module path `src/quotemind/models/`.
4. API routes and verbs API-01..13.
5. Tablestore table names: `qm_quotes`, `qm_audit`, `qm_counters`, SDK-managed `qm_*` prefixes; KnowledgeStore tenants `catalog`, `customers`, `episodic:{customer_id}`, `sop`.
6. OSS bucket names and key layouts: `quotemind-inbox/rfq/...`, `quotemind-artifacts/{quotes,outbox,pages,traces}/...`.
7. Quote number format `QM-YYYY-NNNN`.
8. Embedding dimension 1024.
9. Status enum values of the state machine (FR-080).
10. Trace step schema DM-14.

Any change requires bumping this spec to 1.1+ and updating `docs/verification-log.md`.

---

## 13. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Model ID unavailable in Singapore at build time | Medium | High | FR-012 bootstrap check + frozen fallbacks |
| `tablestore-for-agent-memory` signature drift vs docs | Medium | Medium | Appendix E verification step before EP-04 coding; thin adapter layer `src/quotemind/memory/store.py` isolates SDK |
| WeasyPrint native libs on FC | Medium | Medium | Custom container image path in `deploy/Dockerfile.pdf` as fallback; render tested in CI container matching FC base |
| DirectMail sender verification delay | High | Low | FR-093 stub transport is the demo default |
| Vision extraction quality on worst scans | Medium | Medium | Demo uses vetted fixtures; adversarial cases scored but not demoed live |
| AgentScope 1.x → 2.0 churn | Medium | Medium | Pin exact version; no agentscope-runtime dependency (D-02) |
| Two-week clock | — | High | Critical path in §Document control note; P2s cut first; vertical slice by day 6 |

## 14. Glossary
See §1.4. Additional: **cassette** = recorded model I/O for offline tests; **blocking flag** = flag that prevents approve without waiver; **fast path** = plan-skipped simple pipeline.


---

## Appendix A — Seed data specification

Seed generator `src/quotemind/seed/generate.py` produces deterministic fixtures (seeded RNG) so eval labels stay valid.

**A.1 Catalog (60 SKUs).** Distribution: 14 laptops (Dell Latitude/XPS, Lenovo ThinkPad, HP EliteBook, Asus ExpertBook), 6 desktops, 8 monitors (Dell, LG, Samsung 24–32"), 8 networking (Cisco/ TP-Link switches, Ubiquiti APs, firewall), 4 servers/NAS (Dell PowerEdge, Synology), 10 software licenses (Microsoft 365 Business, Windows 11 Pro, Office LTSC, Adobe CC, antivirus, per-seat/year), 6 services (cài đặt/installation, bảo trì/maintenance-month, triển khai/deployment-day), 4 accessories (dock, RAM, SSD, UPS). Fields per DM-05; realistic VND price points (laptop list 18–52M; licenses 1.2–9.8M/seat-year; services 1.5–12M); cost_price set for margins 6–18%; 6 SKUs `out_of_stock` with lead_time 14–30 days; 1 `telecom_service` SKU (SIM data plan) to exercise the 10% VAT rule. Bilingual names, e.g. `{"vi":"Máy tính xách tay Dell Latitude 5450 (Core i7, 32GB, 512GB)","en":"Dell Latitude 5450 laptop (Core i7, 32GB, 512GB)"}`.

**A.2 Customers (8).** 3 end_customer (incl. one English-preferring FDI firm "Sunrise Manufacturing Vietnam Co., Ltd.", USD reference), 3 dealer, 2 project (project_discount_pct 3 and 5). One customer has rich episodic history (see A.3) for UJ-04. MSTs are synthetic 10-digit (mark clearly as demo data).

**A.3 Historical quotes (6 episodic memories).** For customer `cust_thanhcong` (dealer): includes QM-2026-0007 with a Latitude 5440→5450 substitution accepted and 2% extra dealer discount noted; ages spread 10–220 days to exercise decay; importances varied so gc demo prunes ≥1.

**A.4 SOP snippets (10).** payment (2: 100% trước giao hàng; 50/50), delivery (2), warranty (2), validity (2), substitution policy (2). Bilingual.

**A.5 Eval RFQ fixtures (30 + 5 CI cassettes).** Composition per FR-120. Vietnamese text example fixture `eval/dataset/vi_text_003.txt`:
```
Kính gửi Quý công ty,
Công ty TNHH Thành Công cần báo giá các mặt hàng sau:
1. Laptop Dell Latitude 5450, Core i7, RAM 32GB, SSD 512GB - số lượng 20 cái
2. Màn hình Dell 27 inch P2723DE - 20 cái
3. Bản quyền Microsoft 365 Business Standard - 25 user/năm
Giao hàng tại TP.HCM trong 2 tuần. Đề nghị báo giá gồm VAT.
Trân trọng, Nguyễn Văn A - 0909xxxxxx
```
Scanned fixtures are generated: HTML → PDF → raster → slight rotate/noise (ImageMagick) to simulate scans; ground truth stored alongside (DM-13). The vetted demo scan fixture is `eval/dataset/vi_scan_002.pdf` (UJ-02). Two adversarial: (i) "máy tính bảng vẽ Wacom" (out-of-catalog), (ii) conflicting spec ("Latitude 5450 RAM 64GB" — catalog max 32GB).

**A.6 Demo seller identity (config, not code):** "CyberSkill Demo Distribution JSC" — address/MST/bank block clearly marked SAMPLE; do not use real CyberSkill MST in the public repo.

## Appendix B — Vietnam VAT quick reference (2026, normative for FR-052)

- Legal basis: Nghị quyết 204/2025/QH15; Nghị định 174/2025/NĐ-CP: 2% reduction (10→8%) effective 01/07/2025–31/12/2026 for goods/services otherwise at 10%, including IT goods/services, EXCLUDING: viễn thông (telecom), tài chính-ngân hàng-chứng khoán-bảo hiểm, bất động sản, kim loại & sản phẩm kim loại, khai khoáng (trừ than), hàng chịu thuế TTĐB.
- QuoteMind mapping: catalog categories laptop/desktop/monitor/network/server/software_license/service/accessory → 8%; telecom_service → 10%; vat_rate stored per SKU; per-line override allowed at revise with audit.
- Footer note template (vi): "Thuế GTGT áp dụng theo Nghị định 174/2025/NĐ-CP (thuế suất ưu đãi 8% đến 31/12/2026, trừ nhóm loại trừ)." (en): "VAT applied per Decree 174/2025/ND-CP (reduced 8% rate through 31 Dec 2026, excluded groups at 10%)."
- Quotes are pre-contract documents; no e-invoice issuance in scope.

## Appendix C — Quote PDF layout specification (normative for FR-090)

A4 portrait, margins 18 mm; Be Vietnam Pro (400/600/700), body 10.5 pt, VI text primary weight, EN italic secondary on the line below or right column per block.
1. Header band: Umber #45210E background, seller logo left (SVG placeholder), white seller name; right-aligned "BÁO GIÁ / QUOTATION", quote number, date. Ochre #F4BA17 2 pt rule beneath.
2. Two-column blocks: seller (left): name, address, MST, phone, email; customer (right): name, address, MST?, contact, email. Labels bilingual "Bên bán / Seller".
3. Meta row: Hiệu lực/Validity: {n} ngày/days · Tiền tệ/Currency: VND (USD reference {rate}) · Điều kiện/Terms ref.
4. Line table (repeats header each page): STT | Mô tả hàng hóa, dịch vụ / Description | ĐVT / Unit | SL / Qty | Đơn giá (VNĐ) / Unit price | Thành tiền (VNĐ) / Amount. Zebra rows (2% Umber tint); substitution/lead-time notes as indented small rows under their line, Ochre left border.
5. Totals block right-aligned: Cộng tiền hàng / Subtotal; per-rate VAT lines "Thuế GTGT 8% / VAT 8%"; TỔNG CỘNG / TOTAL bold on Ochre tint; USD reference line if enabled; "Bằng chữ / In words:" full-width italic.
6. Terms grid (2×2): Thanh toán/Payment, Giao hàng/Delivery, Bảo hành/Warranty, Ghi chú/Notes.
7. Bank block: Ngân hàng/Bank, Chủ TK/Beneficiary, Số TK/Account, SWIFT.
8. Signature row: left "Người lập / Prepared by" (agent name "QuoteMind" + reviewer), right "Đại diện bên bán / For the Seller" with space + "(Ký, ghi rõ họ tên / Sign, full name)".
9. Footer every page: VAT policy note (App. B), FX note, "Trang/Page X/Y", generated-by line with quote_id short hash.
Print CSS: `@page { size: A4; margin: 18mm }`, running header via `position: running()`; table `page-break-inside: avoid` on rows.

## Appendix D — Repository layout (frozen top level)

```
quotemind/
├── LICENSE                       # Apache-2.0 (SUB-01)
├── README.md                     # quickstart, proof link (SUB-02), track badge
├── pyproject.toml                # pinned deps (§4.4)
├── Makefile                      # setup/dev/test/eval/demo/deploy targets
├── .env.example
├── deploy/
│   ├── s.yaml                    # FC 3.0 (FR-003)
│   ├── provision.py              # FR-004
│   └── Dockerfile.pdf            # WeasyPrint fallback image
├── src/quotemind/
│   ├── config/{settings.py,models.py,model_prices.yaml}
│   ├── models/                   # DM-01..14 (frozen)
│   ├── agents/                   # AGT-01..08 builders
│   ├── prompts/                  # normative prompt files
│   ├── tools/                    # Toolkit functions
│   ├── mcp_servers/{catalog_mcp.py,email_mcp.py}
│   ├── pricing/engine.py         # EP-05 pure functions
│   ├── memory/{store.py,gc.py}   # SDK adapter + forgetting
│   ├── parsing/{text.py,vision.py,excel.py,raster.py}
│   ├── quote/{assemble.py,render/ (templates, fonts/), numbering.py}
│   ├── orchestrator.py           # FR-130/131
│   ├── api/app.py                # FastAPI-style web function
│   ├── cloud/{alibaba_proof.py,oss.py,tablestore.py,mail.py}
│   ├── obs/{otel.py,trace.py,cost.py}
│   └── seed/generate.py
├── frontend/                     # EP-10 SPA
├── eval/{dataset/,run.py,baseline.py,reports/}
├── tests/                        # unit + integration + cassettes
└── docs/{architecture.md,architecture.png,openapi.json,demo-script.md,
         submission-description.md,privacy.md,verification-log.md,blog/}
```

## Appendix E — Pre-implementation verification snippets (run before EP-04/EP-03 coding; log results)

```python
# E.1 tablestore-for-agent-memory surface check
import inspect, tablestore_for_agent_memory as tam  # confirm actual import name from wheel metadata
from tablestore_for_agent_memory.memory_store import MemoryStore   # adjust to real paths
from tablestore_for_agent_memory.knowledge_store import KnowledgeStore, Filters
print(inspect.signature(MemoryStore.__init__)); print(inspect.signature(KnowledgeStore.__init__))
print([m for m in dir(MemoryStore) if not m.startswith('_')])
print([m for m in dir(KnowledgeStore) if not m.startswith('_')])
```
```python
# E.2 model availability probe (also used by FR-012)
from openai import OpenAI; import os
c = OpenAI(api_key=os.environ["DASHSCOPE_API_KEY"], base_url=os.environ["DASHSCOPE_BASE_URL"])
for m in ["qwen3-max","qwen-plus","qwen-vl-ocr","qwen3-vl-plus","text-embedding-v4"]:
    try:
        if "embedding" in m: c.embeddings.create(model=m, input=["ping"], dimensions=1024)
        else: c.chat.completions.create(model=m, messages=[{"role":"user","content":"ping"}], max_tokens=1)
        print("OK", m)
    except Exception as e: print("FAIL", m, type(e).__name__, str(e)[:120])
```
```python
# E.3 AgentScope structured output smoke
from agentscope.agent import ReActAgent
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
from pydantic import BaseModel
class Ping(BaseModel): ok: bool
# construct agent with qwen-plus; call with structured_model=Ping; assert res.metadata["ok"] in (True, False)
```

## Appendix F — Two-week implementation schedule (guidance, not requirements)

| Days | Milestone | FRs |
|---|---|---|
| 1 | Repo, config, provision, proof module, health | FR-001..005, 008..010, 012 |
| 2 | Seed data + memory adapter verified (App. E) | FR-011, 040, 041, 047 |
| 3–4 | Parsing all three input types | FR-030..034, 022, 020/021, 024 |
| 5 | Matching + pricing engine + tests | FR-042/043, 050..056 |
| 6 | Drafter + vertical slice UJ-01 local | FR-060..063, 130, 132/133 |
| 7 | Critic + state machine + HITL API | FR-070..073, 080..084 |
| 8 | PDF + dispatch + audit | FR-090..094, 062 |
| 9 | Dashboard MVP | FR-100..103, 106 |
| 10 | Observability + traces in UI | FR-110..113 |
| 11 | Eval harness + baseline + reports | FR-120..123 |
| 12 | Memory depth polish (gc, UJ-04), planner path | FR-045/046/049, 131 |
| 13 | Deploy hardening, EV-08 rehearsal, docs, diagram, video shoot | SUB-01..07 |
| 14 | Buffer, final eval numbers, submission | — |

---

*End of QM-SPEC-001 v1.0.0. Subsequent artifacts (architecture diagram pack, repo blueprint detail, agent spec sheets, demo script, submission description) derive from and must remain consistent with this document.*
