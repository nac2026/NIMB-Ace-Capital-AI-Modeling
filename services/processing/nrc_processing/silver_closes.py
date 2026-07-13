"""Silver transform: bronze.closes_raw → silver.closes.

Conforms to nrc_contracts.DailyClose — one row per (scrip, date, source)
where only the close price is known (client historical backfill, 2011→).
Distinct from silver.prices (strict OHLCV) so consumers that only need a
close series can query a simple two-column table without null-handling
boilerplate.

Tier precedence dedup: CLIENT_AUTHORITATIVE > CLIENT_HISTORICAL > LIVE_API >
SCRAPED. Currently only CLIENT_HISTORICAL rows land here (Format B prices),
but the framework is in place for future sources."""
from __future__ import annotations
from datetime import datetime, timezone

import pyarrow as pa
from pydantic import ValidationError

from nrc_compute import DuckDBEngine
from nrc_contracts import DailyClose, SourceTier
from nrc_ingestion import source_tier_rank_sql
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import ProcessingReport

_SRC = "bronze.closes_raw"
_MASTER = "silver.scrip_master"
_DST = "silver.closes"


def transform_closes(
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
    active_only: bool = True,
) -> ProcessingReport:
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    with DuckDBEngine(settings) as engine:
        engine.register_table("bc", _SRC)
        engine.register_table("sm", _MASTER)
        rows_read = engine.sql("SELECT COUNT(*) AS n FROM bc").to_pylist()[0]["n"]

        active_filter = (
            "JOIN sm ON sm.scrip = bc.scrip AND sm.is_active"
            if active_only
            else "LEFT JOIN sm ON sm.scrip = bc.scrip"
        )
        tier_rank_sql = source_tier_rank_sql("bc.source_tier")

        conformed = engine.sql(f"""
            SELECT
                bc.scrip,
                bc.date,
                bc.close,
                bc.source,
                bc.source_tier,
                bc.ingested_at
            FROM bc
            {active_filter}
            WHERE bc.close > 0
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY bc.scrip, bc.date
                ORDER BY {tier_rank_sql} ASC, bc.ingested_at DESC
            ) = 1
        """)

    warnings: list[str] = []
    valid_rows = []
    for row in conformed.to_pylist():
        try:
            DailyClose.model_validate({
                **row,
                "source_tier": SourceTier(row["source_tier"]),
            })
            valid_rows.append(row)
        except ValidationError as e:
            warnings.append(
                f"{row.get('scrip')}@{row.get('date')}: {e.errors()[0]['msg']}"
            )

    valid = pa.Table.from_pylist(valid_rows, schema=conformed.schema)
    io = DeltaIO(settings)
    io.write(_DST, valid, mode=mode, schema_mode="overwrite" if mode == "overwrite" else None)

    return ProcessingReport(
        table=_DST,
        rows_read=rows_read,
        rows_written=valid.num_rows,
        delta_version=io.version(_DST),
        started_at=started_at,
        warnings=warnings,
    )
