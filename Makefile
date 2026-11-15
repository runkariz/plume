# Plume developer targets. Everything runs through uv; see README for prerequisites.
UV ?= uv
COMPOSE ?= docker compose

.PHONY: help install lint format test test-int e2e e2e-live e2e-live-claude eval up down clean

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

E2E_TOKEN ?= pl_e2e_local_only
E2E_PG ?= 18434
E2E_API ?= 18484
E2E_MCP ?= 18485
E2E_ENV = PLUME_PG_HOST_PORT=$(E2E_PG) PLUME_API_HOST_PORT=$(E2E_API) PLUME_MCP_HOST_PORT=$(E2E_MCP)
E2E_COMPOSE = $(E2E_ENV) $(COMPOSE) -p plume-e2e
e2e: ## End-to-end against its own compose project (plume-e2e; ports 18434/18484/18485)
	PLUME_MAINTAINER_TOKENS='["$(E2E_TOKEN)"]' $(E2E_COMPOSE) up -d --build --wait
	PLUME_E2E_TOKEN=$(E2E_TOKEN) PLUME_E2E_API=http://127.0.0.1:$(E2E_API) \
	PLUME_E2E_MCP=http://127.0.0.1:$(E2E_MCP) \
	PLUME_DATABASE_URL=postgresql+psycopg://plume:plume@127.0.0.1:$(E2E_PG)/plume \
	$(UV) run pytest tests/e2e -q -m e2e; status=$$?; $(E2E_COMPOSE) down -v; exit $$status

e2e-live: ## Live tests (real embeddings; needs PLUME_VERTEX_API_KEY or PLUME_GEMINI_API_KEY)
	$(UV) run pytest tests/integration tests/e2e -q -m live
	PLUME_EVAL_LIVE=1 $(UV) run pytest tests/eval -q -m eval -s

e2e-live-claude: ## Level 2: Claude Code (claude -p + plugin) against a running stack; opt-in, billed
	PLUME_L2_RUN=1 $(UV) run pytest tests/live_claude -m claude_live -v -rs

eval: ## Release gate on the gold sets (offline; PLUME_EVAL_LIVE=1 + a key for live embeddings)
	$(UV) run pytest tests/eval -q -m eval -s

up: ## Start the compose stack (Postgres, API on 18480, MCP on 18481)
	$(COMPOSE) up -d --build --wait

down: ## Stop the compose stack (keeps the data volume)
	$(COMPOSE) down

clean: ## Remove caches
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage htmlcov
