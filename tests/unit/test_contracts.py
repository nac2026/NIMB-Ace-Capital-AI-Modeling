"""Smoke tests for nrc_contracts: every schema instantiates, validates, and round-trips JSON."""
from __future__ import annotations
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from nrc_contracts import (
    SOURCE_TIER_RANK,
    ActionType,
    AdditionalInfoSnapshot,
    CorporateAction,
    DailyBar,
    DailyClose,
    EventType,
    FundamentalMetric,
    FundamentalSnapshot,
    IndexSnapshot,
    IndicatorSet,
    MacroIndicator,
    NewsArticle,
    PeerRanking,
    Quarter,
    QueryTrace,
    Quote,
    ScripMaster,
    SourceTier,
    Stage1Result,
    Stage2BankResult,
    ToolCall,
    ToolMetadata,
    ToolResponse,
    Valuation,
)

NOW = datetime.now(timezone.utc)


def test_scrip_canonicalization():
    """Scrip symbols are uppercased and stripped."""
    bar = DailyBar(
        scrip="  nabil  ", date=date(2026, 4, 20),
        open=533.0, high=534.9, low=527.1, close=528.0,
        volume=39912, turnover=21109795.6, ingested_at=NOW,
    )
    assert bar.scrip == "NABIL"


def test_daily_bar_rejects_non_positive_close():
    with pytest.raises(ValidationError):
        DailyBar(
            scrip="NABIL", date=date(2026, 4, 20),
            open=500, high=500, low=500, close=0,
            volume=100, turnover=50000, ingested_at=NOW,
        )


def test_daily_bar_forbids_extra_fields():
    with pytest.raises(ValidationError):
        DailyBar(
            scrip="NABIL", date=date(2026, 4, 20),
            open=500, high=500, low=500, close=500,
            volume=100, turnover=50000, ingested_at=NOW,
            unknown_field="oops",
        )


def test_corporate_action_bonus():
    ca = CorporateAction(
        scrip="NABIL", action_type=ActionType.BONUS,
        ratio=0.125, announcement_date=date(2025, 12, 7),
        fiscal_year_bs=2081,
    )
    assert ca.action_type == ActionType.BONUS
    assert ca.ratio == 0.125


def test_fundamental_metric_roundtrip():
    fm = FundamentalMetric(
        scrip="NABIL", fiscal_year_bs=2082, quarter=Quarter.Q2,
        metric_name="roe", value=14.93, ingested_at=NOW,
    )
    raw = fm.model_dump_json()
    assert FundamentalMetric.model_validate_json(raw) == fm


def test_fundamental_snapshot_partial():
    """All fundamental fields are optional — snapshots can be partial."""
    fs = FundamentalSnapshot(
        scrip="NABIL", fiscal_year_bs=2082, quarter=Quarter.Q2,
        roe=14.93, npl_ratio=4.25, car=12.77, cd_ratio=78.12,
    )
    assert fs.roe == 14.93
    assert fs.eps is None


def test_peer_ranking_percentile_bounds():
    with pytest.raises(ValidationError):
        PeerRanking(
            scrip="NABIL", sector="Commercial Bank",
            fiscal_year_bs=2082, quarter=Quarter.Q2,
            metric_name="roe", value=14.9,
            rank_in_sector=1, percentile_in_sector=1.5,   # out of range
            sector_median=12.0, sector_mean=11.5,
            computed_at=NOW,
        )


def test_indicator_set_minimal():
    ind = IndicatorSet(
        scrip="NABIL", date=date(2026, 4, 20), close=528.0,
        sma_20=525.3, rsi_14=52.1, computed_at=NOW,
    )
    assert ind.sma_50 is None
    assert ind.rsi_14 == 52.1


def test_news_article_defaults():
    na = NewsArticle(
        article_id="abc123", url="https://www.sharesansar.com/newsdetail/xyz",
        source="sharesansar", published_at=NOW,
        title="Nabil posts Q2 profit of Rs 4.76 Arba",
        scrip_tags=["NABIL"], event_type=EventType.EARNINGS, ingested_at=NOW,
    )
    assert na.language.value == "en"
    assert "NABIL" in na.scrip_tags


def test_scrip_master():
    sm = ScripMaster(
        scrip="NABIL", company_name="Nabil Bank Limited",
        sector="Commercial Bank", listed_shares=270_569_984.0,
        paid_up_value=100.0, paid_up_capital=27_056_998_400.0,
        registered_date=date(1984, 7, 12), company_id=16,
    )
    assert sm.is_active is True
    assert sm.company_id == 16


def test_macro_indicator():
    mi = MacroIndicator(
        indicator="inflation_cpi", date=date(2026, 3, 1),
        value=3.62, unit="%", ingested_at=NOW,
    )
    assert mi.source == "nrb"


def test_index_snapshot():
    idx = IndexSnapshot(
        index_name="NEPSE", date=date(2026, 4, 20),
        open=2831.8, high=2846.39, low=2813.24, close=2825.23,
        turnover=5_434_240_276.3, change=-13.17, percent_change=-0.46,
    )
    assert idx.close == 2825.23


def test_stage1_result():
    s1 = Stage1Result(
        scrip="NABIL", sector="Commercial Bank",
        fiscal_year_bs=2082, quarter=Quarter.Q2,
        profitability_score=1.2, revenue_growth_score=0.8,
        return_ratio_score=1.5, composite_score=1.17,
        passed=True, rank=3, computed_at=NOW,
    )
    assert s1.passed is True


def test_stage2_bank_result_flags():
    # BFI row: ratios are decimals (0.0425 = 4.25%).
    s2 = Stage2BankResult(
        scrip="NABIL", sector="Commercial Bank", fiscal_year_bs=2082, quarter=Quarter.Q2,
        roe=0.1493, roe_percentile=0.65,
        npl_ratio=0.0425, npl_percentile=0.30,
        car=0.1277, car_percentile=0.55,
        cd_ratio=0.7812, cd_percentile=0.40,
        composite_score=0.72, flags=["NPL_HIGH"],
        computed_at=NOW,
    )
    assert "NPL_HIGH" in s2.flags


def test_stage2_general_sector_result():
    # Non-BFI row: NPL/CAR/CD null, scored on ROE/ROA/net margin.
    s2 = Stage2BankResult(
        scrip="MANDU", sector="Hydro Power", fiscal_year_bs=2082, quarter=Quarter.Q3,
        roe=0.078, roe_percentile=0.6,
        roa=0.033, roa_percentile=0.7,
        net_margin=0.43, net_margin_percentile=0.8,
        composite_score=0.7, flags=["ROE_LOW"],
        computed_at=NOW,
    )
    assert s2.npl_ratio is None and s2.car is None
    assert "ROE_LOW" in s2.flags


def test_valuation():
    v = Valuation(
        scrip="NABIL", date=date(2026, 4, 20),
        pe_trailing=13.86, pb=2.07,
        peer_pe_median=12.5, peer_pb_median=1.8,
        pe_vs_peer_pct=0.11, upside_pct=-0.03,
        computed_at=NOW,
    )
    assert v.pe_trailing == 13.86


def test_query_trace_autogenerates_id():
    qt = QueryTrace(
        query_text="Is NABIL fairly valued?",
        total_latency_ms=1250,
        tool_calls=[
            ToolCall(
                tool_name="valuation", tool_version="1.0.0",
                input={"scrip": "NABIL"}, output={"pe_trailing": 13.86},
                latency_ms=45, started_at=NOW,
            ),
        ],
    )
    assert qt.trace_id is not None
    assert len(qt.tool_calls) == 1


def test_source_tier_rank_strictly_ordered():
    """Client-authoritative beats client-historical beats live-api beats scraped."""
    ranks = SOURCE_TIER_RANK
    assert ranks[SourceTier.CLIENT_AUTHORITATIVE] < ranks[SourceTier.CLIENT_HISTORICAL]
    assert ranks[SourceTier.CLIENT_HISTORICAL] < ranks[SourceTier.LIVE_API]
    assert ranks[SourceTier.LIVE_API] < ranks[SourceTier.SCRAPED]
    # Strict ordering: all four ranks are distinct.
    assert len(set(ranks.values())) == len(ranks)


def test_source_tier_values_are_stable_strings():
    """Enum string values are part of the Bronze wire format — pin them."""
    assert SourceTier.CLIENT_AUTHORITATIVE.value == "client_authoritative"
    assert SourceTier.CLIENT_HISTORICAL.value == "client_historical"
    assert SourceTier.LIVE_API.value == "live_api"
    assert SourceTier.SCRAPED.value == "scraped"


def test_daily_bar_carries_source_tier():
    """DailyBar accepts source_tier; defaults to None for back-compat with
    scraper rows written before the refactor."""
    bar = DailyBar(
        scrip="NABIL", date=date(2026, 4, 20),
        open=533.0, high=534.9, low=527.1, close=528.0,
        volume=39912, turnover=21109795.6,
        source="client_csv_format_b", source_tier=SourceTier.CLIENT_HISTORICAL,
        ingested_at=NOW,
    )
    assert bar.source_tier == SourceTier.CLIENT_HISTORICAL


def test_daily_close_round_trip():
    """Close-only rows: date + close is enough, OHLCV not required."""
    dc = DailyClose(
        scrip="NABIL", date=date(2011, 7, 17), close=101.82,
        source="client_csv_format_b", source_tier=SourceTier.CLIENT_HISTORICAL,
        ingested_at=NOW,
    )
    assert dc.close == 101.82
    assert DailyClose.model_validate_json(dc.model_dump_json()) == dc


def test_daily_close_rejects_non_positive():
    with pytest.raises(ValidationError):
        DailyClose(
            scrip="NABIL", date=date(2011, 7, 17), close=0,
            source="client_csv_format_b", source_tier=SourceTier.CLIENT_HISTORICAL,
            ingested_at=NOW,
        )


def test_fundamental_snapshot_accepts_shreyas_columns():
    """The extended snapshot holds every BS + IS field produced by the
    client Shreyas CSVs without rejecting any."""
    fs = FundamentalSnapshot(
        scrip="NABIL", fiscal_year_bs=2080, quarter=Quarter.Q4,
        # Income statement
        interest_income=46_303_122, interest_expense=30_096_111,
        net_interest_income=16_207_011, fees_income=3_983_518,
        fees_expense=740_242, net_fees_income=3_243_276,
        total_operating_income=20_202_611, impairment_charge=3_224_390,
        net_operating_income=16_978_221, staff_expenses=4_766_245,
        other_operating_expenses=1_685_442, depreciation_amortization=679_683,
        operating_profit=9_846_851, profit_before_tax=9_795_276,
        income_tax=2_735_243, net_profit=7_060_033,
        # Balance sheet
        total_assets=558_421_734, cash_and_bank_balance=8_178_988,
        due_from_nrb=20_182_905, placement_with_bfis=14_287_531,
        loans_to_customers=373_977_599, total_loans=386_127_539,
        investments=107_781_346, total_liabilities=498_853_809,
        total_deposits=462_085_913, shareholders_equity=59_567_925,
        paid_up_capital=27_056_997,
        # Derived
        eps=26.09, bvps=220.16, roe=0.1224, npl_ratio=0.0385,
        car=0.1239, cd_ratio=0.836, pe_ratio=20.08,
    )
    assert fs.total_assets == 558_421_734
    assert fs.net_profit == 7_060_033
    # Back-compat: old partial constructor still works
    partial = FundamentalSnapshot(
        scrip="NABIL", fiscal_year_bs=2082, quarter=Quarter.Q2,
        roe=14.93, npl_ratio=4.25,
    )
    assert partial.eps is None


def test_additional_info_snapshot_roundtrip():
    """The ratio-block snapshot holds the Shreyas additional-info columns."""
    ai = AdditionalInfoSnapshot(
        scrip="NABIL", fiscal_year_bs=2080, quarter=Quarter.Q4,
        capital_fund_to_rwa=0.1239, npl_ratio=0.0385,
        llp_to_npl_ratio=1.1015, cost_of_funds=0.0586,
        cd_ratio=0.836, base_rate=0.0763, avg_interest_spread=0.0399,
        market_value_per_share=524.0, earnings_per_share=26.09,
        pe_ratio=20.08, net_worth_per_share=220.16,
        tier1_capital=54_000_000, tier2_capital=4_000_000,
        total_capital=58_000_000, ordinary_shares=270_569.97,
        cash_dividend_pct=0.11, bonus_pct=0.0,
        source="client_csv_shreyas", source_tier=SourceTier.CLIENT_AUTHORITATIVE,
        ingested_at=NOW,
    )
    assert ai.tier1_capital == 54_000_000
    assert AdditionalInfoSnapshot.model_validate_json(ai.model_dump_json()) == ai


def test_fundamental_metric_carries_source_tier():
    fm = FundamentalMetric(
        scrip="NABIL", fiscal_year_bs=2082, quarter=Quarter.Q2,
        metric_name="roe", value=14.93,
        source="client_csv_shreyas", source_tier=SourceTier.CLIENT_AUTHORITATIVE,
        ingested_at=NOW,
    )
    assert fm.source_tier == SourceTier.CLIENT_AUTHORITATIVE


def test_tool_response_generic_envelope():
    resp = ToolResponse[Quote](
        data=Quote(
            scrip="NABIL", close=528.0, change=-2.0,
            percent_change=-0.38, volume=39912,
            turnover=21109795.6, as_of=NOW,
        ),
        metadata=ToolMetadata(
            tool="get_quote", tool_version="1.0.0",
            data_as_of=NOW, sources=["silver.prices"],
            latency_ms=12,
        ),
    )
    assert resp.data.scrip == "NABIL"
    assert resp.metadata.tool == "get_quote"
    # JSON round-trip
    raw = resp.model_dump_json()
    assert '"scrip":"NABIL"' in raw
