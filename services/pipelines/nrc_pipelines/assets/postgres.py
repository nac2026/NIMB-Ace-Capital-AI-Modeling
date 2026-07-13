"""Postgres serving-layer assets — schema migrations + Gold → Postgres sync.

Two assets:
  * postgres_schema   — applies pending SQL migrations idempotently.
                        Runs before sync; blocks every serving table.
  * postgres_sync     — TRUNCATE + COPY every Gold table (plus the Silver
                        tables the tool layer queries directly) into the
                        Postgres serving layer.

Gold inputs come from dbt (not Python). The dbt multi-asset
`dbt_gold_assets` produces peer_rankings_quarterly, indicators_daily,
stage1_screen_results, stage2_bank_screen, valuation — we reference them
by AssetKey so Dagster waits for dbt to finish before running the COPY.

The LLM tool layer queries Postgres, not the lakehouse. Without this sync
the chat UI returns stale data (or empty serving tables if first boot)."""
from dagster import AssetExecutionContext, AssetKey, MetadataValue, Output, asset

from nrc_processing import apply_migrations, sync_all

from ..resources import StorageResource

_GROUP = "postgres"
_COMPUTE_KIND = "postgres"

# dbt asset keys. Dagster auto-generates these from dbt's schema.name
# metadata (`+schema: gold` in dbt_project.yml + the model filename).
_DBT_GOLD_KEYS = [
    AssetKey(["gold", "peer_rankings_quarterly"]),
    AssetKey(["gold", "indicators_daily"]),
    AssetKey(["gold", "stage1_screen_results"]),
    AssetKey(["gold", "stage2_bank_screen"]),
    AssetKey(["gold", "valuation"]),
]


@asset(
    group_name=_GROUP,
    key_prefix=["postgres"],
    description=(
        "Apply any pending Postgres schema migrations under "
        "infra/postgres/schema/. Idempotent — no-op if the latest version "
        "is already applied. Always runs before postgres_sync."
    ),
    metadata={"target": "postgres (serving layer)"},
    compute_kind=_COMPUTE_KIND,
)
def postgres_schema(context: AssetExecutionContext) -> Output[int]:
    applied = apply_migrations()
    if applied:
        context.log.info(f"applied migrations: {applied}")
    else:
        context.log.info("schema already up to date")
    return Output(
        value=len(applied),
        metadata={
            "migrations_applied": MetadataValue.int(len(applied)),
            "versions": MetadataValue.json(applied),
        },
    )


@asset(
    group_name=_GROUP,
    key_prefix=["postgres"],
    deps=[postgres_schema, *_DBT_GOLD_KEYS],
    description=(
        "TRUNCATE + COPY every Gold/serving table into Postgres. This is "
        "what makes fresh data visible to the LLM tool layer — without "
        "this asset, the chat UI queries stale snapshots. Reads both "
        "Delta (Silver) and Parquet (dbt Gold) transparently via DuckDB."
    ),
    metadata={"target": "postgres (serving layer)"},
    compute_kind=_COMPUTE_KIND,
)
def postgres_sync(context: AssetExecutionContext) -> Output[int]:
    reports = sync_all()
    total_rows = 0
    for r in reports:
        context.log.info(r.summary())
        total_rows += r.rows_written
    return Output(
        value=total_rows,
        metadata={
            "tables_synced": MetadataValue.int(len(reports)),
            "total_rows": MetadataValue.int(total_rows),
        },
    )


# Broker-flow serving tables — synced on the floor-sheet cadence (more
# frequent than the daily EOD), so they get a targeted sync that doesn't
# truncate-reload the rest of the serving layer the app is reading.
_BROKER_TABLES = [
    "broker_flow_daily",
    "broker_concentration_daily",
    "broker_accumulation",
    "broker_pair_graph",
    "speculation_score",
    # Internal-trade surveillance serving tables — same cadence as broker flow
    # (they're rebuilt by the same floorsheet_job run).
    "internal_trade_enriched",
    "internal_trade_surveillance",
    "internal_counterparty_exposure",
    "internal_cross_trade",
]
_DBT_BROKER_KEYS = [AssetKey(["gold", t]) for t in _BROKER_TABLES]


@asset(
    group_name=_GROUP,
    key_prefix=["postgres"],
    deps=[postgres_schema, *_DBT_BROKER_KEYS],
    description=(
        "TRUNCATE + COPY just the floor-sheet broker-flow Gold tables into "
        "Postgres. Targeted (sync_all(only=...)) so the floor-sheet cadence "
        "doesn't disturb the rest of the serving layer."
    ),
    metadata={"target": "postgres (broker-flow serving tables)"},
    compute_kind=_COMPUTE_KIND,
)
def postgres_sync_broker(context: AssetExecutionContext) -> Output[int]:
    reports = sync_all(only=_BROKER_TABLES)
    total_rows = 0
    for r in reports:
        context.log.info(r.summary())
        total_rows += r.rows_written
    return Output(
        value=total_rows,
        metadata={
            "tables_synced": MetadataValue.int(len(reports)),
            "total_rows": MetadataValue.int(total_rows),
        },
    )

# NOTE: email alerts are NOT dispatched from the pipeline. The orchestrator's
# always-on background loop (services/orchestrator/.../api_alerts.py) is the
# single emitter — daily digest after close + urgent intraday — so a data
# refresh recomputes the scores without firing its own email.
