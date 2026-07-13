"""Silver assets — Bronze conformance, tier-precedence dedup, contract validation.

Dependency model:
  silver_scrip_master                     ← bronze_scraper_scrip_master (bootstrap)
  silver_prices                           ← bronze_scraper_prices  + silver_scrip_master
  silver_closes                           ← bronze_format_b_closes + silver_scrip_master
  silver_fundamentals_long       ┐
  silver_fundamentals_snapshots  ┘ ← bronze_shreyas_fundamentals
                                    + bronze_format_b_fundamentals
                                    + bronze_scraper_fundamentals  (optional)
                                    + silver_scrip_master
  silver_additional_info                  ← bronze_shreyas_additional_info + silver_scrip_master
  silver_corporate_actions                ← bronze_scraper_corporate_actions + silver_scrip_master
  silver_news                             ← bronze_scraper_news + silver_scrip_master
  silver_index                            ← bronze_scraper_index_history

Bootstrap note: silver_scrip_master currently has bronze_scraper_scrip_master
as its only source. To bootstrap a fresh lakehouse, materialize that Bronze
asset once via the manual_scrape_job or `nrc-scrape scrip-master`. Once
populated, daily_eod_job works indefinitely without re-scraping."""
from dagster import (
    AssetExecutionContext,
    AssetOut,
    MetadataValue,
    Output,
    asset,
    multi_asset,
)

from nrc_processing import (
    transform_additional_info,
    transform_closes,
    transform_corporate_actions,
    transform_floorsheet,
    transform_fundamentals,
    transform_index_snapshots,
    transform_internal_trades,
    transform_news,
    transform_prices,
    transform_scrip_master,
)

from ..resources import StorageResource
from .bronze_client_csv import (
    bronze_automation_fundamentals,
    bronze_format_b_closes,
    bronze_format_b_fundamentals,
    shreyas_bronze,
)
from .bronze_internal import bronze_internal_trades
from .bronze_scraper import (
    bronze_scraper_corporate_actions,
    bronze_scraper_fundamentals,
    bronze_scraper_index_history,
    bronze_scraper_news,
    bronze_scraper_prices,
    bronze_scraper_scrip_master,
)
from .bronze_smtm import bronze_smtm_company_list, bronze_smtm_eod_prices, bronze_smtm_floorsheet

_GROUP = "silver"
_COMPUTE_KIND = "python"


def _emit(context: AssetExecutionContext, report) -> Output[int]:
    """Uniform Output wrapping — row counts + version + duration."""
    context.log.info(report.summary())
    for w in report.warnings[:5]:
        context.log.warning(w)
    return Output(
        value=report.rows_written,
        metadata={
            "rows_written": MetadataValue.int(report.rows_written),
            "rows_read": MetadataValue.int(report.rows_read),
            "delta_version": MetadataValue.int(report.delta_version),
            "duration_s": MetadataValue.float(report.duration_s),
            "warnings": MetadataValue.int(len(report.warnings)),
        },
    )


@asset(
    group_name=_GROUP,
    key_prefix=["silver"],
    deps=[bronze_smtm_company_list, bronze_scraper_scrip_master],
    description=(
        "Universe master — all-sector NEPSE equities from SMTM company_list "
        "(~243 active across 12 sectors), share-structure enriched from the "
        "scraper where it overlaps. Applies canonical_ticker so all downstream "
        "JOINs share one form. Blocks every Silver asset that filters on "
        "is_active. Falls back to scraper-only if the SMTM Bronze is absent."
    ),
    metadata={"table": "silver.scrip_master"},
    compute_kind=_COMPUTE_KIND,
)
def silver_scrip_master(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit(context, transform_scrip_master(settings=storage.settings))


@asset(
    group_name=_GROUP,
    key_prefix=["silver"],
    deps=[bronze_smtm_eod_prices, bronze_scraper_prices, silver_scrip_master],
    description=(
        "Strict OHLCV bars conforming to nrc_contracts.DailyBar. Source-tier "
        "deduped on (scrip, date): SMTM EOD snapshot (all sectors, LIVE_API) wins "
        "over the banks-only scraper history. Grows one trading day at a time."
    ),
    metadata={"table": "silver.prices"},
    compute_kind=_COMPUTE_KIND,
)
def silver_prices(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit(context, transform_prices(settings=storage.settings))


@asset(
    group_name=_GROUP,
    key_prefix=["silver"],
    deps=[bronze_format_b_closes, silver_scrip_master],
    description=(
        "Close-only daily prices conforming to nrc_contracts.DailyClose. "
        "~14 years of history for 18 banks (SCB has fundamentals but no price "
        "file — client data gap). Distinct from silver.prices so OHLCV "
        "consumers don't have to handle nulls."
    ),
    metadata={"table": "silver.closes"},
    compute_kind=_COMPUTE_KIND,
)
def silver_closes(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit(context, transform_closes(settings=storage.settings))


@multi_asset(
    group_name=_GROUP,
    outs={
        "silver_fundamentals_long": AssetOut(
            key_prefix=["silver"],
            description=(
                "One row per (scrip, fy, quarter, canonical_metric) after "
                "source-tier precedence dedup: client_authoritative (Shreyas) "
                "> client_historical (Format B) > scraped (Sharesansar). "
                "Metric label canonicalization via _metric_map.py."
            ),
            metadata={"table": "silver.fundamentals_long"},
        ),
        "silver_fundamentals_snapshots": AssetOut(
            key_prefix=["silver"],
            description=(
                "Wide pivot of fundamentals_long — one row per (scrip, fy, "
                "quarter) with ~55 snake_case columns. This is the shape the "
                "`get_fundamentals` tool returns."
            ),
            metadata={"table": "silver.fundamentals_snapshots"},
        ),
    },
    deps=[
        shreyas_bronze,
        bronze_automation_fundamentals,
        bronze_format_b_fundamentals,
        bronze_scraper_fundamentals,
        silver_scrip_master,
    ],
    compute_kind=_COMPUTE_KIND,
)
def silver_fundamentals(
    context: AssetExecutionContext, storage: StorageResource
):
    """Produce long + wide Silver fundamentals in a single transform pass."""
    long_report, wide_report = transform_fundamentals(settings=storage.settings)
    context.log.info(long_report.summary())
    context.log.info(wide_report.summary())
    for w in (long_report.warnings + wide_report.warnings)[:5]:
        context.log.warning(w)
    yield Output(
        value=long_report.rows_written,
        output_name="silver_fundamentals_long",
        metadata={
            "rows_written": MetadataValue.int(long_report.rows_written),
            "rows_read": MetadataValue.int(long_report.rows_read),
            "delta_version": MetadataValue.int(long_report.delta_version),
            "duration_s": MetadataValue.float(long_report.duration_s),
            "warnings": MetadataValue.int(len(long_report.warnings)),
        },
    )
    yield Output(
        value=wide_report.rows_written,
        output_name="silver_fundamentals_snapshots",
        metadata={
            "rows_written": MetadataValue.int(wide_report.rows_written),
            "rows_read": MetadataValue.int(wide_report.rows_read),
            "delta_version": MetadataValue.int(wide_report.delta_version),
            "duration_s": MetadataValue.float(wide_report.duration_s),
            "warnings": MetadataValue.int(len(wide_report.warnings)),
        },
    )


@asset(
    group_name=_GROUP,
    key_prefix=["silver"],
    deps=[shreyas_bronze, silver_scrip_master],
    description=(
        "Wide snapshot of Shreyas-provided ratios + capital + per-share "
        "(CAR, NPL, CD ratio, CoF, base rate, Tier 1/2 capital, MVPS, EPS, "
        "PE, BVPS, dividend, bonus). One row per (scrip, fy, quarter)."
    ),
    metadata={"table": "silver.additional_info"},
    compute_kind=_COMPUTE_KIND,
)
def silver_additional_info(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit(context, transform_additional_info(settings=storage.settings))


@asset(
    group_name=_GROUP,
    key_prefix=["silver"],
    deps=[bronze_scraper_corporate_actions, silver_scrip_master],
    description="Bonus, cash dividend, and rights issue events per scrip.",
    metadata={"table": "silver.corporate_actions"},
    compute_kind=_COMPUTE_KIND,
)
def silver_corporate_actions(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit(context, transform_corporate_actions(settings=storage.settings))


@asset(
    group_name=_GROUP,
    key_prefix=["silver"],
    deps=[bronze_scraper_news, silver_scrip_master],
    description="Scrip-tagged news headlines, one row per article.",
    metadata={"table": "silver.news_articles"},
    compute_kind=_COMPUTE_KIND,
)
def silver_news(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit(context, transform_news(settings=storage.settings))


@asset(
    group_name=_GROUP,
    key_prefix=["silver"],
    deps=[bronze_scraper_index_history],
    description="NEPSE + sector index daily OHLCV history.",
    metadata={"table": "silver.index_snapshots"},
    compute_kind=_COMPUTE_KIND,
)
def silver_index(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit(context, transform_index_snapshots(settings=storage.settings))


@asset(
    group_name=_GROUP,
    key_prefix=["silver"],
    deps=[bronze_smtm_floorsheet],
    description=(
        "Validated floor-sheet trades conforming to nrc_contracts.FloorsheetTrade, "
        "deduped on contract_number. The microstructure base for the broker-flow "
        "Gold models (broker_flow_daily, broker_concentration_daily, "
        "broker_accumulation, broker_pair_graph, speculation_score)."
    ),
    metadata={"table": "silver.floorsheet"},
    compute_kind=_COMPUTE_KIND,
)
def silver_floorsheet(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit(context, transform_floorsheet(settings=storage.settings))


@asset(
    group_name=_GROUP,
    key_prefix=["silver"],
    deps=[bronze_internal_trades],
    description=(
        "The firm's own fills conforming to nrc_contracts.InternalTrade — "
        "contract_number cast to BIGINT (the silver.floorsheet join key), "
        "deduped on (contract_number, client_code, side). Feeds the "
        "internal-trade surveillance Gold models."
    ),
    metadata={"table": "silver.internal_trades"},
    compute_kind=_COMPUTE_KIND,
)
def silver_internal_trades(
    context: AssetExecutionContext, storage: StorageResource
) -> Output[int]:
    return _emit(context, transform_internal_trades(settings=storage.settings))
