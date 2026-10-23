# Plan A developer commands. Python runs through uv (Python 3.12), web through npm.
PY := uv run --no-sync python
.DEFAULT_GOAL := help

.PHONY: help setup schemas check-schemas fixtures check-fixtures lint test check bench \
        web-install web-types web-check-types web-bundle web-dev web-build web-test h0 prematch mcp \
        season match duel second-half live final render eval bundle seed-search

help:
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  %-16s %s\n",$$1,$$2}'

setup: ## Create .venv (Python 3.12) and install Python + web dependencies
	uv venv --python 3.12 --allow-existing
	uv pip install -e ".[dev,agents]"
	cd web && npm ci

schemas: ## Export JSON Schemas from the Pydantic contracts
	$(PY) -m contracts.export_schemas

check-schemas: ## Fail if exported schemas are stale
	$(PY) -m contracts.export_schemas --check

fixtures: ## Rebuild the illustrative fixtures (scripted, NOT simulated)
	$(PY) -m fixtures.build_fixtures

check-fixtures: ## Fail if fixtures are stale
	$(PY) -m fixtures.build_fixtures --check

lint: ## Ruff
	uv run --no-sync ruff check .

test: ## Pytest
	uv run --no-sync pytest

check: check-schemas check-fixtures lint test ## Everything CI runs for Python

bench: ## Simulator benchmark (person A, H1)
	$(PY) -m sim.bench

web-install: ## npm ci
	cd web && npm ci

web-types: ## Regenerate TS types from contracts/schemas/match_bundle.schema.json
	cd web && npm run gen:types

web-check-types: ## Fail if TS types are stale
	cd web && npm run check:types

web-bundle: ## Copy the FIXTURE bundle to web/public/match_bundle.json (illustrative; `make bundle` for the real one)
	mkdir -p web/public
	test -f web/public/match_bundle.json || cp fixtures/match_bundle_fixture.json web/public/match_bundle.json

web-dev: web-bundle ## Run the web app locally (no backend needed)
	cd web && npm run dev

web-build: web-bundle ## Typecheck and build the static web app
	cd web && npm run build

web-test: ## Frontend tests (vitest)
	cd web && npm test

prematch: ## Pre-match workflow for both staffs (AGENTS_MODE=offline|foundry), writes agents/_out/prematch.json
	$(PY) -m agents.prematch

mcp: ## MCP server on loopback HTTP for one scope (SCOPE=KES|HAR|broadcast)
	$(PY) -m mcp_server --scope $(or $(SCOPE),broadcast) --http

h0: check web-check-types web-build web-test ## H0 gate: contracts, fixtures, tests, web build + tests
	@echo "H0 local checks passed. Remaining H0 item: a Foundry model responds (see docs/START_HERE.md)."

# ---- pipeline targets (plan v6 execution §10.2). The per-stage targets at the end are folded into `bundle`.
season: ## Synthetic season -> data/season/public.json (+ eval_only/truth.json)
	$(PY) -m pipeline.season_io

bundle: ## Full demo pipeline -> web/public/match_bundle.json (AGENTS_MODE=offline|foundry, SEED=match seed)
	$(PY) -m pipeline.build $(if $(SEED),--match-seed $(SEED),)

seed-search: ## Try N match seeds for the demo story criteria (N=36), keeps the smallest passing seed
	$(PY) -m pipeline.build --search $(or $(N),36) --workers $(or $(WORKERS),8)

eval: ## Evaluation E1-E8 + calibration -> eval/results/
	$(PY) -m eval.calibrate_adaptation
	$(PY) -m eval.run

match duel second-half live final render:
	@echo "'make $@' is not implemented yet (see docs/START_HERE.md for owner and milestone)"; exit 1
