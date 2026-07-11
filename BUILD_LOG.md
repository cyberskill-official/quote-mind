# QuoteMind build log

Running record of what shipped per PR, deviations with justification, and open questions.
Spec of record: QM-SPEC-001 v1.0.0 (`docs/spec/`). Repository blueprint: QM-REPO-001.

## 2026-07-11 - PR-1 (branch feat/FR-001-scaffold)

FRs: FR-001 (repo scaffold), FR-002 (config), FR-008 (structured logging), FR-009
(health and version), FR-010 (auth middleware). Bootstrap order per QM-REPO-001 section 9.

Delivered:
- Root: LICENSE (Apache-2.0), README.md, pyproject.toml, Makefile, .env.example, merged
  .gitignore (kept the existing block, appended python/node/.env patterns).
- CI: .github/workflows/ci.yml with lint (ruff + import-linter), type (mypy), unit (pytest).
- Package skeleton: the full Appendix D tree as empty packages, with real content for
  config/settings.py, config/models.py, obs/log.py, api/app.py, api/auth.py.
- Tests: settings fail-fast, health shape, auth 401 and 200, JSON logging. Offline, zero
  paid-API calls.
- docs/verification-log.md (resolved pins), docs/traceability.csv (PR-1 rows).
- Spec pack arranged into docs/spec/ (the .zip is removed).

Decisions (logged per the working method):
1. FR-009 and FR-010 name FR-003 (s.yaml) as a dependency, but QM-REPO-001 section 9 places
   health and auth in PR-1 and the FC descriptor in PR-5. Both are implemented at the app
   layer and proven by the test client; the FC handler shim and s.yaml land in PR-5. No frozen
   contract is touched.
2. Dependency layout: light core in [project].dependencies; the full runtime stack (section
   4.4) is pinned under domain extras (agents, memory, cloud, parse, pdf, obs), unioned as
   `all`. `make setup` installs core + dev so the scaffold boots and tests stay green before
   native PDF and agent libraries exist; `make setup-all` installs everything. Every section
   4.4 version stays pinned.
3. Structured logging lives at obs/log.py. The frozen tree names obs/ but not this file, so it
   is an addition, not a rename.
4. CI ships only the jobs PR-1 can pass. smoke-eval (FR-123), golden-pdf (FR-124), and
   diagrams (SUB-03) are TODO in their PRs, and CI installs `.[all,dev]` once a heavy import
   lands (PR-4 memory or EP-02 agents).
5. /health returns both `version` and `git_sha` so it satisfies API-11 ({status, version,
   models}) and FR-009 (status, git SHA, model constants) at the same time.

Findings:
- agentscope 1.0.9 requires Python >=3.11, so the spec's optional FC python3.10 fallback
  (section 4.4, open item 3) is not viable while agentscope is a dependency. The chosen
  3.12-only target avoids it. Recorded in docs/verification-log.md.

Verification (2026-07-11, Python 3.10 sandbox, light toolchain, no paid-API calls):
- ruff check: all checks passed.
- mypy -p quotemind: success, no issues in 24 source files.
- import-linter: 4 contracts kept, 0 broken.
- pytest: 8 passed.
- Note: mypy's SQLite cache cannot live on the sandbox mount (disk I/O error), so the sandbox
  run used --cache-dir=/tmp; the Makefile keeps the default .mypy_cache, which works on the
  Mac and in CI. The authoritative `make setup && make test` on Python 3.12 runs in CI.

Open questions:
- Whether to wire the CyberOS gate runner (.cyberos/gates.env) to the Makefile is pending an
  operator decision; explanation provided in chat.

## 2026-07-11 - PR-2 (branch feat/PR-2-models)

Scope: the models package (DM-01..14) and the quote state machine, per QM-REPO-001 section 9.
Frozen field names and the Status enum/transition table match parent section 7, 5.2, and 12.

Delivered:
- src/quotemind/models/: common.py (BilingualText DM-04, shared enums, new_ulid), quote_record.py
  (Status + LEGAL_TRANSITIONS + QuoteRecord DM-01 + transition guard), intake.py (DM-02),
  extraction.py (DM-03), catalog.py (DM-05/06), memory.py (DM-07/08), matching.py (DM-09),
  quote.py (DM-10), critic.py (DM-11), audit.py (DM-12 + hash chain), eval.py (DM-13),
  trace.py (DM-14), and __init__.py re-exporting the public surface.
- Tests: exhaustive legal and illegal Status transitions (FR-080 AC, all pairs), DM schema
  round-trips (EV-02), and the audit hash chain build/verify/tamper.

Decisions (logged):
1. Status and LEGAL_TRANSITIONS are verbatim from parent 5.2 (frozen 12.9). Terminal states
   derive from the table (statuses with no outgoing edges).
2. Optionality: DM field names match section 7 exactly; fields populated later in the lifecycle
   (source_uri, totals_json, sha256_payload, embeddings, source_span, and so on) are Optional
   with None defaults. This sets nullability, not the frozen field set.
3. Audit hash chain: sha256 over a canonical JSON body (sorted keys, compact separators,
   ensure_ascii off) excluding the hash field; genesis prev_hash is 64 zeros. The spec fixes
   "sha256 chain" but not the encoding, so this is the chosen, documented canonicalization.
4. A few categorical values not fixed by section 7 (Channel, DocType, Urgency, SopTopic,
   customer match method) use sensible enum values; revisit if a later FR pins them.

Verification (2026-07-11, Python 3.10 sandbox): ruff clean, mypy clean (36 files), import-linter
4 of 4 kept, pytest 18 passed. UP042 (enum.StrEnum) is ignored alongside UP017 so the code runs
on the 3.10 gate; (str, Enum) is valid on 3.12.

## 2026-07-11 - PR-3 (branch feat/PR-3-pricing, stacked on feat/PR-2-models)

Scope: the deterministic pricing engine (FR-050..055), per QM-REPO-001 section 9. Pure Decimal
math; pricing imports only models and never the network, agents, or an LLM (D-03).

Delivered:
- pricing/engine.py: unit_price (FR-051 tiers + dealer fallback), line_total, vat_amount,
  quote_totals (per-rate VAT breakdown), margin + blended_margin (FR-053), to_usd (FR-054),
  format_vnd / format_usd (FR-055). All quantized to whole đồng.
- pricing/vat.py: allowed rates {0,5,8,10}, the 2025-07-01..2026-12-31 reduction window, telecom
  forced to 10%, and vat_policy_note (Appendix B footer).
- pricing/words_vi.py: Vietnamese amount-in-words converter.
- Tests: tiered pricing + fallback, totals grouping, a hypothesis property test (totals equal the
  sum of parts, VND integers) for FR-050, VAT rules with the date switch, and 28 amount-in-words
  cases plus the negative guard. Pricing has 100% branch coverage, now enforced in CI.

Decisions and flags:
1. amount_in_words_vi follows the single worked example in the spec (1234000 ->
   "Một triệu hai trăm ba mươi bốn nghìn đồng"): 4 -> "bốn", tens+1 -> "mốt", tens+5 -> "lăm",
   a missing tens digit -> "linh", zero hundreds in a non-leading group -> "không trăm". The
   FR-055 30-case table is not in the spec pack, so these cases are my own derivation. If the
   official table prefers "tư" or "lẻ" in some positions, that is a localized wording tweak, not a
   logic change. FLAGGED for Stephen's review as the native-language authority.
2. unit_price takes an optional project_discount_pct (default 3) so the frozen two-arg call still
   works; the missing-dealer-price flag is emitted later at line assembly, not by the pure price
   function.
3. The CI unit job now enforces pricing 100% branch coverage (NFR-010, QM-REPO-001 section 8).

Verification (Python 3.10 sandbox): ruff clean, mypy clean (39 files), import-linter 4/4 kept
(the pricing-pure contract held), pytest 63 passed, pricing branch coverage 100%.

## 2026-07-11 - PR-4 (branch feat/PR-4-memory, stacked on feat/PR-3-pricing)

Scope (offline part): the memory adapter over tablestore-for-agent-memory and the provisioning
script, per QM-REPO-001 section 9. Appendix E.1 (SDK surface) was verified against the installed
1.1.3 wheel; E.2/E.3 (live model + AgentScope smoke) need credentials and are deferred.

Delivered:
- memory/store.py: MemoryFacade translating DM models to and from the SDK Document/Session/Message.
  Catalog, customers, episodic (per-customer tenant), and SOP go to KnowledgeStore as payload_json
  plus filterable scalars plus embedding; sessions and messages go to MemoryStore. Frozen tenant
  names catalog/customers/episodic:{id}/sop (parent 12.5). from_settings builds the OTSClient and
  stores (vector dim 1024, multi-tenant); init_tables provisions them.
- deploy/provision.py: FR-004 idempotent OSS bucket and Tablestore table/index creation, using the
  oss2 ProviderAuthV4 + StaticCredentialsProvider API verified against oss2 2.19.1. Written, not run.
- Tests: mocked-store unit tests exercise the DM<->SDK translation (Document build, payload round
  trip, hit mapping, session/message shaping, init_tables). No live calls.
- CI and make setup now install the .[memory] extra (first heavy dependency to land).

Decisions and findings:
1. Appendix E.1 confirmed the SDK import paths differ from the spec's assumption; the adapter
   absorbs the drift (Risk #2). Real paths and signatures are in docs/verification-log.md.
2. SDK metadata holds only scalar values, so each aggregate is persisted as a payload_json string
   plus filterable scalars and reconstructed on read.
3. run_gc (FR-046 forgetting) and episodic importance-decay retrieval (FR-044/045) are EP-04 proper
   and land in a later PR; PR-4 is the adapter plus provisioning per the blueprint.

Verification (Python 3.10 sandbox): ruff clean, mypy clean (40 files), import-linter 4/4 kept,
pytest 70 passed. UP047 (PEP 695 generics) joins the ignore list for 3.10 compatibility.

DECISION NEEDED (live cloud): the memory adapter's live behavior, running deploy/provision.py, and
the Appendix E.2/E.3 model probes all require Alibaba Cloud plus DashScope credentials and consent
to spend on paid Qwen calls. Deferred until the operator provides them.

## 2026-07-11 - PR-4 live verification

Model plane verified end to end on real DashScope (Singapore): Appendix E.2 (all frozen model
constants available; text-embedding-v4 dim 1024) and E.3 (AgentScope 1.0.9 structured output,
metadata={'ok': True}) both PASS. Recorded in docs/verification-log.md, including the finding that
AgentScope's DashScopeChatModel needs base_http_api_url=https://dashscope-intl.aliyuncs.com/api/v1
for Singapore (distinct from the openai compatible-mode base).

provision.py fixed to pass region to oss2 (V4 signing requires an explicit region).

BLOCKED on operator account setup (not code): OSS returns 403 UserDisable (activate OSS / billing /
verification) and Tablestore returns "instance not found" (TABLESTORE_INSTANCE / _ENDPOINT must match
an existing ap-southeast-1 instance). Provisioning and live memory resume once those are resolved.

## 2026-07-11 - PR-4 Tablestore live verification

The earlier OTS "instance not found" was a config typo: .env had the example default
TABLESTORE_INSTANCE=quotemind vs the real instance quotemind-demo. Fixed on the Mac. Against the live
ap-southeast-1 instance, init_tables() provisioned the tables and a put_customer/get_customer
round-trip through MemoryFacade returned an equal model - the memory adapter is live-verified. OSS is
still 403 UserDisable pending account activation, so the full provision.py run (OSS buckets first)
completes once OSS is on.

## 2026-07-11 - EP-04 forgetting + budget (branch feat/EP-04-forgetting, stacked on feat/PR-4-memory)

Scope (offline, out of strict PR-1..5 order): the pure memory-decay and budget logic, built while
OSS activation is pending so no time is lost.

Delivered:
- memory/episodic.py: initial_importance (FR-046), recency_decay 0.5^(age/90), effective_score
  (similarity x decay x importance), effective_ceiling, should_prune, rank_by_effective_score.
- memory/budget.py: estimate_tokens (~4 chars/token heuristic) and budget_trim keeping the highest
  effective-score items within a token cap, flagging truncation (FR-049; 2500 context / 1200
  episodic budgets).
- memory/gc.py: run_gc prunes episodic memories whose effective ceiling is below 0.05 and counts
  customers past the compaction limit; `python -m quotemind.memory.gc` entry. The live scan/delete
  path uses the facade; compaction (an LLM profile summary) is flagged for the agent path.
- Tests: importance/decay/score/ceiling/ranking (including the FR-046 AC that a fresh memory
  outranks a 200-day-old one of equal similarity), budget trim, and a mocked-facade gc prune.

Fixes and notes:
- The FR-002 missing-variable test now runs in an isolated cwd so a real .env at the repo root no
  longer supplies the value (pydantic-settings reads .env; os.environ still wins for the other
  tests). This surfaced once the live-verification .env was created.
- Faithfulness note: with the FR-046 importance floor of 0.7 for episodic memories, the prune
  ceiling (<0.05) is only reached past ~340 days, so the gc demo relies on the seed setting low
  importances or old ages. The gc functions implement the formula exactly.

Verification (Python 3.10 sandbox): ruff clean, mypy clean (43 files), import-linter 4/4 kept,
pytest 80 passed.

## 2026-07-11 - EP-03 Excel parser + extraction gate (branch feat/FR-033-excel-parser)

Scope (offline, out of strict PR-1..5 order): FR-033 deterministic .xlsx extraction and the FR-034
validation gate - both pure and fully unit-testable, so they land while OSS activation is pending.

Delivered:
- parsing/excel.py (FR-033): openpyxl-only parse_excel(bytes) -> RFQExtraction. Fuzzy header-row
  detection over the first 15 rows against the Vietnamese and English column names in the spec
  ({stt, ten hang, mo ta, description, qty, so luong, dvt, unit}); a row is the header once it
  carries both a description and a quantity column, so title rows above the table are skipped.
  Quantities are read straight from the cells (no LLM touches numeric cells, per the FR): ints and
  integral floats normalize to a clean Decimal, text digits parse, junk -> None. Fully blank rows
  are dropped; confidence is 1.0 (deterministic). HeaderNotFoundError when no header row is found.
- parsing/validate.py (FR-034): validation_reasons / needs_clarification returning the reason codes
  NO_LINE_ITEMS, MISSING_DESCRIPTION, MISSING_QUANTITY. The pipeline maps a non-empty result to
  status needs_clarification (it does not proceed to matching). Empty-body AC -> NO_LINE_ITEMS.
- parsing/__init__.py re-exports the deterministic surface only; the text/vision/PDF parsers
  (FR-030/031/032) call models and land with the agent path.
- Tests (6): Vietnamese headers under a title row, quantities matching labels exactly incl. an
  integral-float row (FR-033 AC), English headers with a blank row skipped, missing-header raise,
  and the FR-034 gate (empty -> NO_LINE_ITEMS, missing-quantity flagged, complete line passes).

Decisions / notes (logged, not frozen-registry items):
- Per-line language (FR-035) is a deterministic diacritic check: a line carrying Vietnamese
  diacritics reads VI, otherwise EN. A diacritic-free brand/model line (e.g. "Laptop Dell Latitude
  5450") therefore reads EN; the drafter agent refines language later. This keeps the parser
  LLM-free while still populating language_per_line.
- LLM normalization of genuinely ambiguous headers (the second half of FR-033) is deferred to the
  agent path; deterministic fuzzy matching covers the labeled fixtures.
- CI and Makefile now install the parse extra (openpyxl) alongside memory so import-linter builds
  the full graph and the tests run. Makefile `gc` target now invokes the real FR-046 module.

Verification (Python 3.10 sandbox): ruff clean, mypy clean (45 files), import-linter 4/4 kept,
pytest 86 passed.
