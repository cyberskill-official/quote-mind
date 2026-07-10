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
