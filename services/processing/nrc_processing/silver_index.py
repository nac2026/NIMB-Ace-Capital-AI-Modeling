"""Silver transform: bronze.index_history_raw → silver.index_snapshots.

Conforms to nrc_contracts.IndexSnapshot. Minimal conformance — bronze is
already very close to the contract shape. Applies the same OHLC auto-repair
as silver.prices, in case NEPSE/BANKING indices have the same data quirk."""
from __future__ import annotations
from datetime import datetime, timezone

import pyarrow as pa
from pydantic import ValidationError

from nrc_compute import DuckDBEngine
from nrc_contracts import IndexSnapshot
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import ProcessingReport

_SRC = "bronze.index_history_raw"
_DST = "silver.index_snapshots"


def transform_index_snapshots(
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> ProcessingReport:
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    with DuckDBEngine(settings) as engine:
        engine.register_table("bi", _SRC)
        rows_read = engine.sql("SELECT COUNT(*) AS n FROM bi").to_pylist()[0]["n"]

        conformed = engine.sql("""
            SELECT
                index_name,
                date,
                open,
                GREATEST(open, high, low, close) AS high,
                LEAST(open, high, low, close)    AS low,
                close,
                turnover,
                change,
                percent_change,
                ingested_at AS computed_at
            FROM bi
            WHERE open > 0 AND high > 0 AND low > 0 AND close > 0
        """)

    warnings: list[str] = []
    valid_rows = []
    for row in conformed.to_pylist():
        try:
            IndexSnapshot.model_validate(row)
            valid_rows.append(row)
        except ValidationError as e:
            warnings.append(f"{row.get('index_name')}@{row.get('date')}: {e.errors()[0]['msg']}")

    valid = pa.Table.from_pylist(valid_rows, schema=conformed.schema)
    io = DeltaIO(settings)
    io.write(_DST, valid, mode=mode)

    return ProcessingReport(
        table=_DST,
        rows_read=rows_read,
        rows_written=valid.num_rows,
        delta_version=io.version(_DST),
        started_at=started_at,
        warnings=warnings,
    )
