# Plan A developer commands. Python runs through uv (Python 3.12), web through npm.
PY := uv run --no-sync python
.DEFAULT_GOAL := help

.PHONY: help setup schemas check-schemas fixtures check-fixtures lint test check bench \
        web-install web-types web-check-types web-bundle web-dev web-build web-test h0 prematch mcp \
        season match duel second-half live final render eval bundle

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

web-bundle: ## Copy the fixture bundle to web/public/match_bundle.json (until `make bundle` exists)
	mkdir -p web/public
	cp fixtures/match_bundle_fixture.json web/public/match_bundle.json

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

# ---- pipeline targets (plan v6 execution §10.2). Not implemented yet: they fail on purpose.
season match duel second-half live final render eval bundle:
	@echo "'make $@' is not implemented yet (see docs/START_HERE.md for owner and milestone)"; exit 1
