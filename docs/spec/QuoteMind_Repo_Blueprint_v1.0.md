# QuoteMind — Repository Structure Blueprint

**Document ID:** QM-REPO-001 · **Version:** 1.0.0 · **Date:** 2026-07-10 · **Status:** Approved
**Parent spec:** QM-SPEC-001 v1.0.0 (PRD+SRS), which freezes the top-level layout in Appendix D. This blueprint elaborates every directory and file so Cowork agents scaffold identically. On conflict, the parent spec wins.

---

## 1. Purpose

This blueprint tells an implementing agent exactly where every piece of code lives, what each module exports, what may import what, and which files are frozen contracts. Follow it and independently-built features will compose without merge pain; deviate and the DO-NOT-CHANGE registry in the parent spec is violated.

## 2. Design principles

1. **One package, two entrypoints.** All Python lives under `src/quotemind/`; the two FC functions and the CLI tools are thin shells over the same package. No logic in handlers.
2. **Layered imports, enforced.** `models` imports nothing internal; `pricing` imports only `models`; `agents` import `tools`, `prompts`, `models`; `api` imports `orchestrator`; nothing imports `api`. Import-linter contract in CI (see §8) fails the build on violation.
3. **Frozen names are load-bearing.** Env vars, model constants, table names, bucket keys, API routes, Pydantic modules: renaming any of them breaks the spec. They are listed once in `src/quotemind/config/` and imported everywhere else.
4. **Determinism where money lives.** `pricing/` and `quote/numbering.py` are pure; they have no network, no clock beyond an injected `today`, and 100% branch coverage gates.
5. **Everything demo-critical has a make target.** If a reviewer cannot run it with one command, it does not exist.

## 3. Full repository tree (normative)

Files marked ★ are frozen contracts (DO-NOT-CHANGE registry). Files marked ⚙ are generated, never hand-edited.

```
quotemind/
├── LICENSE                                ★ Apache-2.0 full text (SUB-01)
├── README.md                                quickstart · badges · proof link (SUB-02) · diagram embed
├── pyproject.toml                         ★ package meta + pinned deps (§4.4 parent)
├── Makefile                                 canonical entrypoints (§7)
├── .env.example                           ★ every env var from parent §4.7, commented
├── .gitignore                               python, node, .env, eval/reports/*.json artifacts
├── .github/
│   └── workflows/
│       ├── ci.yml                           lint → type → unit → smoke-eval → diagram render
│       └── deploy.yml                       manual-dispatch s deploy (needs secrets)
├── deploy/
│   ├── s.yaml                             ★ FC 3.0 descriptor: both functions (FR-003)
│   ├── provision.py                         idempotent buckets/tables/indexes (FR-004)
│   ├── layer/
│   │   └── build_weasyprint_layer.sh        builds Pango/Cairo layer zip for FC
│   └── Dockerfile.pdf                       fallback custom-container image (risk #3)
├── docs/
│   ├── architecture.md                      QM-ARCH-001 content, PNGs embedded
│   ├── diagrams/
│   │   ├── architecture.mmd               ★ submission diagram source
│   │   ├── architecture.png               ⚙ rendered in CI
│   │   ├── pipeline-sequence.mmd
│   │   └── pipeline-sequence.png          ⚙
│   ├── openapi.json                       ⚙ exported from the app (API-01..13)
│   ├── demo-script.md                       artifact 5 (SUB-04)
│   ├── submission-description.md            artifact 6 (SUB-05)
│   ├── privacy.md                           PDPL mapping (NFR-007)
│   ├── verification-log.md                  Appendix E results, version pins record
│   ├── traceability.csv                   ⚙ FR→test map (P1)
│   └── blog/
│       └── building-quotemind.md            SUB-07 draft
├── src/
│   └── quotemind/
│       ├── __init__.py                      __version__ single source
│       ├── config/
│       │   ├── settings.py                ★ pydantic-settings; fail-fast on missing P0 vars (FR-002)
│       │   ├── models.py                  ★ MODEL_* constants + FALLBACKS dict (§4.6)
│       │   ├── seller.py                    demo seller identity block (Appendix A.6)
│       │   └── model_prices.yaml          ★ price table with as_of date (FR-112)
│       ├── models/                        ★ DM-01..14, one file per aggregate
│       │   ├── __init__.py                  re-exports all public models
│       │   ├── common.py                    BilingualText, Money helpers, ULID, enums
│       │   ├── quote_record.py              DM-01 + Status enum + transition table
│       │   ├── intake.py                    DM-02
│       │   ├── extraction.py                DM-03 RFQExtraction, RFQLine
│       │   ├── catalog.py                   DM-05, DM-06 (CatalogProduct, CustomerProfile)
│       │   ├── memory.py                    DM-07, DM-08
│       │   ├── matching.py                  DM-09
│       │   ├── quote.py                     DM-10 Quote, QuoteLine, Totals
│       │   ├── critic.py                    DM-11
│       │   ├── audit.py                     DM-12 AuditEvent + hash chain fn
│       │   ├── eval.py                      DM-13
│       │   └── trace.py                     DM-14
│       ├── pricing/
│       │   ├── engine.py                  ★ pure functions (FR-050..054)
│       │   ├── vat.py                       VAT table + policy note (FR-052, App. B)
│       │   └── words_vi.py                  bằng chữ converter (FR-055)
│       ├── parsing/
│       │   ├── router.py                    doc_type → parser dispatch
│       │   ├── text.py                      qwen-plus structured extraction (FR-030)
│       │   ├── vision.py                    page-image → qwen-vl-ocr (FR-032)
│       │   ├── excel.py                     openpyxl deterministic (FR-033)
│       │   └── raster.py                    pypdfium2 rasterizer (FR-031)
│       ├── memory/
│       │   ├── store.py                   ★ THE adapter over tablestore-for-agent-memory
│       │   ├── episodic.py                  write/retrieve with importance×decay (FR-044..046)
│       │   ├── gc.py                        forgetting + compaction CLI (FR-046)
│       │   └── budget.py                    2500-token context guard (FR-049)
│       ├── tools/
│       │   ├── registry.py                  build_toolkit(agent_name) factory (FR-132)
│       │   ├── catalog_tools.py             vector/fts/get_product (wraps MCP client)
│       │   ├── memory_tools.py              get_episodic, get_sop
│       │   ├── pricing_tools.py             price_quote, recompute_quote
│       │   ├── state_tools.py               get/set_quote_state (guarded transitions)
│       │   └── dispatch_tools.py            render_pdf, store_artifact, presign, send_email
│       ├── mcp_servers/
│       │   ├── catalog_mcp.py               FastMCP stdio server (C-05)
│       │   └── email_mcp.py                 send + stub inbox
│       ├── agents/
│       │   ├── factory.py                   build_agent(name) → ReActAgent wired per AGT spec
│       │   ├── orchestrator_agent.py        AGT-01 (+PlanNotebook policy)
│       │   ├── intake.py … dispatch.py      AGT-02..08, one file each
│       ├── prompts/                        ★ normative prompt .md files, versioned header
│       │   ├── orchestrator.md · intake.md · parser_text.md · parser_vision.md
│       │   ├── matcher.md · drafter.md · critic.md · dispatch_email.md
│       ├── quote/
│       │   ├── assemble.py                  code-side numeric injection + checksum (FR-060)
│       │   ├── numbering.py               ★ QM-YYYY-NNNN atomic counter (FR-062)
│       │   └── render/
│       │       ├── template_quote.html.j2   Appendix C layout
│       │       ├── quote.css                print CSS, CDS tokens
│       │       └── fonts/                   BeVietnamPro-{Regular,SemiBold,Bold}.ttf (OFL)
│       ├── orchestrator.py                ★ run_quote(quote_id) single entry (FR-130/131)
│       ├── api/
│       │   ├── app.py                       FastAPI app, routes API-01..13
│       │   ├── auth.py                      Bearer middleware (FR-010)
│       │   └── handlers_fc.py               FC HTTP + OSS-event shims → app / run_quote
│       ├── cloud/
│       │   ├── alibaba_proof.py           ★ deployment proof module (FR-005, SUB-02)
│       │   ├── oss.py                       V4 auth, put/get, presign slash_safe (FR-091)
│       │   ├── tablestore.py                OTSClient factory + qm_* plain tables
│       │   └── mail.py                      DirectMail SMTP + stub transport (FR-092/093)
│       ├── obs/
│       │   ├── otel.py                      tracer setup, GenAI span helpers (FR-110)
│       │   ├── trace.py                     TraceStep collector → OSS trace.json (FR-111)
│       │   └── cost.py                      token×price accounting (FR-112)
│       ├── eval_/                            (trailing underscore: avoid stdlib-ish clash)
│       │   ├── run.py                       pipeline|baseline runner (FR-121)
│       │   ├── baseline.py                  monolithic single agent (FR-122)
│       │   ├── metrics.py                   F1, accuracy, success, latency, cost
│       │   └── judge_language.py            EV-06 rubric judge
│       └── seed/
│           ├── generate.py                  deterministic fixtures (Appendix A)
│           └── data/                        static seeds: sop.json, customers.json …
├── frontend/
│   ├── package.json · vite.config.ts · index.html
│   ├── src/
│   │   ├── main.tsx · api.ts (typed client of API-01..13) · theme.css (CDS tokens)
│   │   ├── pages/{Queue,QuoteDetail,EvalReport}.tsx
│   │   └── components/{LineTable,FlagBadge,ConfidenceChip,TracePanel,ActionBar,WaiverModal}.tsx
│   └── dist/                              ⚙ built, uploaded to OSS by make deploy-frontend
├── eval/
│   ├── dataset/                             30 fixtures + labels.json (DM-13) + cassettes/
│   └── reports/                           ⚙ {ts}_{mode}.json + summary.md
└── tests/
    ├── unit/        pricing, words_vi, state machine, audit chain, formatters, budget
    ├── contract/    schema round-trips, OpenAPI conformance
    ├── integration/ 5 cassette pipeline cases (FR-123), memory adapter live-optional
    └── golden/      quote_golden.png + pixel-diff test (FR-124)
```

## 4. Module contracts (what each package exports and may import)

| Package | Public surface (import from here only) | May import | Must NOT import |
|---|---|---|---|
| `config` | `settings`, `MODEL_*`, `FALLBACKS`, `SELLER_BLOCK` | stdlib, pydantic | anything internal |
| `models` | all DM classes, `Status`, `LEGAL_TRANSITIONS` | `config.settings` (types only) | agents, tools, api |
| `pricing` | `unit_price, line_total, vat_amount, quote_totals, margin, vat_policy_note, amount_in_words_vi` | `models` | network, agents, clock (inject `today`) |
| `parsing` | `parse(intake, payload) -> RFQExtraction` | `models`, `config`, `cloud.oss`, model client | `agents` (parsers are called BY agents/tools) |
| `memory` | `MemoryFacade` (sessions, episodic, sop, catalog search), `run_gc()` | `models`, `config`, `cloud.tablestore`, embeddings client | `agents` |
| `tools` | `build_toolkit(agent_name)` and individual async tool fns returning `ToolResponse` | `memory`, `pricing`, `parsing`, `quote`, `cloud`, `models` | `api` |
| `agents` | `build_agent(name) -> ReActAgent` | `tools`, `prompts` (file read), `config`, `models` | `api`, `orchestrator` |
| `orchestrator` | `run_quote(quote_id) -> Status` | `agents`, `models`, `memory`, `obs` | `api` |
| `api` | FastAPI `app`, FC handlers | `orchestrator`, `models`, `config`, `cloud` | — (top of the stack) |
| `cloud` | `oss`, `tablestore`, `mail`, `alibaba_proof` | `config` | `agents`, `api` |
| `obs` | `span()`, `record_step()`, `flush_trace()` | `config`, `models.trace` | business packages |
| `eval_` | CLI `run` | `orchestrator`, `models`, `metrics` | `api` |

Enforcement: `pyproject.toml` carries an `importlinter` config with these layers; CI job `lint` runs it (§8).

## 5. Frozen-contract file stubs (verbatim starting points)

### 5.1 `src/quotemind/config/models.py` ★

```python
"""Model routing constants — QM-SPEC-001 §4.6. FROZEN names."""
MODEL_PLANNER = "qwen3-max"
MODEL_CLASSIFIER = "qwen-plus"
MODEL_PARSER_TEXT = "qwen-plus"
MODEL_PARSER_VISION = "qwen-vl-ocr"
MODEL_DRAFTER = "qwen3-max"
MODEL_CRITIC = "qwen3-max"
MODEL_EMBED = "text-embedding-v4"
EMBED_DIMENSIONS = 1024  # FROZEN (parent §12.8)

FALLBACKS = {
    "qwen3-max": "qwen-max",
    "qwen-vl-ocr": "qwen3-vl-plus",
}
```

### 5.2 `src/quotemind/models/quote_record.py` — Status machine core ★

```python
class Status(str, Enum):
    RECEIVED = "received"; PARSING = "parsing"; MATCHING = "matching"
    PRICING = "pricing"; DRAFTING = "drafting"; VALIDATING = "validating"
    PENDING_APPROVAL = "pending_approval"; APPROVED = "approved"
    DISPATCHING = "dispatching"; SENT = "sent"; REJECTED = "rejected"
    REVISING = "revising"; NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_MANUAL = "needs_manual"
    FAILED_INTAKE = "failed_intake"; FAILED_PARSE = "failed_parse"
    FAILED_PRICE = "failed_price"; FAILED_DRAFT = "failed_draft"
    CRITIC_FAILED = "critic_failed"; FAILED_DISPATCH = "failed_dispatch"

LEGAL_TRANSITIONS: dict[Status, set[Status]] = {
    Status.RECEIVED: {Status.PARSING, Status.FAILED_INTAKE},
    Status.PARSING: {Status.MATCHING, Status.NEEDS_CLARIFICATION, Status.FAILED_PARSE},
    Status.MATCHING: {Status.PRICING},
    Status.PRICING: {Status.DRAFTING, Status.FAILED_PRICE},
    Status.DRAFTING: {Status.VALIDATING, Status.FAILED_DRAFT, Status.NEEDS_MANUAL},
    Status.VALIDATING: {Status.PENDING_APPROVAL, Status.CRITIC_FAILED},
    Status.PENDING_APPROVAL: {Status.APPROVED, Status.REJECTED, Status.REVISING},
    Status.REVISING: {Status.DRAFTING, Status.NEEDS_MANUAL},
    Status.APPROVED: {Status.DISPATCHING},
    Status.DISPATCHING: {Status.SENT, Status.FAILED_DISPATCH},
}
```

### 5.3 `deploy/s.yaml` skeleton ★

```yaml
edition: 3.0.0
name: quotemind
access: default
vars:
  region: ap-southeast-1
resources:
  quotemind-api:
    component: fc3
    props:
      region: ${vars.region}
      functionName: quotemind-api
      runtime: python3.12          # fallback python3.10 (parent open item 3)
      code: ../src_build
      handler: quotemind.api.handlers_fc.http_handler
      memorySize: 1024
      timeout: 300
      instanceLifecycleConfig:
        initializer: { handler: quotemind.api.handlers_fc.initializer, timeout: 30 }
      environmentVariables: { ... injected at deploy ... }
      triggers:
        - triggerName: http, triggerType: http
          triggerConfig: { authType: anonymous, methods: [GET, POST] }
  quotemind-ingest:
    component: fc3
    props:
      region: ${vars.region}
      functionName: quotemind-ingest
      runtime: python3.12
      code: ../src_build
      handler: quotemind.api.handlers_fc.oss_event_handler
      memorySize: 1024
      timeout: 300
      triggers:
        - triggerName: oss-rfq, triggerType: oss
          sourceArn: acs:oss:${vars.region}:${config(accountID)}:quotemind-inbox
          triggerConfig:
            events: ["oss:ObjectCreated:*"]
            filter: { key: { prefix: "rfq/" } }
```

(Trigger schema fields to be confirmed against Serverless Devs fc3 docs at deploy time; record in verification log.)

## 6. Naming conventions

- Python: `snake_case` modules/functions, `PascalCase` Pydantic models matching DM names exactly; async tool functions verb-first (`price_quote`, `get_episodic`).
- Frontend: components `PascalCase.tsx`; API client mirrors route names (`approveQuote`).
- Branches: `feat/FR-042-catalog-matcher`, `fix/...`; one FR (or tight FR cluster) per PR; PR title starts with the FR id — this is how traceability.csv is generated.
- Commits: conventional commits; scope = package (`feat(pricing): FR-052 VAT rules`).
- Prompt files: header block `<!-- prompt: drafter | version: 1.0 | agent: AGT-06 | spec: QM-SPEC-001 -->`; any edit bumps version and is a reviewed change.

## 7. Makefile targets (canonical entrypoints)

| Target | Does |
|---|---|
| `make setup` | `uv sync` (or pip install -e .[dev]) + frontend `npm ci` |
| `make verify` | runs Appendix E snippets; writes `docs/verification-log.md` entries |
| `make test` | unit + contract (offline, cassette-only) |
| `make eval-smoke` | 5 cassette cases (FR-123) |
| `make eval` | full 30-case pipeline run (live models) |
| `make eval-baseline` | baseline mode + side-by-side report |
| `make dev` | local API on :9000 (`QM_ENV=local`) |
| `make seed` | `python -m quotemind.seed` (FR-011) |
| `make demo` | seed + drive UJ-01..04 against target env (NFR-011) |
| `make gc` | memory garbage collection demo (FR-046) |
| `make diagrams` | re-render .mmd → .png |
| `make deploy` | s deploy + provision + smoke `/health` |
| `make deploy-frontend` | build SPA + OSS upload |
| `make proof` | `python -m quotemind.cloud.alibaba_proof` (SUB-02 evidence) |

## 8. CI pipeline (`.github/workflows/ci.yml`)

Jobs (all required on PR to main):
1. **lint** — ruff, import-linter layer contract (§4).
2. **type** — mypy basic.
3. **unit** — tests/unit + contract; coverage gate: pricing 100% branch, overall ≥70% (NFR-010).
4. **smoke-eval** — FR-123 cassettes; thresholds from parent §3.1 encoded as asserts.
5. **golden-pdf** — container with WeasyPrint deps; pixel-diff ≤2% (FR-124).
6. **diagrams** — mmdc render; fail if .png differs from committed (prevents drift).
`deploy.yml` is manual `workflow_dispatch` only; requires repo secrets; never runs on PR.

## 9. Bootstrap order for Cowork (first five PRs)

1. **PR-1 (FR-001/002/008/009/010):** scaffold, settings, logging, health, auth — repo boots.
2. **PR-2 (models package, DM-01..14 + state machine tests):** the shared language.
3. **PR-3 (FR-050..055 pricing + words_vi, 100% coverage):** money is done and frozen early.
4. **PR-4 (Appendix E verify + memory adapter `memory/store.py` + provision):** riskiest external contract pinned.
5. **PR-5 (FR-005 alibaba_proof + deploy s.yaml + make deploy):** deployment proof exists from week 1.
After these, EP-02/03 (intake+parsing), then EP-04..09 vertical slice, then EP-10..13 per Appendix F schedule.

## 10. Secrets and safety notes for implementers

- Never commit `.env`, keys, or real CyberSkill identifiers; seller identity is the SAMPLE block in `config/seller.py` (Appendix A.6).
- Cassettes must be scrubbed: recorder filter strips `Authorization` headers and any real key material before write.
- The public repo goes live from day 1 (judges may look early); nothing sensitive ever lands in history — no force-push cleanups planned.

*End of QM-REPO-001 v1.0.0.*
