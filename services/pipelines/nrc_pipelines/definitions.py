"""Dagster Definitions entry point — loads every asset, job, schedule, sensor.

Structure:
  assets.bronze_client_csv   — Shreyas + Format B adapters (group: 'bronze_client_csv')
  assets.bronze_scraper      — 6 scraper-backed adapters (group: 'bronze_scraper', manual)
  assets.silver              — 8 Silver transforms (group: 'silver')
  assets.gold                — 5 Gold transforms (group: 'gold')
  assets.postgres            — schema migrations + sync (group: 'postgres')

  jobs.daily_eod_job         — primary daily refresh (client CSV → Silver → Gold → sync)
  jobs.manual_scrape_job     — scraper-backed Bronze, opt-in only
  jobs.postgres_sync_job     — Gold → Postgres only, for manual re-sync

Run locally: `uv run dagster dev -m nrc_pipelines --port 3001`."""
from __future__ import annotations

from dagster import Definitions, load_assets_from_modules
from dagster_dbt import DbtCliResource

from .assets import bronze_client_csv, bronze_github, bronze_internal, bronze_scraper, bronze_smtm, dbt_analytics, news, postgres, silver
from .assets.dbt_analytics import dbt_project
from .jobs import (
    daily_eod_job,
    floorsheet_job,
    github_prices_backfill_job,
    manual_scrape_job,
    news_job,
    postgres_sync_job,
    tradebook_job,
)
from .resources import ClientDocsResource, StorageResource
from .schedules import (
    daily_eod_schedule,
    floorsheet_intraday_schedule,
    floorsheet_schedule,
    github_prices_schedule,
    news_schedule,
)

# Each module under assets/ contributes its @asset functions. The
# dbt_analytics module exposes one @dbt_assets multi-asset that fans out
# into one Dagster asset per dbt model.
all_assets = load_assets_from_modules(
    [bronze_client_csv, bronze_github, bronze_internal, bronze_scraper, bronze_smtm, silver, postgres, dbt_analytics, news]
)

defs = Definitions(
    assets=all_assets,
    resources={
        "storage": StorageResource(),
        "client_docs": ClientDocsResource(),
        # DbtCliResource invokes the dbt binary under the hood. It takes
        # a project_dir that matches the DbtProject handle used by
        # @dbt_assets so they share the same manifest.
        "dbt": DbtCliResource(project_dir=dbt_project),
    },
    jobs=[daily_eod_job, floorsheet_job, tradebook_job, github_prices_backfill_job, news_job, manual_scrape_job, postgres_sync_job],
    schedules=[daily_eod_schedule, floorsheet_schedule, floorsheet_intraday_schedule, github_prices_schedule, news_schedule],
)
