"""Silver transform: bronze.additional_info_raw → silver.additional_info.

Conforms to nrc_contracts.AdditionalInfoSnapshot. One row per (scrip,
fiscal_year_bs, quarter) carrying the Shreyas-provided ratio, capital, and
per-share metrics that the client computes upstream (NRB/SEBON-derived).

Column mapping from raw Shreyas labels to canonical snake_case field names
is applied here. Rows that don't correspond to any canonical field are
still available in the Bronze table for ad-hoc queries."""
from __future__ import annotations
from datetime import datetime, timezone

import pyarrow as pa
from pydantic import ValidationError

from nrc_compute import DuckDBEngine
from nrc_contracts import AdditionalInfoSnapshot, Quarter, SourceTier
from nrc_ingestion import source_tier_rank_sql
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import ProcessingReport

_SRC = "bronze.additional_info_raw"
_MASTER = "silver.scrip_master"
_DST = "silver.additional_info"

# Shreyas wide column → AdditionalInfoSnapshot field
_COLUMN_MAP: dict[str, str] = {
    "CapitalFundToRwa":                     "capital_fund_to_rwa",
    "NonPerformingLoanToTotalLoan":         "npl_ratio",
    "TotalLoanLossProvisionToTotalNpl":     "llp_to_npl_ratio",
    "CostOfFundsAsOfDate":                  "cost_of_funds",
    "CreditDepositRatiosAsPerNrbDirective": "cd_ratio",
    "BaseRate":                             "base_rate",
    "AverageInterestSpread":                "avg_interest_spread",
    "AverageYield":                         "avg_yield",
    "NetLiquidAssetByDeposits":             "net_liquid_asset_ratio",
    "MarketValuePerShare":                  "market_value_per_share",
    "EarningsPerShare":                     "earnings_per_share",
    "PeRatio":                              "pe_ratio",
    "NetWorthPerShare":                     "net_worth_per_share",
    "Tier1Capital":                         "tier1_capital",
    "Tier2Capital":                         "tier2_capital",
    "TotalCapital":                         "total_capital",
    "OrdinaryShares":                       "ordinary_shares",
    "Dividend":                             "cash_dividend_pct",
    "Bonus":                                "bonus_pct",
}


def transform_additional_info(
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
    active_only: bool = True,
) -> ProcessingReport:
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    with DuckDBEngine(settings) as engine:
        engine.register_table("bi", _SRC)
        engine.register_table("sm", _MASTER)
        rows_read = engine.sql("SELECT COUNT(*) AS n FROM bi").to_pylist()[0]["n"]

        active_filter = (
            "JOIN sm ON sm.scrip = bi.scrip AND sm.is_active"
            if active_only
            else "LEFT JOIN sm ON sm.scrip = bi.scrip"
        )
        tier_rank_sql = source_tier_rank_sql("bi.source_tier")

        raw_wide = engine.sql(f"""
            SELECT bi.*
            FROM bi
            {active_filter}
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY bi.scrip, bi.fiscal_year_bs, bi.quarter
                ORDER BY {tier_rank_sql} ASC, bi.ingested_at DESC
            ) = 1
        """)

    # Map columns to canonical fields and validate against the contract.
    warnings: list[str] = []
    conformed: list[dict[str, object]] = []
    for r in raw_wide.to_pylist():
        row: dict[str, object] = {
            "scrip": r["scrip"],
            "fiscal_year_bs": int(r["fiscal_year_bs"]),
            "quarter": int(r["quarter"]),
            "source": r.get("source", "client_csv_shreyas"),
            "source_tier": r.get("source_tier", SourceTier.CLIENT_AUTHORITATIVE.value),
            "ingested_at": r["ingested_at"],
        }
        # Initialize all mapped fields to None so validation sees the full shape.
        for canonical in _COLUMN_MAP.values():
            row.setdefault(canonical, None)
        for raw_col, canonical in _COLUMN_MAP.items():
            val = r.get(raw_col)
            if val is not None:
                try:
                    row[canonical] = float(val)
                except (TypeError, ValueError):
                    continue

        try:
            AdditionalInfoSnapshot.model_validate({
                **row,
                "quarter": Quarter(row["quarter"]),
                "source_tier": SourceTier(row["source_tier"]),
            })
            conformed.append(row)
        except ValidationError as e:
            warnings.append(
                f"{row['scrip']} {row['fiscal_year_bs']}Q{row['quarter']}: "
                f"{e.errors()[0]['msg']}"
            )

    schema = pa.schema(
        [
            ("scrip", pa.string()),
            ("fiscal_year_bs", pa.int32()),
            ("quarter", pa.int8()),
            *[(canonical, pa.float64()) for canonical in _COLUMN_MAP.values()],
            ("source", pa.string()),
            ("source_tier", pa.string()),
            ("ingested_at", pa.timestamp("us", tz="UTC")),
        ]
    )
    table = pa.Table.from_pylist(conformed, schema=schema)
    io = DeltaIO(settings)
    io.write(_DST, table, mode=mode, schema_mode="overwrite" if mode == "overwrite" else None)

    return ProcessingReport(
        table=_DST,
        rows_read=rows_read,
        rows_written=table.num_rows,
        delta_version=io.version(_DST),
        started_at=started_at,
        warnings=warnings,
    )
