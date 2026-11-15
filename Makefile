# Plume developer targets. Everything runs through uv; see README for prerequisites.
UV ?= uv
COMPOSE ?= docker compose

.PHONY: help install lint format test test-int e2e e2e-live eval up down clean

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

install: ## Create .venv with all dependency groups
	$(UV) sync --frozen

lint: ## ruff (lint + format check), mypy --strict, import-linter
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy
	$(UV) run lint-imports --no-cache

format: ## Apply ruff fixes and formatting
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

test: ## Architecture + unit + contract (fakes) tests (fast, no Docker)
	$(UV) run pytest tests/architecture tests/unit tests/contract -q -m "not integration and not live"

test-int: ## Contract (Postgres) + integration tests (testcontainers pgvector; needs Docker)
	$(UV) run pytest tests/contract tests/integration -q -m "integration and not live"

e2e: ## End-to-end against the docker compose stack (Postgres, API, MCP)
	$(COMPOSE) up -d --build --wait
	$(UV) run pytest tests/e2e -q -m e2e; status=$$?; $(COMPOSE) down; exit $$status

e2e-live: ## Live tests (real embeddings; needs PLUME_VERTEX_API_KEY or PLUME_GEMINI_API_KEY)
	$(UV) run pytest tests/integration tests/e2e -q -m live

eval: ## Release eval gate (gold questions); arrives with slice 4
	@if [ -d tests/eval ]; then $(UV) run pytest tests/eval -q -m eval; \
	else echo "eval: no gold-question suite yet (slice 4)"; fi

up: ## Start the compose stack (Postgres, API on 18480, MCP on 18481)
	$(COMPOSE) up -d --build --wait

down: ## Stop the compose stack (keeps the data volume)
	$(COMPOSE) down

clean: ## Remove caches
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage htmlcov
