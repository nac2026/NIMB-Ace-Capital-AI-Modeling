"""Silver transform: bronze.internal_trades_raw → silver.internal_trades.

Conforms to nrc_contracts.InternalTrade. The key job here is to **cast
contract_number from string → BIGINT** so it joins cleanly to
silver.floorsheet.contract_number (int64) in the Gold surveillance models —
this is the single most important step in the whole feature.

Dedup grain is (contract_number, client_code, side): re-ingesting a day's dump
collapses identical fills, while an intra-firm cross (one fund buys, another
sells the *same* NEPSE contract) keeps BOTH rows so cross-trade detection can
see it. Validation (price>0, qty>0, parseable ids) is enforced in SQL, mirroring
silver_floorsheet; the InternalTrade contract remains the schema of record.

client_name is canonicalized to UPPERCASE with collapsed whitespace — the desk's
dumps spell the same fund inconsistently ('NIBL Sahabhagita Fund' vs
'NIBL SAHABHAGITA FUND'), and mixed casing would make one fund look like two on
the surveillance board. client_code remains the account-level identity."""
from __future__ import annotations
from datetime import datetime, timezone

from nrc_compute import DuckDBEngine
from nrc_ingestion import source_tier_rank_sql
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import ProcessingReport

_SRC = "bronze.internal_trades_raw"
_DST = "silver.internal_trades"


def transform_internal_trades(
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> ProcessingReport:
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()
    io = DeltaIO(settings)

    with DuckDBEngine(settings) as engine:
        engine.register_table("it", _SRC)
        rows_read = engine.sql("SELECT COUNT(*) AS n FROM it").to_pylist()[0]["n"]
        tier_rank_sql = source_tier_rank_sql("it.source_tier")

        conformed = engine.sql(f"""
            SELECT
                it.scrip,
                CAST(it.contract_number AS BIGINT) AS contract_number,
                it.client_code,
                regexp_replace(UPPER(TRIM(it.client_name)), '\\s+', ' ', 'g') AS client_name,
                it.side,
                it.price,
                it.quantity,
                it.value,
                CAST(it.order_id AS BIGINT)        AS order_id,
                it.traded_at,
                it.trade_date,
                it.source,
                it.source_tier,
                it.ingested_at
            FROM it
            WHERE it.price > 0 AND it.quantity > 0 AND it.value >= 0
              AND it.side IN ('B', 'S')
              AND TRY_CAST(it.contract_number AS BIGINT) > 0
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY it.contract_number, it.client_code, it.side
                ORDER BY {tier_rank_sql} ASC, it.ingested_at DESC
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
