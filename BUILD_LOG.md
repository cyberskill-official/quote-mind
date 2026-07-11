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

## 2026-07-11 - EP-07 critic core (branch feat/FR-070-critic)

Scope (offline, out of strict PR-1..5 order): the deterministic, code-enforced half of the critic -
FR-070 independent recomputation, the computable subset of FR-071 policy flags, and FR-072 bilingual
number + mojibake checks. Pure functions over an assembled Quote (DM-10) -> CriticReport (DM-11); no
network, no LLM. The LLM critic narrative (FR-073) layers on top in AGT-07.

Delivered (src/quotemind/quote/critic.py):
- FR-070 recompute_diffs(quote): recomputes each line total and VAT, then subtotal / per-rate VAT
  breakdown / grand total, using the SAME pricing-engine functions (line_total, vat_amount,
  quote_totals) so the engine stays the single source of numeric truth (D-03, hard rule 2). Any
  claimed value that differs by > 0 VND becomes a RecomputeDiff (field, expected, actual, line_idx);
  run_critic then adds the blocking RECOMPUTE_MISMATCH. Meets the FR-070 AC (a tampered line total
  fails with the offending line id).
- FR-071 policy_flags(quote, ...): MARGIN_BELOW_FLOOR (blocking; blended or any per-line margin
  below floor, default 5 from settings) and MISSING_MANDATORY_FIELDS (blocking); UNKNOWN_CUSTOMER,
  NEEDS_CONFIRMATION (any substituted/no-match line), and VALIDITY_OUT_OF_BOUNDS (non-blocking).
- FR-072 bilingual_number_mismatches + mojibake_fields: vi/en fields must carry the same numeric
  tokens (regex/numeric diff after stripping thousands separators, never the LLM); mojibake detected
  by U+FFFD, a "â€" artifact, or a Latin-1 high letter followed by a U+0080-U+00BF byte - none of
  which occur in correct NFC Vietnamese. Both raise blocking flags.
- run_critic(...) -> CriticReport: passed only when nothing blocks; carries a deterministic bilingual
  summary note (the rich narrative is FR-073, the agent's job).
- quote/__init__.py exports the critic surface.
- Tests (10): clean pass; tampered line total (FR-070 AC), subtotal+total, and VAT breakdown; margin
  floor; the three non-blocking flags together (which do not fail the quote); bilingual number
  mismatch; mojibake; missing mandatory field.

Decisions / notes (logged, not frozen-registry items):
- FR-071 VAT_EXCLUDED_CATEGORY mismatch and the SOP validity bounds need data the Quote does not
  carry (line category; SOP min/max). Category enforcement stays in pricing (FR-052, where category
  exists); the validity check runs only when the agent passes SOP bounds. Logged as a deliberate
  subset; the rest lands with the agent path.
- Mojibake and bilingual-number disagreements are treated as BLOCKING: corrupted governing
  Vietnamese or numbers that disagree across languages are integrity failures that must not ship.
  FR-072 does not label blocking-ness, so this is a documented choice.

Verification (Python 3.10 sandbox): ruff clean, mypy clean (46 files), import-linter 4/4 kept,
pytest 96 passed.

## 2026-07-11 - EP-06/EP-09 numbering + bilingual HTML render (branch feat/FR-090-render)

Scope (offline): FR-062 quote numbering (pure format) and the FR-090 render's deterministic half -
the bilingual HTML per the normative Appendix C layout. Jinja2 is a core dependency, so the HTML
render needs no extra; the WeasyPrint PDF byte-generation is a lazy live path behind the pdf extra.

Delivered:
- quote/numbering.py (FR-062): format_quote_number / parse_quote_number / is_valid_quote_number for
  the frozen QM-YYYY-NNNN format (seq zero-padded to 4, widening past 9999). The per-year atomic
  counter (qm_counters) stays a runtime concern; only the format lives here, tested offline.
- quote/render/quote.html.j2 (FR-090): A4 bilingual layout following Appendix C section by section -
  Umber #45210E header band with an Ochre #F4BA17 rule, seller/customer blocks, meta row, the
  STT|Mô tả/Description|ĐVT/Unit|SL/Qty|Đơn giá/Unit price|Thành tiền/Amount table with zebra rows
  and indented Ochre-bordered note rows, right-aligned totals with a per-rate "Thuế GTGT n% / VAT n%"
  line and the Bằng chữ/In words line, a 2x2 terms grid, the bank block, the signature row, and a
  running footer carrying the VAT policy note, FX note, and short quote-id hash.
- quote/render/__init__.py: render_html(quote, vat_policy_note=..., ...) builds the context (every
  money value formatted by the pricing engine - the template never computes) and renders with
  autoescape on; render_pdf lazily imports WeasyPrint and raises a clear error when the pdf extra is
  absent. build_context is exposed for testing.
- quote/__init__.py also exports the numbering helpers.
- pyproject: package-data ships the .j2 template and fonts/ inside the wheel.
- Tests (7): numbering format/parse/validate incl. >9999 widening and invalid inputs; HTML render
  is bilingual and byte-exact on Vietnamese diacritics (BÁO GIÁ, Mô tả, Đơn giá, Bằng chữ, the
  bằng-chữ total), carries dot-thousands totals and both VAT-rate lines and the USD reference, shows
  the bank block (ACB / account / ASCBVNVX), the brand palette, and autoescapes an "R&D" ampersand.

Decisions / notes (logged):
- Be Vietnam Pro is referenced via @font-face url() to fonts/*.ttf; the TTFs are not yet bundled
  (only fonts/.gitkeep), so the live PDF must add them for correct diacritic rendering. The HTML
  render and its tests do not need the fonts.
- The seller identity and bank block are data-driven from quote.seller_block (with a nested "bank"
  dict), not hardcoded, so the template stays free of the frozen registry.

Verification (Python 3.10 sandbox): ruff clean, mypy clean (47 files), import-linter 4/4 kept,
pytest 103 passed.

## 2026-07-11 - EP-04 matcher fusion + customer resolution (branch feat/FR-042-matcher)

The deterministic, code-enforced half of catalog matching (FR-042) and customer resolution (FR-043),
in the tools layer where the agents will call them. No model calls; the LLM select is injected.

Delivered:
- tools/matching.py (FR-042): reciprocal_rank_fusion / fuse_candidates over the vector and full-text
  SKU rankings (RRF, k=60, deterministic SKU tie-break); build_match_result bands a selection into a
  MatchResult (DM-09) - MATCHED, or NEEDS_CONFIRMATION when confidence < 0.75 or specs conflict (with
  up to 3 alternatives excluding the chosen SKU and a bilingual reason), or NO_MATCH when nothing was
  selected (near-misses surfaced as alternatives). top_candidate gives a no-LLM default selection.
- tools/customer.py (FR-043): resolve_customer picks from candidate profiles by email domain, then
  fuzzy name (difflib ratio over accent-folded names, threshold 0.8), then a free-text hint; falls
  back to tier end_customer with unknown_customer=true. CustomerResolution carries profile/tier/flag.
- tools/__init__.py exports both.
- Tests (11): RRF ranking + scoring + tie-break; the four banding outcomes incl. alternative capping
  and spec-conflict override; customer resolution by domain / fuzzy accent-insensitive name / hint,
  domain-beats-name precedence, and the unresolved end_customer fallback.

These connect the live-verified catalog memory to assembly: the matcher yields the SKU and tier that
feed AssemblyLine, and unknown_customer feeds the critic's non-blocking flag.

Verification (Python 3.10 sandbox): ruff clean, mypy clean (48 files), import-linter 4/4 kept,
pytest 114 passed.
## 2026-07-11 - EP-06 quote assembly (branch feat/FR-060-assemble)

FR-060, the keystone that turns matched, priced lines into a Quote (DM-10) and ties the whole
deterministic chain together: pricing -> assembly -> critic -> render.

Delivered (src/quotemind/quote/assemble.py):
- AssemblyLine: one resolved RFQ line (CatalogProduct + qty + tier + line discount + optional NL
  overrides for description/unit/note + source). Description/unit default to the catalog values, so
  assembly is usable without the drafter and the drafter can override later.
- assemble_quote(...): for each line applies unit_price (FR-051 tiered), vat_rate_for (FR-052,
  telecom forced to 10%), line_total and vat_amount, then quote_totals for subtotal / per-rate VAT /
  grand total, amount_in_words_vi for the bang chu, to_usd for the optional USD reference, and
  margin/blended_margin for MarginInfo. Every number is engine-produced; the LLM only supplies the
  NL fields, which arrive as inputs. Sets quote flags VAT_EXCLUDED_CATEGORY (any telecom line) and
  LEAD_TIME (any out-of-stock line).
- Exported from quote/__init__.py.
- Tests (3): a two-line dealer+project quote whose numbers are checked against the engine, then the
  end-to-end proof - run_critic returns zero recompute diffs and passed=True (assembly and the
  critic agree by construction), and render_html shows the grand total and quote number; the
  VAT_EXCLUDED_CATEGORY/LEAD_TIME flags; and NL fields defaulting to the catalog.

Verification (Python 3.10 sandbox): ruff clean, mypy clean (47 files), import-linter 4/4 kept,
pytest 106 passed.
## 2026-07-11 - PR-4 live close + memory search metadata fix (branch fix/memory-search-metadata)

OSS was activated and the three offline PRs (EP-03, EP-07, EP-06/09) merged to main. Resumed with
the live provision + catalog round-trip that had been blocked.

Live verification (Mac .venv against real ap-southeast-1 cloud):
- deploy/provision.py: created quotemind-inbox and quotemind-artifacts (both private); Tablestore
  tables/indexes initialized at vector dim 1024; exit 0. Re-run is idempotent (FR-004 AC).
- Catalog round-trip: embedded 3 products with text-embedding-v4 (dim 1024), put_catalog, then
  get_catalog (equal round-trip) and search_catalog_vector - top hit DELL-LAT-5450 @ 0.85 for a
  "laptop Dell doanh nghiep i5 16GB" query, correctly ranked ahead of the monitor and switch, with
  byte-exact Vietnamese reconstructed. full_text_search returned the two Dell items.

Bug found and fixed (store.py): the SDK's vector_search / full_text_search return DocumentHit
documents with metadata = {} unless meta_data_to_get is passed, so _parse could not find
payload_json and _hits dropped every result (search returned 0 while get_document worked). Fixed all
four search methods (search_catalog_vector, search_catalog_text, search_episodic, search_sop) to
pass meta_data_to_get=[payload_json]. This is the value of the live round-trip - a real
result-mapping bug the mocked unit test (which returns a canned Response with metadata) could not
catch. No unit test asserts call kwargs, so the fix is transparent to the suite.

Verification (Python 3.10 sandbox, rebuilt after session reset): ruff clean, mypy clean (47 files),
import-linter 4/4 kept, pytest 103 passed. Live: catalog vector + text search now return
reconstructed models.

## 2026-07-11 - Agent layer: the pipeline runs end to end, live (branch feat/agent-layer)

Single batch branch, as requested. The model now appears at exactly two points on the quote path -
extraction and catalog selection - and nothing else about the money changed: every number is still
produced by the deterministic engine and independently re-checked by the critic.

Delivered:
- prompts/: normative system prompts as versioned constants. Each states the rules the code also
  enforces (never do arithmetic, never invent a SKU, preserve diacritics byte-exact).
- agents/model.py: AgentScope factory. Model names come from the frozen registry; the native
  DashScope base (/api/v1) that AgentScope needs is derived from the OpenAI-compatible base already
  in .env, so there is no second endpoint env var to drift.
- memory/embedding.py (FR-041): embed_texts at the frozen model + dimension (text-embedding-v4,
  1024), batched at 10 per call, input order restored from the response index.
- agents/parser.py (FR-030): text RFQ -> RFQExtraction via structured output.
- agents/matcher.py (FR-042 select): the LLM picks one SKU from the fused candidate list, and the
  code then *enforces* the whitelist - a SKU the model invents is discarded, never trusted.
- memory/store.py: added search_customers_text (FR-043 candidates) and made catalog_text public so
  seeding embeds exactly the text the store indexes; put_customer now indexes name + domains +
  emails so a buyer can be found by any of them.
- orchestrator.py (FR-130): parse -> FR-034 gate -> resolve customer -> per line (embed, vector +
  full-text search, RRF fuse, LLM select, band) -> assemble -> critic -> render.
- deploy/seed.py (FR-011): 8 demo catalog products + 2 customers, embedded and written.
- Tests (+11): base-URL derivation, the SKU-whitelist guardrail (a hallucinated SKU is rejected),
  embedding batching/order/dimension, and the whole orchestrator end to end with the model AND the
  cloud mocked - plus the FR-034 clarification path and the no-match path.

Live end-to-end run (real DashScope + real ap-southeast-1, 34s):
  Vietnamese RFQ email -> qwen-plus extracted 3 lines with exact quantities and intact diacritics ->
  customer resolved from the email domain to "Công ty TNHH Thành Công", tier dealer ->
  all 3 lines matched (DELL-LAT-5450, DELL-P2723DE, MS-M365-BP) -> priced at dealer prices ->
  subtotal 291,000,000, total 314,280,000 VND, bang chu "Ba trăm mười bốn triệu hai trăm tám mươi
  nghìn đồng" -> critic passed with 0 recompute diffs and no blocking flags -> bilingual HTML.
  Rendered output committed at docs/sample-quote.html.

Notes / deferred:
- AgentScope prints agent turns to stdout; that noise should be silenced before the serverless
  deploy (FR-008 structured logging owns the log surface).
- Terms and quote notes still use documented defaults; SOP memory (FR-048) and the bilingual drafter
  (FR-061) will replace them. The quote is already bilingual because catalog names are BilingualText.
- Vision/PDF parsers (FR-031/032), episodic memory (FR-044/045), and the planner handoff (FR-131)
  remain.

Also added docs/roadmap.html - a self-contained view of all 13 epics / 82 FRs with live status.

Verification: ruff clean, mypy clean (54 files), import-linter 4/4 kept, pytest 128 passed,
pricing branch coverage 100%.

## 2026-07-11 - Intake, persistence and the human gate (branch feat/intake-hitl)

Single batch branch. The pipeline now has durable state: an RFQ posted to the API is persisted,
numbered, run to the approval gate, and can be approved by a completely different process.

Delivered:
- memory/quotes.py: QuoteStore over the three frozen tables (qm_quotes, qm_audit, qm_counters).
  FR-062 numbering now uses a real atomic per-year counter - the Python Tablestore SDK cannot read
  back an incremented value (ReturnType has no RT_AFTER_MODIFY), so it is a bounded compare-and-set
  loop, which is still atomic: a losing writer retries against the new value. Idempotency (FR-024)
  is a pointer row inside qm_quotes rather than a fourth table, and the queue is a bounded scan;
  both are documented demo-scale choices that keep the frozen table list intact. put_quote uses
  update_row (not put_row) so a status change cannot wipe the stored quote/critic/html.
- intake.py (FR-022/024/025): deterministic classification - doc type from the filename, language
  from Vietnamese diacritics (vi/en/mixed), urgency from keywords. No model needed, and code cannot
  hallucinate a doc type. Oversize (>15 MB) and unsupported types are rejected before anything else.
- service.py: QuoteService, the only writer of quote state. Every transition goes through the frozen
  state machine (FR-080) and writes a hash-chained audit event (FR-094) before returning. submit
  (idempotent), process (persists each stage), review (FR-082), approve/reject (FR-083), revise
  (FR-084, capped at 3 revisions), stale_pending (FR-085).
- api/app.py: API-01..08. POST /api/rfq returns 202 and runs the pipeline in the background (FR-020).
  FastAPI cannot mix a JSON body model with File/Form on one route, so the content type is dispatched
  by hand to satisfy FR-020's "multipart OR JSON" requirement.
- models/common.py: added Language.MIXED and DocType.IMAGE, which FR-022 requires and the DM enums
  had omitted.

Spec correction worth noting: an earlier reading sent every quote with a blocking flag to
critic_failed. That is wrong. FR-070 (a recompute mismatch) is a hard failure - the arithmetic did
not survive an independent check. FR-071 policy flags (e.g. MARGIN_BELOW_FLOOR) are different: the
quote still reaches the human, who may waive them explicitly at the gate, and the waiver is audited
(FR-083). The code now does exactly that.

Live run (real Tablestore):
  tables created -> submit -> QM-2026-0001 from the atomic counter -> re-post returns the same id
  (FR-024) -> pipeline to pending_approval, total 248,400,000 VND -> a BRAND NEW QuoteService (new
  client, new objects) loads the quote from Tablestore, verifies the 7-event hash chain, and approves
  it. That is FR-081 durable pause and resume, proven rather than asserted.

Tests: +18 (146 total). Intake classification and guards; the service lifecycle against real
assembled/critiqued quotes including the blocking-flag waiver path and an illegal transition; the API
surface end to end with a fake store (202, idempotent re-post, 409 with the flag list, 404, 422, 401).

Deferred: OSS drop channel (FR-021), FR-085's log event and dashboard badge, and dispatch (PDF,
presigned URL, email) which is the next batch.

Verification: ruff clean, mypy clean (57 files), import-linter 4/4 kept, pytest 146 passed.

## 2026-07-11 - Dispatch: PDF, OSS artifact, email, OSS drop (branch feat/dispatch)

The quote now leaves the building. On approval it is rendered to PDF, stored privately in OSS,
fetched back over a presigned URL, and emailed - and an RFQ dropped into the inbox bucket runs the
whole path by itself.

Delivered:
- cloud/oss.py: ArtifactStore over the two buckets. Artifacts land at the frozen keys
  quotes/{quote_number}.pdf and outbox/{quote_number}.eml; presigned GETs are V4-signed with
  slash_safe=True and a 600s TTL (FR-091). The inbox side lists and reads rfq/ objects (FR-021).
- quote/render/render_pdf (FR-090): WeasyPrint over the existing Appendix C template. Verified the
  way the AC asks - the PDF text is extracted back out with pypdfium2 and every Vietnamese string
  (BÁO GIÁ, Mô tả hàng hóa, Bằng chữ, the bang chu total, Thanh toán trong 30 ngày) still carries its
  diacritics byte-exact. The brand TTFs are not committed (binary assets); WeasyPrint falls back to
  the system sans and diacritics still render - see quote/render/fonts/README.md.
- dispatch.py (FR-092/093): one bilingual MIME message, two transports. Vietnamese leads (it is the
  governing language), English follows, the presigned link is in both parts, and the PDF is attached
  only when <= 3 MB. `smtp` goes through DirectMail over SSL 465; `stub` writes the identical message
  to oss://quotemind-artifacts/outbox/ and is audited as sent_stub, so demos are deterministic.
- service.dispatch: approved -> dispatching -> sent, with every step audited and any failure landing
  durably in failed_dispatch. pdf_url renders on demand if the object is missing.
- api: API-09 GET /api/quotes/{id}/pdf returns 302 to a fresh presigned URL; approval now triggers
  dispatch in the background (FR-083).
- deploy/ingest.py (FR-021): one code path, two entry points - an FC OSS trigger handler and a
  `python deploy/ingest.py` scan. The dropped key becomes source_uri and channel is oss_drop, so a
  file-borne RFQ is indistinguishable downstream from an API one.

Bug the live run caught: .txt and .eml were not in the supported-extension map, so the OSS drop
rejected its own text file as an unsupported type. Fixed - a dropped text file is an email_text
document. This is exactly the class of bug the unit tests could not see, because they never named a
real file.

Live (real cloud): QM-2026-0002 approved -> PDF rendered -> stored at quotes/QM-2026-0002.pdf ->
presigned GET returned HTTP 200 with 37,421 real PDF bytes -> stub email written to
outbox/QM-2026-0002.eml with the PDF attached -> audit chain still verifies. Separately, a .txt RFQ
dropped into oss://quotemind-inbox/rfq/ was ingested by deploy/ingest.py and ran to
pending_approval as QM-2026-0003. The rendered PDF is committed at docs/sample-quote.pdf.

Deferred: the DirectMail smtp path is implemented but untested against a live verified sender (the
demo default is stub); brand TTFs; FR-085's log event and badge.

Verification: ruff clean, mypy clean (59 files), import-linter 4/4 kept, pytest 155 passed, pricing
branch coverage 100%. CI now installs pango/cairo before the pdf extra so WeasyPrint runs there too.

## Batch: observability + review dashboard (EP-11, EP-10) - feat/observability-dashboard

FR-110/111/112/113 + FR-100/101/102/103/105/106. The demo's money shot: the reviewer can see not
just the quote, but every step that produced it, priced.

- obs/otel.py (FR-110): GenAI semantic conventions - `chat qwen3-max`, `execute_tool vector_search`,
  `gen_ai.provider.name` / `gen_ai.operation.name` / `gen_ai.request.model` / `gen_ai.usage.*`. The
  OTel SDK is optional: with no exporter installed the span is a no-op, so nothing on the quote path
  depends on a collector being up. The name/attribute builders are pure, so the convention itself is
  unit-tested rather than asserted in a comment.
- obs/trace.py (FR-111): every model call, tool call and memory read on a quote's path becomes an
  ordered TraceStep (DM-14) with tokens, cost and duration. Written to
  oss://quotemind-artifacts/traces/{quote_id}.json and served by API-05. Prompt and response bodies
  are excluded by default - an RFQ carries a real customer's details and a trace is not the place to
  leak them; TRACE_CONTENT=1 turns them on for debugging.
- obs/cost.py + config/model_prices.yaml (FR-112): token counts times a checked-in price table, in
  Decimal. Two decisions worth stating plainly. First, the token counts are the provider's own,
  read off ChatResponse.usage via a DashScopeChatModel subclass - not estimated, because a
  fabricated cost number in an eval report is worse than none. Second, the prices are Alibaba's
  published *list* prices for the International (Singapore) endpoint, dated in the file; batch
  inference, context caching and the free quota all discount them, so what QuoteMind reports is an
  honest upper bound, not a bill.
- obs/errors.py (FR-113): the taxonomy plus a retry policy with one load-bearing rule - only model
  and tool calls are retried (1s, then 4s). Deterministic steps are never retried, because if
  pricing or the critic recompute failed, the input was wrong and running the arithmetic again just
  produces the same wrong answer more slowly, while hiding the bug.
- service.py: the trace is persisted next to the quote, and a trace write failure can never fail a
  quote - it lands as a `trace.persist_failed` audit event and the quote still reaches the human.
  Observability that can take down the product is worse than no observability.
- web/index.html (FR-100..103, FR-105): one self-contained file, no build step. Queue with status
  filters and 5s polling; detail with the bilingual line table, confidence and flag chips, totals,
  margin and amount-in-words; an action bar whose approve button opens a waiver modal *only* when
  the critic raised a blocking flag (and a 409 from the server if a waiver is skipped); and the
  collapsible reasoning-trace panel showing each step with its tokens, cost and duration. CDS
  Umber/Ochre, light theme.
- deploy/upload_site.py (FR-106): substitutes the API base and token at upload time and publishes
  the page as the only public object in the artifacts bucket. Quotes, traces and outbox messages
  stay private behind presigned URLs. The API gained CORS for exactly this reason - the token, not
  the origin, is the security boundary.

Deferred: FR-104 (realtime push) polls at 5s instead of using SSE/WebSocket - a demo-scale choice,
and honest about it in the roadmap.

Live (real cloud, `python deploy/smoke_trace.py`): a two-line Vietnamese RFQ ran to
pending_approval producing a 9-step trace - parse (qwen-plus, 1262->428 tok), then per line: embed
(text-embedding-v4), vector_search, full_text_search, select (qwen3-max, ~2000 tok in). Totals:
5,345 -> 833 real provider tokens, **$0.008320 per quote**, 22.4s wall. The document was written to
oss://quotemind-artifacts/traces/{quote_id}.json (2,526 bytes) and read back byte-for-byte, and
`contents` was empty - TRACE_CONTENT is off, so no customer prose left the process. That per-quote
cost is now a real number the eval (EP-12) can put against the single-agent baseline.

The dashboard was then driven in a real browser against that live API, not just unit-tested:
QM-2026-0004 rendered its bilingual line table, totals, VN amount-in-words and the full 9-step trace
panel with per-step tokens and dollars. QM-2026-0003 (margin 4.8%, below the 5% floor) showed its
blocking flag, and pressing Approve raised the waiver modal rather than approving silently. The
waiver was submitted with a Vietnamese comment, the quote moved to `dispatching`, dropped out of the
pending queue, and the hash-chained audit recorded it verbatim at seq 8:
`human.approved {"comment": "Duyệt ngoại lệ: khách chiến lược FPT, chấp nhận biên 4.8%",
"waived_flags": ["MARGIN_BELOW_FLOOR"]}` - diacritics intact through the browser, the API, and
Tablestore. Screenshot at docs/dashboard.png.

Verification: ruff clean, mypy clean (63 files), import-linter 4/4 kept, pytest 175 passed, pricing
branch coverage 100%.
