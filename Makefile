# Plume developer targets. Everything runs through uv; see README for prerequisites.
UV ?= uv
COMPOSE ?= docker compose

.PHONY: help install lint format test test-int e2e eval up down clean

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

test: ## Architecture + unit tests (fast, no Docker)
	$(UV) run pytest tests/architecture tests/unit -q

test-int: ## Integration tests (testcontainers Postgres + pgvector; needs Docker)
	$(UV) run pytest tests/integration -q -m integration

e2e: ## End-to-end against the docker compose stack
	$(COMPOSE) up -d --wait
	$(UV) run pytest tests/e2e -q -m e2e; status=$$?; $(COMPOSE) down; exit $$status

eval: ## Release eval gate (gold questions); arrives with slice 4
	@if [ -d tests/eval ]; then $(UV) run pytest tests/eval -q -m eval; \
	else echo "eval: no gold-question suite yet (slice 4)"; fi

up: ## Start the compose stack
	$(COMPOSE) up -d --wait

down: ## Stop the compose stack (keeps the data volume)
	$(COMPOSE) down

clean: ## Remove caches
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage htmlcov
