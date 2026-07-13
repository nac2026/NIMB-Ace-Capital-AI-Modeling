"""Silver transforms: bronze.fundamentals_raw →
  * silver.fundamentals_long (FundamentalMetric contract — one row per metric)
  * silver.fundamentals_snapshots (FundamentalSnapshot contract — one row per quarter)

Three sources now feed bronze.fundamentals_raw:
  1. Sharesansar scraper  (section ∈ 'balance'/'profitloss'/'keymetrics')
     — period_raw is free-text '2nd Quarter 2082/2083', fiscal_year_bs/
       quarter columns are NULL.
  2. Shreyas tidy CSV     (section ∈ 'shreyas_bs'/'shreyas_is')
     — fiscal_year_bs + quarter pre-populated, period_raw NULL.
  3. Format B wide CSV    (section ∈ 'format_b_bs'/'format_b_is'/
     'format_b_key_stats') — same shape as Shreyas.

Silver picks a single winner per (scrip, fy, quarter, canonical_metric) via
source_tier rank: CLIENT_AUTHORITATIVE (Shreyas) > CLIENT_HISTORICAL
(Format B) > LIVE_API > SCRAPED (Sharesansar). The pivot to wide snapshots
is deterministic once the long table is tier-deduped."""
from __future__ import annotations
from datetime import datetime, timezone

import pyarrow as pa
from pydantic import ValidationError

from nrc_compute import DuckDBEngine
from nrc_contracts import FundamentalMetric, FundamentalSnapshot, Quarter, SourceTier
from nrc_ingestion import source_tier_rank_sql
from nrc_nepal import parse_quarter_period
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._metric_map import CANONICAL_METRICS, METRIC_MAP
from ._report import ProcessingReport

_SRC = "bronze.fundamentals_raw"
_MASTER = "silver.scrip_master"
_DST_LONG = "silver.fundamentals_long"
_DST_WIDE = "silver.fundamentals_snapshots"


def transform_fundamentals(
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
    active_only: bool = True,
) -> tuple[ProcessingReport, ProcessingReport]:
    """Produce silver.fundamentals_long + silver.fundamentals_snapshots in one pass."""
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    with DuckDBEngine(settings) as engine:
        engine.register_table("bf", _SRC)
        engine.register_table("sm", _MASTER)
        rows_read = engine.sql("SELECT COUNT(*) AS n FROM bf").to_pylist()[0]["n"]

        active_filter = (
            "JOIN sm ON sm.scrip = bf.scrip AND sm.is_active"
            if active_only
            else "LEFT JOIN sm ON sm.scrip = bf.scrip"
        )

        # Pull every row with context for classification. period_raw is
        # parsed in Python below for scraper-style rows; Shreyas/Format-B
        # rows already have fiscal_year_bs/quarter columns populated.
        raw = engine.sql(f"""
            SELECT
                bf.scrip,
                bf.section,
                bf.metric,
                bf.period_raw,
                CAST(bf.fiscal_year_bs AS BIGINT) AS fiscal_year_bs,
                CAST(bf.quarter AS BIGINT)        AS quarter,
                bf.value_num,
                bf.source,
                bf.source_tier,
                bf.ingested_at
            FROM bf
            {active_filter}
            WHERE bf.value_num IS NOT NULL
        """)

    # --- Resolve (fy, quarter) from either structured columns or period_raw,
    #     map raw metric to canonical name, emit candidate rows. ---------
    candidates: list[dict[str, object]] = []
    warnings: list[str] = []
    for r in raw.to_pylist():
        key = (r["section"], r["metric"])
        canonical = METRIC_MAP.get(key)
        if canonical is None:
            continue  # unmapped metric — stays in Bronze only
        fy = r["fiscal_year_bs"]
        q = r["quarter"]
        if fy is None or q is None:
            # Fall back to parsing scraper-style period_raw.
            if not r["period_raw"]:
                continue
            try:
                fy, q = parse_quarter_period(r["period_raw"])
            except ValueError as e:
                warnings.append(
                    f"{r['scrip']}: bad period {r['period_raw']!r} ({e})"
                )
                continue
        candidates.append({
            "scrip": r["scrip"],
            "fiscal_year_bs": int(fy),
            "quarter": int(q),
            "metric_name": canonical,
            "value": float(r["value_num"]),
            "source": r["source"],
            "source_tier": r["source_tier"],
            "ingested_at": r["ingested_at"],
        })

    if not candidates:
        warnings.append("no fundamental rows survived mapping")

    # --- Tier-precedence dedup on (scrip, fy, quarter, metric_name) ------
    # Re-enter DuckDB to run the QUALIFY in SQL — cleaner than sorting in
    # Python and matches the pattern used for silver.prices.
    tier_rank_sql = source_tier_rank_sql("source_tier")
    with DuckDBEngine(settings) as engine:
        conn = engine._conn  # pyright: ignore[reportPrivateUsage]
        cand_tbl = pa.Table.from_pylist(candidates, schema=pa.schema([
            pa.field("scrip", pa.string()),
            pa.field("fiscal_year_bs", pa.int64()),
            pa.field("quarter", pa.int64()),
            pa.field("metric_name", pa.string()),
            pa.field("value", pa.float64()),
            pa.field("source", pa.string()),
            pa.field("source_tier", pa.string()),
            pa.field("ingested_at", pa.timestamp("us", tz="UTC")),
        ]))
        conn.register("candidates", cand_tbl)
        deduped = conn.execute(f"""
            SELECT scrip, fiscal_year_bs, quarter, metric_name, value,
                   source, source_tier, ingested_at
            FROM candidates
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY scrip, fiscal_year_bs, quarter, metric_name
                ORDER BY {tier_rank_sql} ASC, ingested_at DESC
            ) = 1
        """).to_arrow_table()

    # --- Validate + write silver.fundamentals_long ----------------------
    long_rows: list[dict[str, object]] = []
    for r in deduped.to_pylist():
        row = {
            "scrip": r["scrip"],
            "fiscal_year_bs": r["fiscal_year_bs"],
            "quarter": int(r["quarter"]),
            "metric_name": r["metric_name"],
            "value": r["value"],
            "reported_date": None,
            "fiscal_year_ad_start": None,
            "source": r["source"],
            "source_tier": (SourceTier(r["source_tier"]) if r["source_tier"] else None),
            "ingested_at": r["ingested_at"],
        }
        try:
            FundamentalMetric.model_validate(row)
            # Store source_tier as its string value on disk (enum would break Arrow).
            row["source_tier"] = r["source_tier"]
            long_rows.append(row)
        except ValidationError as e:
            warnings.append(
                f"{r['scrip']} {r['metric_name']}: {e.errors()[0]['msg']}"
            )

    long_schema = pa.schema([
        ("scrip", pa.string()),
        ("fiscal_year_bs", pa.int32()),
        ("quarter", pa.int8()),
        ("metric_name", pa.string()),
        ("value", pa.float64()),
        ("reported_date", pa.date32()),
        ("fiscal_year_ad_start", pa.date32()),
        ("source", pa.string()),
        ("source_tier", pa.string()),
        ("ingested_at", pa.timestamp("us", tz="UTC")),
    ])
    long_table = pa.Table.from_pylist(long_rows, schema=long_schema)

    io = DeltaIO(settings)
    io.write(_DST_LONG, long_table, mode=mode, schema_mode="overwrite" if mode == "overwrite" else None)
    long_report = ProcessingReport(
        table=_DST_LONG,
        rows_read=rows_read,
        rows_written=long_table.num_rows,
        delta_version=io.version(_DST_LONG),
        started_at=started_at,
        warnings=warnings,
    )

    # --- Wide snapshots — pivot the already-deduped long table -----------
    started_wide = datetime.now(timezone.utc)
    with DuckDBEngine(settings) as engine:
        engine.register_table("fl", _DST_LONG)
        # DuckDB PIVOT requires the full metric list at query-time; pass the
        # canonical set sorted so the column order is deterministic.
        metric_literals = ", ".join(f"'{m}'" for m in sorted(CANONICAL_METRICS))
        wide = engine.sql(f"""
            PIVOT fl
            ON metric_name IN ({metric_literals})
            USING FIRST(value)
            GROUP BY scrip, fiscal_year_bs, quarter
            ORDER BY scrip, fiscal_year_bs, quarter
        """)

    wide_rows = []
    wide_warnings: list[str] = []
    for r in wide.to_pylist():
        try:
            row_for_validation = {**r, "quarter": Quarter(r["quarter"])}
            FundamentalSnapshot.model_validate(row_for_validation)
            wide_rows.append(r)
        except ValidationError as e:
            wide_warnings.append(
                f"{r['scrip']} {r['fiscal_year_bs']}Q{r['quarter']}: {e.errors()[0]['msg']}"
            )

    wide_table = pa.Table.from_pylist(wide_rows, schema=wide.schema)
    io.write(_DST_WIDE, wide_table, mode=mode, schema_mode="overwrite" if mode == "overwrite" else None)
    wide_report = ProcessingReport(
        table=_DST_WIDE,
        rows_read=long_table.num_rows,
        rows_written=wide_table.num_rows,
        delta_version=io.version(_DST_WIDE),
        started_at=started_wide,
        warnings=wide_warnings,
    )

    return long_report, wide_report
