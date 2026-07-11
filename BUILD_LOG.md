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

## Batch: evaluation harness (EP-12) - feat/eval-harness

FR-120/121/122/123/124, plus FR-031 and a real FR-011 catalog. This is the batch that turns the
Track-4 claim from an assertion into a measurement.

### The headline

30 labelled RFQ cases against a 61-SKU catalog, run live on real DashScope + Tablestore + OSS, in
two modes on identical inputs with identical models. 25 runnable; the 5 scanned-PDF cases are
declared and skipped, not quietly dropped from the denominator.

| mode | task success | line F1 | SKU top-1 | price exact | needs human | p50 | $/quote |
|---|---|---|---|---|---|---|---|
| pipeline | **96%** | 0.992 | 100% | **96%** | 8% | 22.9s | $0.0109 |
| baseline | **48%** | 0.992 | 98% | **48%** | **0%** | 21.0s | $0.0134 |

**+48 points of task success. +48 points of price exactness.**

The interesting part is not the gap, it is the *shape* of it. The single agent extracts the line
items almost as well as the pipeline does (F1 0.992 vs 0.992) and picks the right SKU almost as often
(98% vs 100%). It is not a stupid baseline. It fails on exactly one thing: **every single one of its
13 failures is the money.** It gets the arithmetic wrong on 52% of quotes - and its
human-intervention rate is 0%, because with no critic and no gate it never once notices. On the
out-of-catalog case it invented a price for a product that does not exist (123,768,000 vs
42,768,000).

That is the whole argument for the architecture, and it is now a number rather than a slogan: the
model is good at reading and matching, and cannot be trusted with VND arithmetic across multiple
lines at two VAT rates. Taking the arithmetic away from it, and putting a critic behind it, is worth
48 points. The pipeline is also *cheaper* ($0.0109 vs $0.0134), because the baseline has to carry the
whole candidate catalog in one prompt.

Against the spec's goals (section 3.1): G-01 success >= 80% -> 96%. G-02 F1 >= 0.95 -> 0.992.
G-03 SKU >= 0.90 -> 1.00. G-05 p50 <= 90s -> 22.9s. G-06 delta >= +10 pts -> +48. G-07 cost <=
$0.05 -> $0.0109. All met.

### The eval caught two of my own bugs, which is the point of having one

The first run scored 68%, not 96%. Both causes were mine, and neither was visible to any unit test:

1. **Thin service margins in the fixture.** Appendix A.1 mandates 6-18% margins; I had authored 14
   SKUs (mostly services and licences) at 3.5-5.9%, *below* the critic's 5% floor. So the critic
   correctly flagged three perfectly good quotes as MARGIN_BELOW_FLOOR - it was right and my data was
   wrong. The fix was the data, not the floor. A weaker instinct here would have been to relax the
   critic to make the number go up.
2. **Customer resolution on file-borne RFQs.** A spreadsheet carries no sender inside it, and the
   harness was passing `customer_id` as a name hint - but `resolve_customer` matches on *name*, so
   all four xlsx cases silently fell through to END_CUSTOMER list pricing and mispriced by 7-14%. In
   the real world a spreadsheet arrives *attached to an email*, and intake passes that envelope
   through; the eval now supplies the sender exactly as intake does.

Fixing both took the pipeline from 68% to 96%. Neither bug is one the unit suite could have found,
because both are about the fixture and the plumbing agreeing with reality rather than with themselves.

### The one remaining failure, and why it is arguable

adv_002 asks for a "Latitude 5450 with 64GB RAM". No such machine exists - the catalog tops out at
32GB. The recorded run shows the model reaching for a SKU that was not among its candidates, and the
**SKU whitelist refused it**, so no quote was produced and the case went to a human. My label says it
should have matched the closest SKU and raised a spec-conflict flag, so the harness scores it as a
miss. I have left the label alone and reported the miss rather than relabelling to reach 100%,
because the disagreement is real and worth arguing about - and because a system that refuses to
quote a machine that does not exist is not obviously worse than one that substitutes a 32GB laptop
and lets the customer find out on delivery.

### Also in this batch

- **A real seller identity problem, fixed.** `api/app.py` carried CyberSkill's *actual* bank account
  number, SWIFT and beneficiary name in a public repo. Appendix A.6 explicitly forbids this, and it
  is a genuine invoice-fraud exposure: a quote PDF carries payment instructions. All of it is now
  clearly-marked SAMPLE data in `config/seller.py` (which also lets the eval build quotes without
  importing the API layer). Real tenant identity belongs in deploy-time config, never in source.
- **FR-011: the catalog is now 61 SKUs and 8 customers** (Appendix A.1/A.2). The old 8-SKU catalog
  made "top-1 SKU accuracy" meaningless - almost any retrieval would land on the right row. The new
  one is built with deliberately confusable families (Latitude 5450 i5 / 5450 i7 / 5440 / 7450;
  P2422H / P2423D / P2723DE) so the matcher actually has to discriminate.
- **FR-031: digital PDF extraction.** Text is lifted out with pypdfium2 and handed to the normal text
  path. A scanned PDF raises `ScannedPdfError` rather than being parsed into a confidently empty
  quote - it needs vision OCR (FR-032), which is what the 5 skipped cases are waiting on.
- **Orchestrator entry points** for text, spreadsheet and PDF now converge on one shared
  `quote_from_extraction`. A channel with its own pricing path would be a channel that could disagree.
- **FR-123: CI cassettes.** Five cases recorded from a live run's own trace (FR-111 with
  TRACE_CONTENT=1 - so what CI replays is what the models really said) and replayed with no API key,
  no cost and no network. The thresholds are exact, not approximate: given the same recorded model
  output the deterministic half must produce the same quote to the đồng, every time.
- **FR-124: the golden PDF.** Rendered, rasterised and pixel-diffed at 2%. It exercises both VAT
  bands (8% goods + 10% telecom) so a VAT regression shows up as a picture. Caveat stated rather than
  hidden: the golden is font-dependent - recorded on macOS it differs from Linux by ~25% of pixels,
  which is font fallback, not layout - so it is pinned to the CI platform until the Be Vietnam Pro
  TTFs are bundled.

Verification: ruff clean, mypy clean (71 files), import-linter 4/4 kept, pytest 229 passed, pricing
branch coverage 100%.

## Batch: deployment proof and submission artifacts (EP-01, SUB-*) - feat/deploy-proof

FR-003, FR-005, FR-012, and SUB-02..06.

### FR-005: the Alibaba proof, and why it asserts on content

`src/quotemind/cloud/alibaba_proof.py` is the file the hackathon asks for - "a link to a code file
demonstrating use of Alibaba Cloud services and APIs". It is deliberately one module with no
indirection, so a judge can read it top to bottom in two minutes.

Every check asserts on *what came back*, not on the absence of an exception. That distinction is the
whole design: an embedding check that only asserted "no error" would happily accept a vector of the
wrong width into a system whose index is pinned at 1024, and the failure would surface months later
as bad retrieval rather than as a red line today. So it asserts the dimension. Likewise OSS
round-trips a Vietnamese payload and byte-compares it, and Tablestore reads its row back and checks
the diacritics survived.

Live: **8/8 PASS on ap-southeast-1, exit 0.** DashScope chat (`qwen3-max`, 'OK' in 2,023 ms) and
embedding (1024 dims); OSS put -> V4-presigned GET -> HTTP 200 -> byte-match -> delete; Tablestore
create -> put -> get (byte-exact) -> delete.

### FR-012: the cold-start check caught itself being wrong, twice

The model-availability probe is supposed to detect a retired model id and swap in the documented
fallback. Running it live against the real gateway, it did something worse than nothing: it reported
`qwen-vl-ocr` as unavailable and **activated the fallback on a perfectly healthy model**, while
marking `text-embedding-v4` unverified.

Neither model was down. The probe was sending a text-only chat call to *every* frozen id - and an
embedding model has no chat endpoint, while a vision model rejects a message with no image part.
The check was manufacturing its own outages.

The first fix was to make the probe modality-aware (embeddings -> `embeddings.create`, vision -> a
message with an image part). That surfaced the second bug immediately: the vision model rejected the
1x1 PNG with `[height:1 or width:1 must be larger than 10]`.

And that error is the actual insight. **A model that rejects our input has, by definition, answered
us** - it is deployed, reachable, and talking. It is only a model that is *gone* that should trigger
a fallback. So the probe now fails closed on absence (`model_not_found`, `does not exist`) and open
on argument: a 400 about a parameter counts as reachable. Without that distinction the check is
fragile in the worst possible direction - any future tightening of an input rule by Model Studio
would silently reroute production traffic onto a different model, which is precisely the outcome
FR-012 exists to prevent.

Live, after the fix: **all four frozen model ids verified, zero substitutions, nothing unverified.**

Two properties the check is built to have, both because the alternative is worse: it never blocks a
cold start (a boot check that can take the API down is a liability, not a safeguard), and any
substitution is visible on `/health` (a silent fallback is how you spend a day debugging a quality
regression before noticing you have been on a different model since Tuesday).

### FR-003: two functions, one pipeline

`deploy/s.yaml` (Serverless Devs 3.0.0, `fc3`) deploys `quotemind-api` on an HTTP trigger and
`quotemind-ingest` on an OSS object-created trigger over `quotemind-inbox/rfq/`. They share one
codebase on purpose - an ingest path with its own copy of the quoting logic would be a second system
that could disagree with the first about the price. `api/fc.py` is a thin shim: FC 3.0 runs an ASGI
app directly, so `handler` *is* the FastAPI app rather than a hand-rolled event adapter that could
drift from the one every test exercises.

The `authType: anonymous` trigger is argued for in the file rather than glossed over: FC's gateway
auth signs with the account AK/SK, which a browser dashboard cannot hold and a judge cannot use, so
the *application* is the authorization boundary (bearer token on every `/api/*` route, FR-010) and
`/health` is deliberately open so the deployment can be verified without a credential. Demo-grade by
design, and section 3.2 says so.

### Submission artifacts

- **SUB-02** README section "Proof of Alibaba Cloud Deployment", linking the module and tabulating
  what each check proves. The deployed endpoint URL is the one blank left - it needs `s deploy`.
- **SUB-03** `docs/architecture.md` + `architecture.mmd` + rendered `architecture.png`. The diagram
  puts the deterministic pricing engine in ochre and the two gates in red, because those are the
  parts of the picture that carry the argument.
- **SUB-04** `docs/demo-script.md` - five beats, ~3 minutes, paced so the beat that matters (the
  system refusing to sign off a thin-margin quote) lands with time to spare. It includes a
  "what not to do" section: do not hide the one eval failure, do not fake the 23-second latency, do
  not oversell the autonomy.
- **SUB-05** `docs/submission-description.md`, 491 words of the 500 allowed.
- **SUB-06** Track 4 badge already in the README.

Makefile targets are now real rather than `@echo` placeholders: `make proof`, `make deploy`,
`make deploy-frontend`, `make eval`, `make eval-smoke`, `make eval-baseline`, `make diagrams`,
`make demo`.

Verification: ruff clean, mypy clean (74 files), import-linter 4/4 kept, pytest 237 passed, pricing
branch coverage 100%. Live: alibaba_proof 8/8, /health reports 4/4 models verified.

## Batch: vision OCR + the deployment made real (feat/vision-ocr)

FR-031/032, and FR-003/FR-012/FR-106 taken from "descriptor exists" to "you can click it".

**Vision OCR (FR-031/032).** Scanned RFQs are rasterised at 200 DPI (10-page cap) and read by
`qwen-vl-ocr`. The prompt demands JSON only; `strip_fence` removes a code fence and nothing else -
it never "repairs" malformed JSON, because a parser that guesses at a price is worse than one that
refuses. An unreadable quantity becomes `None`, never a guess. This unblocked the 5 scanned cases the
eval had been carrying as skipped, so the denominator is now the real 30.

**The eval, complete for the first time.** 30/30 runnable, including 5 real OCR scans:

| | task success | line F1 | SKU top-1 | price exact | needs human | p50 | $/quote |
|---|---|---|---|---|---|---|---|
| pipeline | **97%** | 0.993 | 100% | **97%** | 7% | 23.0 s | $0.0103 |
| single-agent baseline | 40% | 0.929 | 98% | 40% | **0%** | 22.8 s | $0.0109 |

A +57 point gap, and the baseline got *worse* when the scans were added (48% -> 40%): more documents
mean more arithmetic, and it does the arithmetic in the model. It is exactly priced-correctly 40% of
the time and it flags a problem 0% of the time. That combination - confidently wrong, silently - is
the failure mode the whole architecture exists to prevent.

**Function Compute: four 502s, and what each one actually was.** The endpoint is now live at
https://quotemind-api-yccvwlooxw.ap-southeast-1.fcapp.run. Getting there cost four wrong answers,
and the useful part of this entry is that the first three were guesses:

1. *No dependencies in the bundle.* Fixed with a root `requirements.txt` + `s build`.
2. *`PYTHONPATH` clobbered FC's default.* FC vendors runtime deps at `/code/python`; setting our own
   PYTHONPATH replaced that path rather than adding to it, so the function booted with our package
   importable and not one of its dependencies. It must lead with `/code/python`.
3. *`AttributeError: module 'lib' has no attribute 'GEN_EMAIL'`.* `oss2` -> `aliyunsdkcore` ->
   vendored urllib3 -> pyOpenSSL. The runtime ships an old pyOpenSSL; our bundle shadowed the
   runtime's `cryptography` with a modern one that had removed the binding it dereferences at import.
   Both halves must now be pinned together, and the pairing is load-bearing.
4. *The real one.* I had asserted, confidently and wrongly, that "FC 3.0 runs an ASGI app directly".
   Then that FC serves HTTP functions over WSGI. Both were assumptions. So I stopped guessing and
   logged what FC actually passes: `handler(event: bytes, ctx: FCContext)`, where the event is an
   HTTP envelope (`rawPath`, `headers`, base64 `body`, `requestContext.http.method`) and the
   expected return is an envelope too. FC's WSGI path exists but only fires when
   `request.http_params` is set, and the `fcapp.run` endpoint never sets it. `api/fc.py` now
   translates envelope -> WSGI environ -> app -> envelope, base64 in both directions so a PDF and a
   Vietnamese quote both survive the crossing. `tests/unit/test_fc_handler.py` asserts against the
   captured envelope, not an invented one.

The lesson recorded for its own sake: three deploys were spent guessing because the function's logs
were unavailable, and I kept proposing fixes instead of first fixing the reason I was blind.

**FR-012 was never running in production.** `/health` reported every model `unverified` - correctly,
and I nearly dismissed it as cosmetic. `initializer:` / `initializationTimeout:` is the FC *2.0*
spelling; Serverless Devs accepted the keys, dropped them, and deployed a function with **no
initializer at all** (`s info` confirmed it). Fixing the YAML (`instanceLifecycleConfig`) was
necessary but not sufficient: a probe that only runs from a platform hook is one config typo away
from silently not running again. The probe now runs on first need, and the initializer merely warms
it. Live, `/health` reports `unverified: []`, `substitutions: {}` - every frozen model id answered
from inside FC, which also proves FC -> DashScope connectivity that had never been exercised.

**FR-106 dashboard: served by the API, not by OSS.** OSS refused `Put public object acl` - the
artifacts bucket has Block Public Access on. The right response was not to switch it off: that bucket
holds customer quote PDFs, handed out as 10-minute presigned URLs precisely because they must not be
world-readable. A bucket configured to host a public dashboard is a bucket that would just as happily
serve someone else's quote. The dashboard moved into the package (`src/quotemind/web/`) and is served
at `GET /`, same-origin with the API it calls. Note the trap that nearly ate it: `.fcignore` had a
bare `web/` line, which is gitignore-style and matches at any depth - it would have stripped the
dashboard out of the deployed bundle, and the page would have 500'd in production only.

Verification: ruff clean, mypy clean (77 files), import-linter 4/4 kept, pytest 263 passed, pricing
branch coverage 100%. Live: `/` serves the dashboard, `/health` 200 with 0 unverified models,
`/api/quotes` 401 without a token and returns real Tablestore rows with one.

## Batch: the file channels actually read files (feat/file-intake)

FR-021/022/024/033. This batch exists because the autopilot loop did not work, and finding out why
was worse than the bug.

**The bug.** Both intake channels - `POST /api/rfq` with a file, and the OSS drop - did this:

```python
# Only text-bearing uploads run today; PDF and image parsing land with FR-031/032.
text = raw.decode("utf-8", errors="replace")
```

FR-031/032/033 landed. The comments did not. So a spreadsheet dropped into `quotemind-inbox/rfq/`
was decoded as mojibake, parsed as prose, and parked at `received` - a numbered quote, forever
stuck, with nothing in it. The one intake channel that exists *specifically for files* was the only
one that could not read a file.

**Why the eval did not catch it, which is the part worth keeping.** The eval scores 97% on exactly
these files. It scores them by calling `quote_from_excel` and `quote_from_pdf` **directly**. It
proved the parsers and never once touched the seam that joins them to the product. A harness that
bypasses the broken join will report health forever. So `tests/unit/test_file_intake.py` asserts on
the *seam* - which pipeline each channel selects, and what it hands it - and not on "a quote came
out", which was true of the broken code too.

**The fix.** Parser routing now lives in one place, `QuoteService._pipelines`, keyed by `DocType`,
and both channels call it. A `DocType` with no route is a `KeyError`, and a test asserts the map is
total. `quote_from_image` (FR-033) was added: a photographed RFQ is a one-page scan, so it goes
through the same vision reader as a scanned PDF rather than a second copy of that loop.

**FR-024 was wrong for files, too.** `submit()` hashed the *placeholder text*, so two different
spreadsheets that happened to share a filename collided into one quote - the second customer would
have silently received the first customer's prices - while the same spreadsheet renamed became two
quotes. It now hashes the bytes that actually arrived.

**The OSS trigger, and why it is not in `s deploy`.** Serverless Devs hard-codes a 3 s timeout on the
RAM call that resolves `AliyunOSSEventNotificationRole`; from Vietnam that endpoint answers in 3-20 s.
The deploy aborts *before creating the function*, so we had neither trigger nor function - which is
why `quotemind-ingest` did not exist at all. The trigger is declared in `s.yaml` because that is the
truth about the system, and created once by hand per `docs/deploy/oss-trigger.md`. `logConfig` was
also missing from that function: an event-driven function has no caller to return an error to, so
without logs a failed ingest is just a file that silently never becomes a quote.

**Proven live.** `vi_xlsx_001.xlsx` dropped into `oss://quotemind-inbox/rfq/` produced
**QM-2026-0006**: parsed, matched, priced at 869,400,000 VND, critic-checked, and parked at the human
approval gate flagged `UNKNOWN_CUSTOMER`. That flag is correct - a bare file drop carries no sender,
so the system refuses to guess a pricing tier and asks a human instead.

Verification: ruff clean, mypy clean (77 files), import-linter 4/4 kept, pytest 280 passed, pricing
branch coverage 100%. Traceability backfilled: 84 rows, up from 65 - several FRs were built but had
no evidence row, which is its own kind of untruth.

## Batch: the last two P0s (feat/memory-planner)

FR-044/045/046 (episodic memory) and FR-131 (the planner). Both were "built" in the sense that the
hard parts existed and nothing called them.

**Episodic memory was dead code.** `memory/episodic.py` has had correct, unit-tested importance
scoring, recency decay and effective-score ranking since PR-4. `MemoryFacade` has had `put_episodic`
and `search_episodic` for just as long. Nothing invoked any of it. The system could not remember a
single decision a human had ever made.

Now: on approve or reject, `QuoteService` writes an episode - a bilingual LLM summary (<=120 words),
the items, the outcome, the human's own words, and an importance from FR-046 (approved 0.7, edited
0.8, rejected 0.9, +0.1 over 100M VND). An approval that needed a waiver, or that followed a
revision, is recorded as *edited* rather than *approved*: a quote a human had to argue with is a more
interesting memory than one they nodded through. The write never raises - the decision is already on
the audit chain, and losing the memory of it must not lose the decision.

Before quoting a known customer, the orchestrator recalls the top 3. The vector store ranks on
similarity alone, so it is over-fetched and re-ranked by the FR-046 effective score
(similarity x recency_decay x importance) - without that, a perfectly-matched year-old episode
outranks last week's rejection, which is exactly backwards. The 1200-token budget (FR-049) drops the
weakest, and says so. Every recalled memory id lands in the trace.

**Where memory is not allowed to go.** A recalled episode never touches the money. FR-045 says to
inject the memories into "the drafter context"; there is no LLM drafter to inject into, because the
quote is assembled deterministically, and inventing one so that a retrieved document could nudge a
price would put a similarity search inside the arithmetic path - the one thing this architecture
exists to prevent. The retrieval, the ranking, the budget and the trace record are exactly as
specified. What the memories inform is the human, not the total. That divergence is argued for in
`memory/recall.py` rather than hidden.

**The planner, and how it nearly became theatre.** FR-131 asks for AgentScope's PlanNotebook. The
easy version generates a plan, never consults it, and always reports itself complete - a confident
lie in the one artifact a reviewer opens to find out what happened. So: the plan's subtasks are
closed by the pipeline that actually ran, and a subtask nobody closed still says `todo`. Two things
fell out of building it honestly:

- The plan is created *after* extraction, so it must not list "read the scan" as a subtask. Claiming
  credit for work that finished before the plan existed would be the plan lying on its first line.
- `PlanNotebook.finish_subtask(i)` also advances subtask `i+1` to `in_progress`. The subtask list is
  therefore in *execution* order, not reading order. It was not, and the plan reported the customer
  resolution as still running after it had finished. A test now pins the order.

Trivial quotes skip the plan with a logged reason (FR-131 allows the fast path). The flags that can
gate a plan are the ones that exist at *intake* - line count, a scanned source, an unreadable
quantity, a parser that was unsure. A NO_MATCH line cannot gate it, because NO_MATCH comes from the
matcher, and the plan exists to organise the matcher: planning cannot wait on the result of the thing
it is planning. A test pins that boundary too, so nobody "fixes" it later.

**A trap the store nearly ate.** `QuoteStore.put_quote` takes an explicit column allowlist, not
`**kwargs`. `plan_json` and `episodic_json` would have been silently dropped on the way to
Tablestore, and the reviewer would simply never have seen them - a feature that works in every test
and does nothing in production.

**Proven live.** A scanned Vietnamese RFQ from Thanh Cong: the plan fired (5 subtasks, all closed
with real outcomes - `total 565920000 VND`, `0 recompute diff(s)`), and the episode written from
QM-2026-0001 was recalled at effective score 0.72 (similarity 0.904 x decay 1.000 x importance 0.80),
with its memory id in the trace. Note for operators: Tablestore's vector index is eventually
consistent, so a memory written at approval takes a few seconds to become recallable. In practice the
next RFQ is minutes or days later; it matters only if you test it in a tight loop, as we did.

Verification: ruff clean, mypy clean (80 files), import-linter 4/4 kept, pytest 301 passed, pricing
branch coverage 100%.

## Batch: the dashboard adopts the CyberSkill design system (feat/design-system-ui)

FR-105/106. The dashboard was hand-styled with hardcoded hex values that happened to *resemble*
Umber and Ochre. It now uses the real design system - and the design system turned out to have
opinions that changed what the page says, not just how it looks.

**Vendored, not approximated.** `github.com/cyberskill-official/design-system` ships as npm packages;
this dashboard is one self-contained page served by an event-driven FC handler, with no bundler to
resolve `@cyberskill/tokens` for it. So `tokens.css`, `styles.css`, `glass.css` and the logo are
copied byte-for-byte into `web/vendor/`, inlined at serve time, and pinned by sha256 in
`vendor/MANIFEST.json`. A test re-hashes them on every run. The whole value of vendoring evaporates
the moment someone "just tweaks" a colour in the copy, and Umber/Ochre are what the design system
calls *anchor immutables* - so an edit now fails loudly instead of shipping silently.

The logo is the master file's bytes, per DESIGN.md 1.2.x: the official mark "must be used -
reproduced from the master file, never recreated, retraced, retyped, recoloured". Redrawing it in
CSS would have been quicker, and would have been wrong.

**Two doctrine rules landed squarely on this product.**

*Disclosure is universal* (Part 3h rule 1). Every AI-generated region carries a badge. But a blanket
"AI-generated" banner over a quote would be **false in the direction that matters most**: it would
imply a model priced it. So the disclosure is specific, in both languages and in machine-readable
form - AI reads the document, matches the SKUs, writes the review note and the memory summary; AI
touches **no number**. The prices are exact Decimal from the catalogue, independently recomputed by
the critic. That claim is now the most prominent sentence beneath every quote, which is where it
belongs: it is the entire argument of the system.

*Confidence is calibrated before it is numeric* (Part 3h rule 2). The matcher self-reports a 0.99 on
almost every line. Rendering that as a confidence score would be false precision dressed up as
rigour - it is the model's opinion of itself, not a calibrated claim about this quote. So the page
shows human-review state and provenance instead, and the episodic retrieval scores (similarity,
importance, decay) sit behind a diagnostics toggle where they cannot be mistaken for a promise. A
test fails if anyone starts printing `confidence` on a line.

*Sensitive domains require a human gate* (Part 3h rule 4, naming financial output explicitly). The
approve/reject/revise bar is now the design system's own `HumanReviewGate`, and it says what it is:
"Nothing leaves this system until you approve it."

**UX, beyond the repaint.** The queue no longer rebuilds itself on every 5-second poll - it compares
a signature first. The old behaviour threw away the reviewer's scroll position and keyboard focus
mid-read, which made the dashboard unusable for exactly the task it exists to do. Added: j/k/a/r/e
keyboard review, focus-visible rings, a skip link, aria-live on the toast, `role=listbox` on the
queue, loading skeletons rather than a spinner, honest empty states, and a warm-dark theme (the
design system's, not an inverted-colours guess). A record with no quote - a document the system
refused to guess at - used to render as a blank pane that looked like a bug; it now says what it is.

Verification: ruff clean, mypy clean (81 files), import-linter 4/4 kept, pytest 310 passed, pricing
branch coverage 100%. Deployed: `GET /` returns 200 and 67 KB of self-contained page.

An honest gap: I could not get a rendered screenshot in this environment (the browser extension was
wedged and headless Chrome fought the updater), so the layout has been verified structurally and by
the twelve dashboard tests, but not visually by me. A preview file with mock data ships alongside for
a human to look at.

## Batch: the live audit (fix/live-audit)

Six bugs. Every one passed the whole test suite and failed the moment it met production - and that is
the thread worth pulling: each lived in a seam the tests mocked away.

**1. The plan and the memories were written and never read back.** `QuoteStore` keeps *two* column
allowlists - `put_quote` writes, `get_quote` reads - and I updated one. So `plan_json` and
`episodic_json` were persisted on every quote and read by nobody: the two dashboard panels I had just
built an entire UI redesign around were **empty in production**, while 310 tests went green.

The tests could not have caught it. `FakeStore.put_quote` took `**payloads` and stored anything handed
to it - a test double kinder than the thing it doubles is a double that hides it. There is now one
`PAYLOAD_COLUMNS`, a test asserting the two lists agree, and a fake that rejects any column the real
store would silently drop. I caught this exact trap on the write side in the previous PR, wrote a
comment about it, and then walked into its mirror.

**2. Customer resolution: an unmatched name shadowed an exact email.** The candidate search was an
`or` chain - hint, else company name, else the email's domain - so the email was consulted only when
there was no name at all. Live, "Cong ty Thanh Cong" resolved and "Thanh Cong" did not, from the same
address. The customer was flagged UNKNOWN_CUSTOMER, quoted at **list price instead of their dealer
tier**, and their history was never recalled, because recall needs a resolved customer. Every signal
is now searched and unioned.

**3. The PDF button had never worked, for two independent reasons.** FR-091 specifies a 302 to a
presigned OSS URL. Function Compute's default domain refuses cross-domain redirects
(`ExternalRedirectForbidden`), so the route returned 400 once deployed - it passed under uvicorn. And
the dashboard linked to it with a plain `<a href>`, which sends no Authorization header, so it would
have 401'd anyway. The route now returns the signed URL; the client fetches it with its token and
opens it. The object stays private and the URL short-lived, which is what FR-091 is *for*.

**4. An approved quote could land in `failed_dispatch`.** An RFQ dropped as a file has no sender.
Approval auto-dispatched, dispatch found no address, and a good approved quote turned red. Nothing had
failed; nobody had said where to send it. Dispatch now writes `dispatch.skipped` with its reason and
the quote stays `approved`. The old test asserted the old behaviour - it had encoded the bug as a
requirement.

**5. Approving twice returned 500.** An illegal transition is a conflict, not a server error. Now 409.

**6. Nothing deployed on merge, and nothing said what was live.** There was no deploy workflow: every
release went out because I remembered to run `s deploy` from a laptop, and `/health` said
`git_sha: dev`. The honest answer to "what code is running?" was "probably main, I think". There is
now a deploy workflow - which also sidesteps the Serverless Devs RAM timeout, GitHub's network not
being Vietnam's - `/health` reports the deployed commit, and the workflow **fails if the live SHA is
not the one it just pushed**. A green deploy that shipped the wrong code is worse than a red one,
because nobody looks again.

**Docs.** The submission description claimed 491 words, was 506, and quoted eval numbers from a
25-case run that no longer exists. The demo script walked through a system that predated vision OCR,
the autopilot loop, memory and the planner. Both rewritten; the architecture diagram gains the planner
and episodic recall.

Verification: ruff clean, mypy clean (81 files), import-linter 4/4, pytest 319 passed, pricing branch
coverage 100%. Live after the fixes: a bare-name RFQ from Thanh Cong resolves to `cust_thanhcong` at
dealer tier, recalls its own history (effective 0.719), the PDF downloads (30 KB via signed URL), an
approved file-drop quote stays approved with `dispatch.skipped` audited, and a second approve is 409.

### The seventh and eighth bugs, found while fixing the sixth

**7. A revision threw away the lines it was revising.** `revise()` appended the human's instruction
to `source_text` and re-ran the **text** pipeline. For a quote that arrived as a spreadsheet, a PDF
or a photo, `source_text` is a *placeholder* - the bytes are the document, and the text is only what
a human reads on the record. So a reviewer who asked for a 3% discount on a file-sourced quote got
back a quote with **no line items at all**.

Every test passed, because every test revised a quote that had been pasted as text: the one channel
where the placeholder happens to be the real document. Same seam as the first six.

The extraction is now persisted and `quote_from_revision` re-drafts from *that*. The document is read
exactly once, deliberately: re-OCRing a scan on every revision is not only expensive, it is
non-deterministic - the same page can read differently twice, so an instruction about a *price* could
silently change a *part number*.

**8. There was a third allowlist, and it was the one that wrote.** The comment I had just written on
`put_quote` said "there are TWO such lists". There were three: the keyword-only signature, an inline
tuple in the body that did the actual writing, and `PAYLOAD_COLUMNS` on the read side. `extraction_json`
went into the signature and into `PAYLOAD_COLUMNS` - and the guard test I wrote *in the same commit*
compared exactly those two, so it passed while the column was dropped on the way to Tablestore. The
live revision came back `needs_manual: no stored extraction`.

The same bug, one level deeper, caught by the live site rather than by CI. Again. So the other two
lists are gone: `put_quote` validates against `PAYLOAD_COLUMNS` and **raises** on an unknown column
rather than dropping it, and the test drives a fake Tablestore client to assert that every column the
read side looks for is a column the write side actually sent. A typed signature could not express that
property, which is why it did not hold.

**Also.** `traceability.csv` was missing ten spec FRs entirely - including FR-133, a P0. A matrix that
omits its own failures is not a matrix. They are in it now, honestly marked: four not implemented,
three partial (FR-133 among them: `structured_model=` at the text parser, the matcher and the baseline,
but the vision reader hand-parses JSON, because `qwen-vl-ocr` is an OCR model, not a tool-calling chat
model).

Verification: ruff clean, mypy clean (80 files), import-linter 4/4, **316 passed**, pricing branch
coverage 100%. Live, on a real spreadsheet (QM-2026-0013): "chỉ cần 2 màn hình thôi, không phải 8" ->
all three lines survive, the monitor drops 8 -> 2, and the total is recomputed deterministically from
463,104,000 to 356,832,000 VND.

## Batch: the roadmap, finished (feat/roadmap-finish)

Seven FRs. One of them changed how the product reads, and it is worth saying which and why.

**FR-048 - the terms on a quote are retrieved, not hardcoded.** `DEFAULT_TERMS` was a module-level
constant, so every quote said "giao hàng trong vòng 7 ngày làm việc / delivery within 7 working
days" - *including* a quote for a made-to-order server with a six-week manufacturer lead time. That
is not a formatting problem. It is a promise the business cannot keep, printed on a document the
customer is invoiced from.

The sentences live in the `sop` KnowledgeStore tenant now, and the drafter retrieves them per topic,
seeded with the goods being quoted. Retrieval is *per topic* rather than one global top-k, because a
single search would happily return three payment snippets and no warranty. A topic that retrieves
nothing falls back to the seeded default, because a quote with no payment terms is worse than a
quote with generic ones.

This gives the system its third kind of memory, and they are worth naming together: **procedural**
(what the business always does - `memory/sop.py`), **episodic** (what happened last time with this
customer - `memory/recall.py`), and **semantic** (what the products are - the catalog). All three
inform the draft. None of them is allowed near the arithmetic.

**FR-073 - the critic explains itself, and cannot argue with itself.** The order is load-bearing:
`run_critic` reaches the verdict, in code; *then* `agents/reviewer.py` is handed the finished report
and asked to explain it. The model cannot set `passed`, cannot add or drop a flag, and never sees a
number it could recompute. If the call fails the quote is unaffected. The 80-word cap is enforced
after generation, not merely requested in the prompt, because "concise" is not something a prompt
can promise.

The dashboard renders the two halves side by side and labels them: **KHÔNG DO AI / NOT AI** on the
deterministic verdict, **AI** on the narrative, with a line saying the narrative was written after
the verdict and cannot change it. Collapsing them into one block of prose would hide exactly the
distinction the whole architecture is built on, at the one moment a human is deciding whether to
trust it.

**FR-056** - an out-of-stock line carries its lead time, in both languages, *appended* to whatever
note it already had (a substitution note, typically) rather than replacing it. Two things can be
true about one line. `LEAD_TIME` is non-blocking: it is news, not an error.

**FR-085** - a quote nobody has answered in four hours is badged in the queue and logged. This is
the failure mode an approval gate *creates*: the system did its job, stopped, and asked - and the
asking went unheard.

**FR-104** - `/eval` is public, like `/health`, and for the same reason: the headline of this whole
project is 97% against 40%, and a benchmark a judge has to take on faith is not a benchmark. It
renders a *committed snapshot* rather than running the eval, so the number on the site and the
number in the submission cannot drift apart without a commit saying so. 17 of the 30 cases are ones
we price exactly and the single agent does not.

**FR-124** - Be Vietnam Pro is bundled (Regular / SemiBold / Bold + `OFL.txt`). It was left out on
the reasoning that the repo stays source-only, which was the wrong call for this asset: WeasyPrint's
fallback keeps the diacritics byte-exact, so nothing was broken, but a quotation rendered in whatever
sans-serif the host happens to have is the difference between a document that looks like it came
from a company and one that looks like it came from a script.

**FR-134 - cancel, and the half of it that cannot be built honestly.** A quote at the gate is
cancellable: it ends as `rejected` (the frozen enum's word for "ended, not sent"), but the audit
event is `human.cancel`, so "the operator dropped this" and "the reviewer judged the price wrong"
stay two different facts forever. Only one of them is evidence about the pricing, so a cancel is
**not** written to episodic memory - somebody closing a browser tab must not teach the system to
distrust its own prices.

An *in-flight* run returns **409**, and that is the honest answer rather than a missing feature. The
pipeline runs in a FastAPI BackgroundTask inside the same Function Compute invocation; no second
process holds a handle to it. And the status enum is frozen (section 12.5) with no `cancelled`:
landing an interrupted run in `failed_parse` would put a lie on a hash-chained audit trail, and
`needs_manual` is not reachable from `parsing` under LEGAL_TRANSITIONS. Widening the state machine to
make one P1 fit is exactly the change section 12 says to stop and ask about. **This is a decision for
Stephen, not for me.**

**FR-036 and FR-074 remain unbuilt, on purpose.** Both are P2. FR-074 is the auto-fix loop - a critic
that sends work back to the drafter before a human sees it. Given that this project's entire argument
is that the model does not get to talk its way past the guardrail, an auto-fix loop is a feature I
would want to argue for out loud rather than quietly ship.

Gates: ruff clean, mypy clean (84 files), import-linter 4/4, **334 passed**, pricing branch coverage
100%.

### FR-048, take two: the retrieval was printing a payment obligation nobody agreed to

I shipped FR-048, quoted a Dell PowerEdge server against the live site, and read the terms it
produced. The payment term was **"software licences and implementation services: 100% payment before
activation."**

That is precisely the sin FR-048 exists to fix, committed by FR-048. Two bugs, one symptom:

**The topic filter was applied after a truncation.** `TOP_K` was 4, the search covers the whole
tenant, and the topic filter ran on the results. With 11 snippets across 5 topics, a topic could
contribute a single survivor to the top 4 - and a single survivor wins by default, however badly it
fits. A filter applied after a truncation is a filter over a lottery.

**And similarity is not a classifier.** Even with every candidate present, the software payment term
scored **0.657** against the generic 30-day term's **0.617** for a server. Both are about money,
both say "100%", so they sit close together in the embedding. Similarity had no way to know that a
server is not a software licence, because that is not a similarity question.

Whether a payment term applies to hardware or to software is not fuzzy. **The business knows
exactly.** So `SOPSnippet.applies_to` names the categories a term may be printed on, the categories
of the *matched* lines decide which terms are eligible, and similarity only ranks within that.
Retrieval proposes; the rule disposes - the same shape as the matcher's LLM proposal and its
deterministic banding, and the same shape as the whole project.

Live, after the fix - three RFQs, three genuinely different documents:

| goods | payment | delivery | warranty |
|---|---|---|---|
| 3x PowerEdge R650 | 30% advance over 500M VND | manufacturer lead time | 36 months, on-site |
| 10x Latitude 5450 | 30% advance over 500M VND | 7 working days | 12 months |
| 5x Adobe CC | 100% before activation | free within HCMC/Hanoi | vendor support, no hardware warranty |

One more thing worth recording. The *first* server quote after this deploy still came back with the
old terms, because it landed on a warm Function Compute instance 14 seconds after the rollout. The
env-var `git_sha` on `/health` had already flipped - config updates before code does. That is the
"green deploy shipped the wrong code" failure I built the CD guard for, in miniature, and it means
the guard needs to check *behaviour*, not a version string. Noted for the next round.

### The live URL has never rendered in a browser

Found while trying to screenshot the site for the demo video, which is a humbling way to find it.

Function Compute injects `Content-Disposition: attachment` on **every** response from its default
`*.fcapp.run` domain. We do not set it; it is not configurable. `curl` and `fetch` ignore it - which
is why the API, the integration tests and every live check in this log pass - but **a browser obeys
it**, and a browser is exactly what a judge uses. Open the URL and you get `download.html`.

So the dashboard and `/eval` have never been viewable by anyone. Three separate browsers failed to
screenshot the page during this session and I read each failure as a browser problem. The third one
put a **Save As** dialog on screen with `download (3).html` in it, and I still did not see it.

It is the same restriction that broke the PDF route (`ExternalRedirectForbidden` on a cross-domain
302). The default FC domain is deliberately crippled for browser use in two different ways, and we
have now been bitten by both.

OSS static hosting is not an escape: Block Public Access is set at the **account** level on this
account (`Put public bucket acl is not allowed`), which is the correct setting and should stay - the
artifacts bucket holds customer quote PDFs.

The fix is a custom domain, it takes about fifteen minutes, and it needs Stephen's DNS. Written up
step by step in `docs/deploy/custom-domain.md`, including the two things to change in the repo once
it works - the live URL in the README, and the FR-091 302, whose comment already says "restore the
302 the day a custom domain is bound."

**The lesson is not about Function Compute.** Every check in this project asserts against `curl`, and
`curl` is not the client. The audit that found eight bugs asked *"does the API return the right
JSON?"* over and over, and never once asked *"does the page open?"* A test that never uses the thing
the way a user uses it is a test that can pass forever while the product is unusable.

### CI caught the golden PDF, and the fix removed a skip that had been hiding it

Bundling Be Vietnam Pro (FR-124) changed **29.1% of the pixels** in the rendered quote. That is the
test doing exactly its job: the golden was recorded against WeasyPrint's *fallback* face, and the
brand face is a different typeface. Intentional, and regenerated.

The interesting part is what came off with it. The golden was **pinned to Linux and skipped
everywhere else**, and the old docstring said why:

> "the golden is only portable across machines that resolve the same fonts... Bundling the Be
> Vietnam Pro TTFs is what makes it truly portable, and that is still outstanding."

The TTFs are bundled now. WeasyPrint embeds all five faces into the PDF as TrueType subsets, and
pdfium rasterises those embedded glyphs itself rather than asking the operating system for a font.
So the same quote produces the same pixels everywhere, and the pin is gone: **the test now runs on
the machine where the change is actually being made**, instead of only on the machine where nobody
is looking.

A skipped test catches nothing. This one had been skipped on macOS for its whole life, which is
precisely why a font change reached CI before it reached me.

And a new test asserts the property the pin was standing in for: **the fonts are inside the PDF.**
If WeasyPrint ever stops finding the bundled TTFs it falls back silently - the PDF still renders,
the diacritics still come out right, and the only symptom is a warning on stderr that nobody reads.
`test_the_pdf_carries_its_own_fonts` opens the PDF and checks every face is Be Vietnam Pro and every
one is embedded.

Gates: ruff clean, mypy clean (84 files), import-linter 4/4, **345 passed**, pricing branch coverage
100%.

## Batch: the number was stale, and the refusal was mute (fix/live-url-and-eval)

**Two things needed doing after #23 merged.** The first was the P0 from the last round - the live URL
is a download, not a page. The second I went looking for: the eval snapshot was recorded on 11 July,
*before* FR-048, FR-056 and FR-073 shipped. FR-073 alone adds a whole model call per quote. A
headline claim that predates the code it describes is not a measurement, it is a memory.

So I re-ran it. **The number moved, and not in our favour.**

| | 11 Jul | now |
|---|---|---|
| task success | 96.7% | **93.3%** |
| price exact | 96.7% | **93.3%** |
| caught its own problem | 6.7% | **10.0%** |
| cost / quote | $0.0103 | $0.0126 |
| p50 latency | 23 s | 31 s |

The baseline did not move: 40%, exactly as before. So the gap is **+53 points**, not +57, and every
place that said 97% - the roadmap, the eval page, the dashboard's own tooltip, the README, the
submission text, a docstring in `api/app.py` - said it because a human typed it. Eight files, all
wrong by three points, all silently. A number you copy by hand is a number that goes stale without
telling you. They are corrected; the snapshot itself is generated.

### One case, and the decision not to buy the point back

The whole delta is `adv_002`, which asks for a **Dell Latitude 5450 with 64GB RAM and a 2TB SSD** - a
configuration the catalogue does not sell. On 11 July the matcher substituted the closest thing (an
i7 with 32GB and 1TB) and priced it. Today it looks at that same candidate and refuses:

> *"None of the candidate SKUs meet the requested 64GB RAM and 2TB SSD specifications."*

Five runs out of five. It is not a coin flip and it is not a retrieval bug - I checked, and
`DELL-LAT-5450-I7` is candidate number one. The model simply declines to sell a 32GB machine to
someone who asked for 64GB.

**That is the right call**, and it is the exact behaviour this entire project argues for. The label
disagrees with it. I could have moved the label - it is a synthetic case, and nobody would have
noticed. I did not, and the README now says so out loud: a system whose premise is *stop rather than
guess* should not be quietly re-graded for stopping.

Nothing in this repo changed the matcher. `qwen3-max` is a moving target - the spec froze the model
*id*, not its weights - and this is what that looks like from the inside. It is also the argument for
committing the eval and dating it.

### The bug underneath: a refusal that would not say why

Here is the part that was actually broken. The matcher worked all that out - which SKUs it
considered, that they were 32GB, that 32GB is not 64GB - wrote it down in both languages, handed it
to the pipeline, and the pipeline **threw it away**. On the refusal path the service persisted the
trace and nothing else. What the reviewer saw was:

> *"No quote was produced. The system stopped rather than guess."*

True, and completely useless. To find out what had happened they had to re-read the customer's email
and go through the catalogue by hand - which is the entire job the autopilot exists to do. The system
made a good decision and then declined to explain it, which in practice is barely better than making
a bad one.

A refusal is a decision. It now gets persisted like one: `matches_json` joins the payload columns,
the extraction is kept (so the reviewer can amend and re-run), the clarification reasons land on the
record so the *queue* shows them, and the detail pane renders a table - **what they asked for, what
we nearly matched it to, and why that was not good enough.**

Gates: ruff clean, mypy clean (84 files), import-linter 4/4, **349 passed**, pricing branch coverage
100%.

## Batch: the site is a site (feat/https)

`https://quotemind.cyberskill.world` — a page, in a browser, with a real certificate.

**The CNAME landed, and then FC said no twice, each time usefully.**

First: `DomainNameNotResolved`. Function Compute will not create a custom domain until the CNAME
*already* points at it - which is why DNS is genuinely step one and not something a script can do for
you. Alibaba's own resolver (223.5.5.5) saw the record before Cloudflare's did.

Then: `CertConfig is required but not provided`. FC will not accept `HTTPS` in `protocol` without a
certificate - it is not optional there. And a certificate needs domain validation, which cannot
begin until the domain resolves *somewhere*. So the order is forced: bind HTTP, prove the page
renders, then come back with a cert. An `http://` URL for an hour is better than a download for
another day.

**The certificate, without a single manual step.** Let's Encrypt's HTTP-01 challenge asks one
question - *does this domain serve what you say it serves?* - and once the domain was bound over
HTTP we were in a position to answer it. `deploy/issue_cert.py` orders the certificate, writes the
key authorization to OSS, waits until it can fetch the challenge back through the live site (never
hand a token to a CA before you can serve it yourself), tells Let's Encrypt to validate, and hands
the certificate to FC.

The challenge lives in **OSS, not an environment variable**, and that is the one design decision here
worth defending: an env var means a function redeploy per challenge, and a redeploy inside an ACME
validation window is a race nobody should have to run. Renewal is now a `put_object` and a `curl`.

Staging CA first, and it caught a bug (a cosmetic API that does not exist in this `acme` version)
before it could burn a production rate limit.

**And FR-091 does not get its 302 back.** The comment in `quote_pdf` said "restore the 302 the day a
custom domain is bound." That day arrived and the comment was **wrong**, which is worth saying rather
than quietly deleting. Two things made the redirect unusable, and the domain only fixes one:

  1. `ExternalRedirectForbidden` on the default domain. **Gone** - the custom domain is precisely the
     endpoint that error asked for.
  2. The route is bearer-guarded, and a 302 is only useful to a client that can *follow a link*. A
     plain `<a href>` carries no Authorization header. **Nothing about a domain changes that**, and
     it is why the PDF button had never worked once, anywhere.

The note treated the platform objection as the whole reason when the *client* objection is the one
that decides. The redirect is now merely possible; it was never the better shape. FR-091's actual
guarantee - private object, short-lived signed URL - is preserved either way, and preserved more
usably by handing the URL back.

Gates: ruff clean, mypy clean (84 files), import-linter 4/4, **350 passed**, pricing branch coverage
100%.

### The check that would have caught it, checked in

The live suite that found the `Content-Disposition` P0 was a script in `/tmp`. That is not a check,
it is an anecdote: nobody else can run it, CI does not know it exists, and nothing stops Function
Compute quietly putting the header back. It is now `deploy/smoke.py` (`make smoke`), it runs against
the **deployment** rather than the code, and its first assertion is that `/` and `/eval` send no
`Content-Disposition` at all.

Writing it surfaced a second bug of exactly the same family, this time in my own tooling. The old
script posted a **fixed** RFQ string. Intake is idempotent on the source text (FR-024) - so from its
second run onward it was never exercising the pipeline. It was handed back the quote the *previous*
run had left behind, and asserted against that. It passed, every time, and it was testing nothing:
`cancel` was even "failing" because the quote it re-fetched had already been cancelled an hour
earlier, which is the system behaving perfectly. Every run now posts an RFQ the system has genuinely
never seen, and the pipeline block went from re-reading a cached answer to running end to end.

One more, smaller: the smoke test verifies TLS against a **shipped** CA bundle (`certifi`), not
whatever the machine happens to trust. A macOS framework Python has no root store until someone runs
`Install Certificates.command`, so the naive version failed on a perfectly valid certificate - and a
check that cries wolf on a good deployment is worse than no check, because it teaches you to ignore
it. It still fails on a bad certificate.

Three bugs, one shape: **a check is worth exactly what it would have caught.**

Live, over HTTPS, against a pipeline run from scratch: **16/16**.
Gates: ruff clean, mypy clean (84 files), import-linter 4/4, **350 passed**, pricing branch 100%.

### CD ran for the first time, and took the site down for quoting

The eleven secrets landed, the deploy job stopped no-opping, and `s deploy` shipped this line for the
first time in the project's life:

    DASHSCOPE_BASE_URL: ${{ vars.DASHSCOPE_BASE_URL || 'https://dashscope-intl.aliyuncs.com/api/v1' }}

A fallback typed by hand months earlier and **never once executed**, because until the secrets existed
the job exited at the guard. It was wrong.

DashScope serves the same models under two bases, and they are not interchangeable: `/compatible-mode/v1`
is the OpenAI-compatible API (chat, embeddings, vision) and `/api/v1` is the native one that
AgentScope's `DashScopeChatModel` wants. Five call sites hand `settings.dashscope_base_url` straight
to an `OpenAI(...)` client, so it must be the compatible base; `agents.model.native_base_url` derives
the native base *back out of it*. That made "this setting is always the compatible base" load-bearing,
and it was defended by nothing but a docstring saying so.

Handed the native base, the system did not fall over. It did something worse. **Chat kept working** -
native is what chat wanted anyway - so `/health` was green, the model probe passed 7/7, the dashboard
rendered, `/eval` rendered, auth worked, the audit chain verified. And every embedding call went to
`/api/v1/embeddings`, which does not exist. The matcher took a 404 on every RFQ and every quote died
at `failed_parse`.

**The site was up. The models answered. It could not produce a quote.**

Three fixes, in descending order of importance:

  1. `Settings` now normalizes either form to the compatible base (`_always_the_compatible_base`).
     Fixing the workflow line alone would have been fixing the *instance*: the invariant would still
     have been a comment, and the next person to set that variable would still have had a 50/50
     chance. Both bases are now derived from one value that cannot be wrong.
  2. The workflow line is corrected anyway. Belt and braces - but note that a fallback nobody has
     ever executed is a guess, and this one was a wrong guess sitting in the repo for weeks.
  3. `deploy/smoke.py` settles on any *resting* state, not a hand-listed set of good ones. Its
     `SETTLED` set omitted the failure statuses, so a pipeline that was dying in four seconds
     presented as a 150-second timeout - the check sat there politely re-asking a question that had
     already been answered.

`tests/unit/test_dashscope_base_url.py` is the fence: 5 of its 9 assertions fail on the old code.

The pattern is the one this log keeps recording, one layer further out. It is no longer *"the tests
mock the seam"* - it is now **"the deploy pipeline is a seam, and it had never run."** CD's first
execution is a code path like any other, and it went straight to production.

### CD now asks the second question

The verify step that let the outage through was not wrong, it was *insufficient*, and the difference
matters. It asked **"is the right code live?"** - SHA match, `/health` green, model probe 7/7,
`curl /` returns 200 - and every one of those passed while the site could not produce a quote. It
never asked **"does the thing still work?"**

It also pointed at the `fcapp.run` domain, which is the endpoint that sends
`Content-Disposition: attachment`. So the "the dashboard renders" line in CD was verifying a page
that, in a browser, downloads.

CD now runs `deploy/smoke.py` against the real domain over HTTPS: it pushes an RFQ the system has
never seen all the way to the approval gate, on every deploy. A broken deploy is now a **red** deploy.

That is the whole argument for the smoke test existing, made twice in one afternoon - once by the
bug, once by the pipeline that shipped it.
