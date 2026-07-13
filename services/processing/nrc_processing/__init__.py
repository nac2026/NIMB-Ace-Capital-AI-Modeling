"""Bronze → Silver processing transforms (pure Python / DuckDB SQL).

Gold-layer transforms used to live here too. They have since moved to the
dbt project at `<repo>/dbt/models/gold/` — see that directory for
indicators, peer rankings, stage screens, and valuation. `sync_postgres`
reads the dbt-produced Parquet files on MinIO alongside the Silver Delta
tables transparently (DuckDB reads both formats)."""
from __future__ import annotations

__version__ = "0.1.0"

from ._report import ProcessingReport
from .postgres_schema import apply_migrations
from .silver_additional_info import transform_additional_info
from .silver_closes import transform_closes
from .silver_corporate_actions import transform_corporate_actions
from .silver_floorsheet import transform_floorsheet
from .silver_fundamentals import transform_fundamentals
from .silver_index import transform_index_snapshots
from .silver_internal_trades import transform_internal_trades
from .silver_news import transform_news
from .silver_prices import transform_prices
from .silver_scrip_master import transform_scrip_master
from .sync_postgres import SyncReport, sync_all

__all__ = [
    "ProcessingReport",
    "transform_scrip_master",
    "transform_floorsheet",
    "transform_internal_trades",
    "transform_prices",
    "transform_closes",
    "transform_corporate_actions",
    "transform_fundamentals",
    "transform_additional_info",
    "transform_news",
    "transform_index_snapshots",
    "apply_migrations",
    "sync_all",
    "SyncReport",
]
