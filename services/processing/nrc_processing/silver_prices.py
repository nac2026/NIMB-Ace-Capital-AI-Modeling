"""Silver transform: bronze.prices_raw → silver.prices.

Conforms to nrc_contracts.DailyBar. Drops Bronze-only fields (per_change,
status, source_file) and the 10 merged banks' rows (they're still useful
historically, but silver.prices is the 'active universe' table downstream
Gold tables query against).

Validation rules enforced:
  * open/high/low/close > 0
  * volume ≥ 0, turnover ≥ 0

Known data quality repair: Sharesansar's `high`/`low` reflect the intraday
trading range, but `open` and `close` come from official opening/closing
auctions which can fall outside that range on thin days. Roughly 13% of
active-universe rows have close-of-day outside [low, high]. Silver repairs
this by setting `high = GREATEST(open, high, low, close)` and symmetrically
for `low` — the bar still represents the same day, with corrected OHLC
invariants that downstream candle / technical calcs require."""
from __future__ import annotations
from datetime import datetime, timezone

import pyarrow as pa
from pydantic import ValidationError

from nrc_compute import DuckDBEngine
from nrc_contracts import DailyBar
from nrc_ingestion import source_tier_rank_sql
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import ProcessingReport

_SRC = "bronze.prices_raw"
_MASTER = "silver.scrip_master"
_DST = "silver.prices"


def transform_prices(
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
    active_only: bool = True,
) -> ProcessingReport:
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    with DuckDBEngine(settings) as engine:
        engine.register_table("bp", _SRC)
        engine.register_table("sm", _MASTER)
        rows_read = engine.sql("SELECT COUNT(*) AS n FROM bp").to_pylist()[0]["n"]

        # Join against silver.scrip_master to filter to active universe only.
        active_filter = "JOIN sm ON sm.scrip = bp.scrip AND sm.is_active" if active_only else "LEFT JOIN sm ON sm.scrip = bp.scrip"

        # Source-tier precedence dedup: for any (scrip, date) where multiple
        # sources wrote rows (e.g. scraped OHLCV + future live-API OHLCV),
        # keep the one with the best (lowest) tier rank, breaking ties by
        # ingested_at DESC (most recent first).
        tier_rank_sql = source_tier_rank_sql("bp.source_tier")

        conformed = engine.sql(f"""
            SELECT
                bp.scrip,
                bp.date,
                bp.open,
                GREATEST(bp.open, bp.high, bp.low, bp.close) AS high,
                LEAST(bp.open, bp.high, bp.low, bp.close)    AS low,
                bp.close,
                bp.volume,
                bp.turnover,
                CAST(NULL AS INTEGER) AS num_transactions,
                CAST(NULL AS DOUBLE)  AS previous_close,
                CAST(NULL AS DOUBLE)  AS vwap,
                CAST(NULL AS DOUBLE)  AS adjusted_close,
                bp.source,
                bp.source_tier,
                bp.ingested_at
            FROM bp
            {active_filter}
            WHERE bp.open > 0 AND bp.high > 0 AND bp.low > 0 AND bp.close > 0
              AND bp.volume >= 0
              AND bp.turnover >= 0
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY bp.scrip, bp.date
                ORDER BY {tier_rank_sql} ASC, bp.ingested_at DESC
            ) = 1
        """)

    warnings: list[str] = []
    valid_rows = []
    for row in conformed.to_pylist():
        try:
            DailyBar.model_validate(row)
            valid_rows.append(row)
        except ValidationError as e:
            if len(warnings) < 20:
                warnings.append(f"{row.get('scrip')}@{row.get('date')}: {e.errors()[0]['msg']}")

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
