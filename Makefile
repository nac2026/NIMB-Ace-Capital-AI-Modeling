# NEPSE Research Copilot — developer commands
# Run `make help` to list targets.

.PHONY: help bootstrap sync up down restart logs ps clean test lint fmt check \
        dagster-dev dagster-eod dagster-scrape dagster-sync \
        dbt-deps dbt-build dbt-test dbt-docs dbt-parse

SHELL := /bin/bash
COMPOSE := docker compose

help:   ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

bootstrap: sync                ## First-time setup: install Python deps
	@echo "→ bootstrap complete. Next: 'make up' to start infra."

sync:                          ## uv sync all workspace members
	uv sync

up:                            ## Start local infra (MinIO, Postgres, Redis)
	$(COMPOSE) up -d
	@echo "waiting for services to become healthy..."
	@$(COMPOSE) ps
	@echo "→ MinIO console: http://localhost:9001  (minioadmin/minioadmin)"
	@echo "→ Postgres:      localhost:5432  (nepse/nepse)"
	@echo "→ Redis:         localhost:6379"
	@echo "→ Run 'make verify' to sanity-check connectivity."

verify:                        ## Verify all infra services reachable
	uv run python scripts/verify_infra.py

down:                          ## Stop local infra (keeps volumes)
	$(COMPOSE) down

restart:                       ## Restart local infra
	$(COMPOSE) restart

logs:                          ## Tail logs from all containers
	$(COMPOSE) logs -f --tail=200

ps:                            ## Show container status
	$(COMPOSE) ps

clean:                         ## Stop infra AND delete all data volumes (destructive)
	$(COMPOSE) down -v
	rm -rf data/minio data/postgres data/redis

test:                          ## Run pytest
	uv run pytest -q

lint:                          ## ruff check
	uv run ruff check .

fmt:                           ## ruff format
	uv run ruff format .

check: lint test               ## lint + test

# ------------------------------------------------------------- Dagster
dagster-dev:                   ## Launch Dagster UI on :3001 (Ctrl+C to stop)
	uv run dagster dev -m nrc_pipelines --port 3001

dagster-eod:                   ## Execute daily_eod_job from CLI (client CSV → Silver → Gold → Postgres)
	uv run dagster job execute -m nrc_pipelines -j daily_eod_job

dagster-scrape:                ## Execute manual_scrape_job from CLI (Sharesansar scraper fallback)
	uv run dagster job execute -m nrc_pipelines -j manual_scrape_job

dagster-sync:                  ## Re-sync Gold tables into Postgres only
	uv run dagster job execute -m nrc_pipelines -j postgres_sync_job

# ------------------------------------------------------------- dbt
# Gold-layer analytics live in dbt. These targets invoke dbt standalone;
# for orchestrated runs (as part of daily_eod_job) dagster-dbt wraps them.
DBT_ENV := DBT_PROFILES_DIR=dbt

dbt-deps:                      ## Install dbt_utils + other package deps (one-time)
	cd dbt && $(DBT_ENV) uv run --env-file ../.env dbt deps

dbt-parse:                     ## Regenerate dbt manifest (Dagster reads this)
	cd dbt && $(DBT_ENV) uv run --env-file ../.env dbt parse

dbt-build:                     ## dbt run + dbt test on every Gold model
	cd dbt && $(DBT_ENV) uv run --env-file ../.env dbt build

dbt-test:                      ## Run dbt tests without rebuilding models
	cd dbt && $(DBT_ENV) uv run --env-file ../.env dbt test

dbt-docs:                      ## Generate + serve dbt docs on :8081
	cd dbt && $(DBT_ENV) uv run --env-file ../.env dbt docs generate
	cd dbt && $(DBT_ENV) uv run --env-file ../.env dbt docs serve --port 8081
