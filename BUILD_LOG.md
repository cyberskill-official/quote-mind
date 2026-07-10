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
