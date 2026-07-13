"""Sync the Gold lakehouse → Postgres serving tables.

Each table: TRUNCATE → psycopg3 COPY FROM STDIN → ANALYZE. COPY is the
fastest bulk-load path in Postgres (2-5× faster than executemany) and
handles 55k indicator rows in well under a second.

Source formats:
  * Delta  — Bronze + Silver + the 5 original Gold tables
  * Parquet — Phase I + J Gold tables (dbt-duckdb 1.9.x doesn't support
              Delta writes via plugin). Read through DeltaIO.read_parquet.

Only Postgres-mirrored tables are synced — query_traces is owned by the
orchestrator and never touched here, schema_migrations is owned by
postgres_schema.apply_migrations()."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import pyarrow as pa

from nrc_storage import DeltaIO, PostgresClient, StorageSettings, get_settings

SourceFormat = Literal["delta", "parquet"]


@dataclass(frozen=True)
class _SyncSpec:
    """One row of the `_SYNC` list — the declarative sync contract.

    `format` tells the sync loop which reader to use. `columns` must match
    both the source schema and the CREATE TABLE column order so COPY
    doesn't need an explicit column list."""
    src_table: str
    dest_table: str
    columns: list[str]
    format: SourceFormat = "delta"


# --------------------------------------------------------------------- sync spec
# Declarative list. Column order matches both the source Delta/Parquet
# schema and the Postgres CREATE TABLE in infra/postgres/schema/.
_SYNC: list[_SyncSpec] = [
    # ==================== Silver (Delta) ====================
    _SyncSpec("silver.scrip_master", "scrips", [
        "scrip", "company_name", "sector", "sub_sector",
        "listed_shares", "paid_up_value", "paid_up_capital",
        "registered_date", "company_id", "is_active",
    ]),
    # daily_bars: hot slice — last 365 days only.
    _SyncSpec("silver.prices", "daily_bars", [
        "scrip", "date", "open", "high", "low", "close",
        "volume", "turnover", "ingested_at",
    ]),
    _SyncSpec("silver.corporate_actions", "corporate_actions", [
        "scrip", "action_type", "ratio", "amount",
        "announcement_date", "book_closure_date", "ex_date",
        "fiscal_year_bs", "source",
    ]),
    _SyncSpec("silver.fundamentals_snapshots", "fundamental_snapshots", [
        "scrip", "fiscal_year_bs", "quarter",
        "net_profit", "operating_profit", "net_interest_income",
        "eps", "bvps", "roe", "roa",
        "npl_ratio", "car", "cd_ratio",
        "total_deposits", "total_loans", "paid_up_capital",
        "pe_ratio", "pb_ratio",
        "total_revenue", "total_assets", "shareholders_equity",
        "market_value_per_share", "dividend_per_share",
    ]),
    _SyncSpec("silver.index_snapshots", "index_snapshots", [
        "index_name", "date", "open", "high", "low", "close",
        "turnover", "change", "percent_change", "computed_at",
    ]),
    # NOTE: news_articles is intentionally NOT synced here — the live newsfeed
    # pipeline (services/newsfeed) owns it via UPSERT + Gemini enrichment.
    # Truncate-reloading it from the stale silver dump would wipe the live feed.

    # ==================== Gold — 5 original (Parquet via dbt) ====================
    _SyncSpec("gold.indicators_daily", "indicators_daily", [
        "scrip", "date", "close",
        "sma_20", "sma_50", "sma_200",
        "ema_12", "ema_26", "rsi_14",
        "macd", "macd_signal", "macd_histogram",
        "bollinger_upper", "bollinger_middle", "bollinger_lower",
        "atr_14", "adx_14", "volume_sma_20",
        "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.peer_rankings_quarterly", "peer_rankings_quarterly", [
        "scrip", "sector", "fiscal_year_bs", "quarter",
        "metric_name", "value", "rank_in_sector", "percentile_in_sector",
        "sector_median", "sector_mean", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.stage1_screen_results", "stage1_screen_results", [
        "scrip", "sector", "fiscal_year_bs", "quarter",
        "profitability_score", "revenue_growth_score", "return_ratio_score",
        "composite_score", "passed", "rank", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.stage2_bank_screen", "stage2_bank_screen", [
        "scrip", "sector", "fiscal_year_bs", "quarter",
        "roe", "roe_percentile",
        "roa", "roa_percentile",
        "net_margin", "net_margin_percentile",
        "npl_ratio", "npl_percentile",
        "car", "car_percentile",
        "cd_ratio", "cd_percentile",
        "composite_score", "flags", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.valuation", "valuation", [
        "scrip", "date", "pe_trailing", "pe_forward", "pb",
        "peer_pe_median", "peer_pb_median", "pe_vs_peer_pct",
        "fair_value_forward_eps", "upside_pct", "computed_at",
    ], format="parquet"),

    # ==================== Gold — Phase I (Parquet) ====================
    _SyncSpec("gold.ttm_fundamentals", "ttm_fundamentals", [
        "scrip", "fiscal_year_bs", "quarter",
        "ttm_net_profit", "ttm_operating_profit", "ttm_profit_before_tax",
        "ttm_interest_income", "ttm_interest_expense",
        "ttm_net_interest_income", "ttm_fees_income", "ttm_net_fees_income",
        "ttm_net_trading_income", "ttm_other_operating_income",
        "ttm_total_operating_income", "ttm_net_operating_income",
        "ttm_impairment_charge", "ttm_staff_expenses", "ttm_other_opex",
        "ttm_depreciation", "ttm_income_tax",
        "total_assets", "total_loans", "loans_to_customers",
        "total_deposits", "shareholders_equity", "paid_up_capital",
        "retained_earnings",
        "ttm_roa", "ttm_roe", "ttm_nim",
        "n_quarters_in_window", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.quarterly_growth", "quarterly_growth", [
        "scrip", "fiscal_year_bs", "quarter",
        "net_profit", "net_profit_qoq_pct", "net_profit_yoy_pct", "net_profit_3y_pct",
        "operating_profit", "operating_profit_qoq_pct", "operating_profit_yoy_pct", "operating_profit_3y_pct",
        "profit_before_tax", "profit_before_tax_qoq_pct", "profit_before_tax_yoy_pct", "profit_before_tax_3y_pct",
        "net_interest_income", "net_interest_income_qoq_pct", "net_interest_income_yoy_pct", "net_interest_income_3y_pct",
        "total_operating_income", "total_operating_income_qoq_pct", "total_operating_income_yoy_pct", "total_operating_income_3y_pct",
        "net_fees_income", "net_fees_income_qoq_pct", "net_fees_income_yoy_pct", "net_fees_income_3y_pct",
        "staff_expenses", "staff_expenses_qoq_pct", "staff_expenses_yoy_pct", "staff_expenses_3y_pct",
        "total_assets", "total_assets_qoq_pct", "total_assets_yoy_pct", "total_assets_3y_pct",
        "total_loans", "total_loans_qoq_pct", "total_loans_yoy_pct", "total_loans_3y_pct",
        "total_deposits", "total_deposits_qoq_pct", "total_deposits_yoy_pct", "total_deposits_3y_pct",
        "shareholders_equity", "shareholders_equity_qoq_pct", "shareholders_equity_yoy_pct", "shareholders_equity_3y_pct",
        "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.dupont_decomposition", "dupont_decomposition", [
        "scrip", "fiscal_year_bs", "quarter",
        "roe_computed", "roa", "equity_multiplier",
        "net_profit_margin", "asset_turnover",
        "tax_burden", "interest_burden", "operating_margin", "nim",
        "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.cost_efficiency", "cost_efficiency", [
        "scrip", "fiscal_year_bs", "quarter",
        "cost_to_income_ratio", "staff_cost_ratio", "other_opex_ratio",
        "depreciation_ratio", "revenue_per_asset", "operating_margin",
        "total_opex", "total_operating_income", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.revenue_quality", "revenue_quality", [
        "scrip", "fiscal_year_bs", "quarter",
        "nii_share", "fees_share", "trading_share", "other_income_share",
        "revenue_diversification_score", "earnings_cv_8q",
        "n_quarters_in_cv_window", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.asset_quality_trends", "asset_quality_trends", [
        "scrip", "fiscal_year_bs", "quarter",
        "npl_ratio", "llp_to_npl_ratio",
        "npl_qoq_change_abs", "npl_yoy_change_abs", "llp_coverage_yoy_change",
        "credit_loss_rate_ttm", "asset_quality_tier", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.capital_strength", "capital_strength", [
        "scrip", "fiscal_year_bs", "quarter",
        "car", "tier1_capital", "tier2_capital", "total_capital",
        "tier1_share", "car_buffer", "car_yoy_change",
        "capital_tier", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.dividend_yield", "dividend_yield", [
        "scrip", "fiscal_year_bs",
        "annual_cash_div_pct", "annual_bonus_pct",
        "market_value_per_share",
        "cash_dividend_yield", "total_dividend_yield",
        "yield_tier", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.piotroski_f_score", "piotroski_f_score", [
        "scrip", "fiscal_year_bs", "quarter",
        "p1_positive_profit", "p2_positive_roa", "p3_profit_grew",
        "p4_roa_improved", "p5_npl_not_worse", "p6_car_not_worse",
        "p7_no_large_issuance", "p8_nim_improved", "p9_cti_improved",
        "f_score", "n_signals_available", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.price_returns", "price_returns", [
        "scrip", "as_of", "close",
        "return_1m", "return_3m", "return_6m", "return_1y",
        "return_3y", "return_5y",
        "drawdown_from_peak", "realized_vol_20d", "position_in_20d_range",
        "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.fundamental_quality_composite", "fundamental_quality_composite", [
        "scrip", "sector", "fiscal_year_bs", "quarter",
        "profitability_pct", "asset_quality_pct", "growth_pct",
        "capital_pct", "efficiency_pct", "piotroski_pct",
        "quality_score_0_100", "quality_tier", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.quality_momentum_matrix", "quality_momentum_matrix", [
        "scrip", "sector", "latest_fy", "latest_quarter",
        "quality_score_0_100", "quality_tier",
        "return_6m", "price_as_of",
        "sector_quality_median", "sector_return_6m_median",
        "is_high_quality", "is_high_momentum",
        "quadrant", "computed_at",
    ], format="parquet"),

    # ==================== Gold — Phase J (Parquet) ====================
    _SyncSpec("gold.valuation_history", "valuation_history", [
        "scrip", "fiscal_year_bs", "quarter",
        "pe_ratio", "pb_ratio",
        "pe_self_pct_5y", "pb_self_pct_5y", "pe_self_pct_all",
        "n_quarters_in_5y_window", "self_valuation_tier", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.operating_leverage", "operating_leverage", [
        "scrip", "fiscal_year_bs", "quarter",
        "op_leverage_raw", "op_leverage_4q_avg", "n_valid_quarters",
        "op_leverage_tier", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.market_cap_metrics", "market_cap_metrics", [
        "scrip", "as_of", "latest_close", "shares_outstanding",
        "market_cap_npr", "market_cap_tier",
        "paid_up_capital_npr", "bvps",
        "price_to_face_value", "price_to_book_computed",
        "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.beta_and_volatility", "beta_and_volatility", [
        "scrip", "as_of", "n_obs",
        "beta", "alpha_annual", "r_squared",
        "annualized_vol", "annualized_return", "sharpe_ratio_2y",
        "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.total_shareholder_return", "total_shareholder_return", [
        "scrip", "as_of", "close_today",
        "close_1y_ago", "close_3y_ago", "close_5y_ago",
        "div_1y", "div_3y", "div_5y",
        "tsr_1y", "tsr_3y", "tsr_5y",
        "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.technical_signal_summary", "technical_signal_summary", [
        "scrip", "latest_indicator_date", "close",
        "r1_trend", "r2_ma_align", "r3_rsi", "r4_macd", "r5_bollinger",
        "signal_sum", "technical_signal", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.sector_momentum", "sector_momentum", [
        "sector", "n_scrips",
        "avg_return_3m", "avg_return_6m", "avg_return_1y",
        "median_return_6m", "return_6m_dispersion",
        "min_return_6m", "max_return_6m",
        "rank_by_6m", "momentum_tier", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.investment_scorecard", "investment_scorecard", [
        "scrip", "sector",
        "quality_pct", "valuation_pct", "momentum_pct", "risk_pct", "income_pct",
        "quality_score_0_100", "pe_self_pct_5y",
        "return_6m", "sharpe_ratio_2y", "total_dividend_yield",
        "scorecard_0_100", "recommendation",
        "computed_at",
    ], format="parquet"),

    # ============ Gold — Floor-sheet broker-flow (Parquet) ============
    # broker_flow_daily + broker_pair_graph are high-volume; full sync is fine
    # at current history (1-day floor-sheet) — add a recent-days slice like
    # daily_bars once multi-month history accrues.
    _SyncSpec("gold.broker_flow_daily", "broker_flow_daily", [
        "scrip", "broker", "trade_date",
        "buy_qty", "sell_qty", "net_qty",
        "buy_amount", "sell_amount", "net_amount",
        "buy_trades", "sell_trades", "trade_sides", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.broker_concentration_daily", "broker_concentration_daily", [
        "scrip", "trade_date", "n_brokers", "total_buy_qty", "total_sell_qty",
        "hhi_buy", "hhi_sell", "hhi_combined",
        "top1_buy_share", "top1_sell_share", "top3_buy_share", "top3_sell_share",
        "buy_dominance_flag", "sell_dominance_flag",
        "buy_control_flag", "sell_control_flag", "concentration_flag", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.broker_accumulation", "broker_accumulation", [
        "scrip", "broker", "cum_net_qty", "cum_net_amount",
        "cum_buy_qty", "cum_sell_qty", "broker_volume", "volume_share",
        "days_active", "days_net_buy", "days_net_sell", "first_day", "last_day",
        "accumulation_rank", "distribution_rank",
        "accumulation_flag", "distribution_flag", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.broker_pair_graph", "broker_pair_graph", [
        "scrip", "broker_lo", "broker_hi", "self_trade",
        "qty_lo_buys", "qty_hi_buys", "pair_qty", "pair_amount", "pair_trades",
        "reciprocal_balance", "pair_volume_share", "circular_score", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.speculation_score", "speculation_score", [
        "scrip", "n_days",
        "c_concentration", "c_control", "c_circular", "c_accumulation", "c_block",
        "has_self_trade", "speculation_score", "speculation_tier", "computed_at",
    ], format="parquet"),

    # ============ Gold — Internal-trade surveillance (Parquet) ============
    # The firm's own fills joined to the floor sheet + market signals. Low
    # volume (the trade book is small) so a full sync is fine.
    _SyncSpec("gold.internal_trade_enriched", "internal_trade_enriched", [
        "contract_number", "scrip", "trade_date", "client_code", "client_name",
        "side", "our_qty", "our_price", "our_value", "order_id", "traded_at",
        "our_broker", "counterparty_broker",
        "day_vwap", "day_high_fs", "day_low_fs",
        "interval_vwap", "n_interval_trades",
        "vol_20d", "prior_high_20d", "prior_low_20d", "day_close",
        "close_t1", "close_t5", "close_t20",
        "markout_1d_pct", "markout_5d_pct", "markout_20d_pct",
        "matched_floorsheet", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.internal_trade_surveillance", "internal_trade_surveillance", [
        "contract_number", "scrip", "trade_date", "client_code", "client_name",
        "side", "our_qty", "our_value", "our_broker", "counterparty_broker",
        "our_price", "day_vwap", "interval_vwap", "n_interval_trades",
        "matched_floorsheet",
        "slippage_vs_vwap_pct", "slippage_npr", "worse_than_range_flag",
        "markout_1d_pct", "markout_5d_pct", "markout_20d_pct",
        "scrip_speculation_score", "scrip_speculation_tier",
        "scrip_concentration_flag", "scrip_circular_score", "scrip_pump_flag",
        "cp_n_trades", "cp_share_of_fund", "cp_market_share", "cp_surprise_z",
        "cp_flagged", "repeat_counterparty_flag", "exit_liquidity_flag",
        "cross_flag", "churn_flag", "bought_near_peak_flag",
        "exec_component", "manip_component", "counterparty_component",
        "cross_component", "outcome_component",
        "surveillance_score", "surveillance_tier", "flag_reasons", "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.internal_counterparty_exposure", "internal_counterparty_exposure", [
        "client_code", "client_name", "counterparty_broker", "scrip",
        "n_trades", "total_qty", "total_amount", "n_days",
        "first_date", "last_date",
        "share_of_fund_qty", "cp_market_share", "surprise_z",
        "cp_is_accumulator", "cp_is_distributor", "cp_in_wash_pair", "cp_flagged",
        "computed_at",
    ], format="parquet"),
    _SyncSpec("gold.internal_cross_trade", "internal_cross_trade", [
        "scrip", "trade_date", "buy_client", "sell_client",
        "buy_contract", "sell_contract",
        "buy_qty", "sell_qty", "buy_price", "sell_price",
        "time_gap_s", "same_client", "computed_at",
    ], format="parquet"),
]


@dataclass
class SyncReport:
    table: str
    rows_written: int
    duration_s: float

    def summary(self) -> str:
        return f"[postgres.{self.table}] wrote {self.rows_written:,} rows in {self.duration_s:.1f}s"


def sync_all(
    *,
    settings: StorageSettings | None = None,
    days_of_bars: int = 365,
    only: list[str] | None = None,
) -> list[SyncReport]:
    """Truncate-and-reload serving tables from the lakehouse.

    `only` limits the run to the given dest_table names (e.g. just the
    broker-flow tables) — useful for incremental syncs that shouldn't
    truncate-reload the tables a live app is serving."""
    settings = settings or get_settings()
    io = DeltaIO(settings)
    pg = PostgresClient(settings)
    pg.open()
    reports: list[SyncReport] = []
    specs = [s for s in _SYNC if only is None or s.dest_table in only]
    try:
        for spec in specs:
            started = datetime.now(timezone.utc)
            # Pick the right reader based on format. Bronze+Silver stay
            # Delta; Gold (dbt) is Parquet.
            if spec.format == "parquet":
                data = io.read_parquet(spec.src_table)
            else:
                data = io.read(spec.src_table)

            # daily_bars is the one table we don't fully mirror — last N days.
            if spec.dest_table == "daily_bars" and days_of_bars:
                data = _recent_bars(data, days_of_bars)

            # dbt-duckdb's external write materializes an EMPTY model as a
            # single all-NULL row; drop those (never valid — every serving
            # table has NOT NULL key columns).
            data = _drop_all_null_rows(data)

            _copy_pyarrow_to_postgres(pg, data, spec.dest_table, spec.columns)
            pg.execute(f"ANALYZE {spec.dest_table}")
            reports.append(SyncReport(
                table=spec.dest_table,
                rows_written=data.num_rows,
                duration_s=(datetime.now(timezone.utc) - started).total_seconds(),
            ))
    finally:
        pg.close()
    return reports


def _drop_all_null_rows(table: pa.Table) -> pa.Table:
    """Drop rows where every column is NULL (dbt-duckdb empty-model artifact)."""
    import pyarrow.compute as pc
    if table.num_rows == 0:
        return table
    any_valid = None
    for col in table.columns:
        valid = col.is_valid()
        any_valid = valid if any_valid is None else pc.or_(any_valid, valid)
    return table.filter(any_valid)


def _recent_bars(table: pa.Table, days: int) -> pa.Table:
    """Keep only the last `days` calendar days of bars (across all scrips)."""
    import pyarrow.compute as pc
    from datetime import timedelta
    if table.num_rows == 0:
        return table
    max_date = pc.max(table["date"]).as_py()
    cutoff = max_date - timedelta(days=days)
    mask = pc.greater_equal(table["date"], pa.scalar(cutoff, pa.date32()))
    return table.filter(mask)


def _copy_pyarrow_to_postgres(
    pg: PostgresClient,
    data: pa.Table,
    table: str,
    columns: list[str],
) -> None:
    """Stream a pyarrow Table into Postgres via psycopg3 COPY FROM STDIN."""
    # Project to the column list, in declared order, so COPY receives tuples
    # positionally matched to the CREATE TABLE.
    projected = data.select(columns)
    # live_quotes has a FK → scrips, so truncating scrips requires CASCADE.
    truncate_sql = f"TRUNCATE {table} CASCADE" if table == "scrips" else f"TRUNCATE {table}"
    with pg.transaction() as conn, conn.cursor() as cur:
        cur.execute(truncate_sql)
        col_list = ", ".join(columns)
        with cur.copy(f"COPY {table} ({col_list}) FROM STDIN") as copy:
            for batch in projected.to_batches():
                rows = batch.to_pylist()
                for r in rows:
                    copy.write_row(tuple(_coerce(r[c]) for c in columns))


def _coerce(v: Any) -> Any:
    """psycopg3 handles most types, but pyarrow sometimes yields numpy scalars
    that the driver rejects. Unwrap to plain Python primitives."""
    if v is None:
        return None
    # numpy integer/float types expose `.item()`; lists come through as-is.
    item = getattr(v, "item", None)
    if callable(item) and not isinstance(v, (list, dict, str, bytes)):
        try:
            return item()
        except (ValueError, TypeError):
            return v
    return v
