.PHONY: setup setup-all dev test lint type verify eval eval-smoke eval-baseline seed demo gc diagrams deploy deploy-frontend proof

## setup: install the package + offline-gate deps (needs pango/cairo for WeasyPrint)
setup:
	pip install -e .[agents,memory,parse,cloud,pdf,dev]

## setup-all: install the full runtime stack + dev toolchain
setup-all:
	pip install -e .[all,dev]

## dev: run the API locally on :9000 (QM_ENV=local)
dev:
	QM_ENV=local uvicorn quotemind.api.app:app --reload --port 9000

## test: offline unit + contract tests (no paid-API calls)
test:
	pytest -q

## lint: ruff + import-linter layer contract (QM-REPO-001 sec 4)
lint:
	ruff check .
	lint-imports

## type: mypy (basic)
type:
	mypy -p quotemind

## verify: Appendix E pre-implementation checks (implemented in PR-4/PR-5)
verify:
	@echo 'Appendix E verification snippets land in PR-4 (memory) / PR-5 (proof).'

## seed: load the demo catalog + customers into Tablestore (FR-011; needs live env)
seed:
	python deploy/seed.py
## eval-smoke: replay the 5 recorded cases with no model (FR-123).
eval-smoke:
	pytest -q tests/integration/test_smoke_eval.py
## eval: the full 30-case run, pipeline vs single-agent baseline (FR-121/122).
eval:
	python -m quotemind.eval_.run --mode both
## eval-baseline: the single-agent control on its own (FR-122).
eval-baseline:
	python -m quotemind.eval_.run --mode baseline
## demo: seed the catalog, then run the demo RFQ end to end (NFR-011).
demo:
	python deploy/seed.py && python deploy/smoke_trace.py
## gc: run episodic forgetting + compaction sweep (FR-046; needs live memory env)
gc:
	python -m quotemind.memory.gc
## diagrams: render the architecture Mermaid to PNG (SUB-03).
diagrams:
	npx -y @mermaid-js/mermaid-cli -i docs/architecture.mmd -o docs/architecture.png -b transparent
## deploy: export GIT_SHA := $(shell git rev-parse --short HEAD)$(shell git diff --quiet || echo -dirty)
deploy: build the bundle, then push both Function Compute functions (FR-003).
## Build first: FC uploads the code dir as-is, so a source-only bundle crashes at cold start.
deploy:
	cd deploy && s build && s deploy -y
## deploy-frontend: publish the dashboard to OSS static hosting (FR-106).
deploy-frontend:
	python deploy/upload_site.py --api-base $(API_BASE)
## proof: exercise DashScope + OSS + Tablestore for real (FR-005 / SUB-02).
proof:
	python -m quotemind.cloud.alibaba_proof

