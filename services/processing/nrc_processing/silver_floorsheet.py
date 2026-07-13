"""Silver transform: bronze.floorsheet_raw → silver.floorsheet.

Conforms to nrc_contracts.FloorsheetTrade. Dedups on contract_number (the
unique trade key) using source-tier precedence + ingested_at, so re-ingesting
a day collapses cleanly.

Unlike the other Silver transforms, validation is enforced in SQL rather than a
per-row Pydantic loop — floor-sheet is the highest-volume table (~60k trades/
day, millions over history) and a Python validation loop would dominate
runtime. The constraints (qty>0, rate>0, non-negative broker ids) are simple
enough to express as a WHERE clause; the FloorsheetTrade contract remains the
documented schema of record for consumers."""
from __future__ import annotations
from datetime import datetime, timezone

from nrc_compute import DuckDBEngine
from nrc_ingestion import source_tier_rank_sql
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import ProcessingReport

_SRC = "bronze.floorsheet_raw"
_DST = "silver.floorsheet"


def transform_floorsheet(
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> ProcessingReport:
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()
    io = DeltaIO(settings)

    with DuckDBEngine(settings) as engine:
        engine.register_table("fs", _SRC)
        rows_read = engine.sql("SELECT COUNT(*) AS n FROM fs").to_pylist()[0]["n"]
        tier_rank_sql = source_tier_rank_sql("fs.source_tier")

        conformed = engine.sql(f"""
            SELECT
                fs.scrip,
                fs.contract_number,
                fs.serial_number,
                fs.buyer_broker,
                fs.seller_broker,
                fs.quantity,
                fs.rate,
                fs.amount,
                fs.traded_at,
                fs.trade_date,
                fs.source,
                fs.source_tier,
                fs.ingested_at
            FROM fs
            WHERE fs.quantity > 0 AND fs.rate > 0 AND fs.amount >= 0
              AND fs.buyer_broker >= 0 AND fs.seller_broker >= 0
              AND fs.contract_number > 0
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY fs.contract_number
                ORDER BY {tier_rank_sql} ASC, fs.ingested_at DESC
            ) = 1
        """)

    io.write(_DST, conformed, mode=mode, partition_by=["trade_date"],
             schema_mode="overwrite" if mode == "overwrite" else None)

    return ProcessingReport(
        table=_DST,
        rows_read=rows_read,
        rows_written=conformed.num_rows,
        delta_version=io.version(_DST),
        started_at=started_at,
        warnings=[],
    )
