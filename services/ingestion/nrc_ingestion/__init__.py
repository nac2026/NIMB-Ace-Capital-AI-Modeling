"""Bronze ingestion — client CSV adapters (default path) + scraper fallback."""
from __future__ import annotations

__version__ = "0.1.0"

from ._report import IngestionReport
from ._source import BronzeStamp, source_tier_rank_sql
from .bronze_corporate_actions import ingest_corporate_actions
from .bronze_fundamentals import ingest_fundamentals
from .bronze_index_history import ingest_index_history
from .bronze_news import ingest_news
from .bronze_prices import ingest_prices
from .bronze_scrip_master import ingest_scrip_master
from .sources.client_csv import (
    ingest_client_csv_automation,
    ingest_client_csv_format_b_fundamentals,
    ingest_client_csv_format_b_prices,
    ingest_client_csv_shreyas,
)
from .sources.client_internal import ingest_client_internal_trades
from .sources.github_prices import ingest_github_nepse_prices
from .sources.smtm import (
    ingest_smtm_company_list,
    ingest_smtm_eod_prices,
    ingest_smtm_floorsheet,
    write_floorsheet_trades,
)

__all__ = [
    "IngestionReport",
    "BronzeStamp",
    "source_tier_rank_sql",
    # SMTM live-API adapters — live NEPSE feed
    "ingest_smtm_floorsheet",
    "ingest_smtm_company_list",
    "ingest_smtm_eod_prices",
    "write_floorsheet_trades",
    # Client CSV adapters — primary ingestion path
    "ingest_client_csv_shreyas",
    "ingest_client_csv_automation",
    "ingest_client_csv_format_b_fundamentals",
    "ingest_client_csv_format_b_prices",
    # Client-internal trade book — the firm's own executions
    "ingest_client_internal_trades",
    # GitHub community price history — fallback / historical backfill
    "ingest_github_nepse_prices",
    # Scraper adapters — manual/fallback only
    "ingest_prices",
    "ingest_corporate_actions",
    "ingest_fundamentals",
    "ingest_news",
    "ingest_scrip_master",
    "ingest_index_history",
]
