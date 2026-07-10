.PHONY: setup setup-all dev test lint type verify eval eval-smoke eval-baseline seed demo gc diagrams deploy deploy-frontend proof

## setup: install the package + dev toolchain (light core; Python 3.12)
setup:
	pip install -e .[dev]

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

seed:
	@echo 'seed: implemented in FR-011 (EP-01/EP-04).'
eval-smoke:
	@echo 'eval-smoke: implemented in FR-123 (EP-12).'
eval:
	@echo 'eval: implemented in FR-121 (EP-12).'
eval-baseline:
	@echo 'eval-baseline: implemented in FR-122 (EP-12).'
demo:
	@echo 'demo: implemented in NFR-011 (EP-13).'
gc:
	@echo 'gc: implemented in FR-046 (EP-04).'
diagrams:
	@echo 'diagrams: implemented with the docs/diagrams PR (SUB-03).'
deploy:
	@echo 'deploy: implemented in PR-5 (FR-003).'
deploy-frontend:
	@echo 'deploy-frontend: implemented in EP-10.'
proof:
	@echo 'proof: implemented in PR-5 (FR-005). Run: python -m quotemind.cloud.alibaba_proof'

