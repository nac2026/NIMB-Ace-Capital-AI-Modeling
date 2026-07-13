"""Integration tests for the research tool layer.

Hits the live Postgres serving layer. Skipped if Postgres is down."""
from __future__ import annotations
import socket
from urllib.parse import urlparse

import pytest

from nrc_contracts import ToolResponse
from nrc_storage import StorageSettings
from nrc_tools import (
    REGISTRY,
    ToolError,
    get_corporate_actions,
    get_fundamentals,
    get_news,
    get_peer_rankings,
    get_quote,
    get_technicals,
    get_valuation,
    list_scrips,
    stage1_screen,
    stage2_bank_screen,
    tool_specs,
)


def _pg_up() -> bool:
    url = StorageSettings().postgres_url
    u = urlparse(url)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((u.hostname or "localhost", u.port or 5432))
            return True
        except OSError:
            return False


pytestmark = pytest.mark.skipif(not _pg_up(), reason="Postgres not running")


# ------------------------------------------------------------ tool registry
def test_registry_has_all_tools():
    assert len(REGISTRY) == 10
    for name in [
        "get_quote", "get_fundamentals", "get_technicals", "get_corporate_actions",
        "get_valuation", "stage1_screen", "stage2_bank_screen",
        "get_peer_rankings", "get_news", "list_scrips",
    ]:
        assert name in REGISTRY


def test_tool_specs_have_required_fields():
    for spec in tool_specs():
        assert "name" in spec
        assert "description" in spec
        assert "input_schema" in spec
        assert spec["input_schema"]["type"] == "object"


# ---------------------------------------------------------------- get_quote
def test_get_quote_returns_envelope():
    r = get_quote("NABIL")
    assert isinstance(r, ToolResponse)
    assert r.data.scrip == "NABIL"
    assert r.data.close > 0
    assert r.metadata.tool == "get_quote"
    assert r.metadata.tool_version
    assert "postgres.daily_bars" in r.metadata.sources


def test_get_quote_canonicalizes_scrip():
    """Lowercased/padded scrip should resolve — scrip field canonicalizes upstream."""
    r = get_quote("  nabil  ")
    assert r.data.scrip == "NABIL"


def test_get_quote_unknown_scrip_raises():
    with pytest.raises(ToolError) as excinfo:
        get_quote("NOTASCRIP")
    assert excinfo.value.reason == "not_found"


# ---------------------------------------------------------- get_fundamentals
def test_get_fundamentals_defaults_to_latest():
    r = get_fundamentals("NABIL")
    assert r.data.scrip == "NABIL"
    assert r.data.fiscal_year_bs >= 2080
    assert r.data.roe is not None


def test_get_fundamentals_specific_quarter():
    r = get_fundamentals("NABIL", fiscal_year_bs=2082, quarter=2)
    assert r.data.fiscal_year_bs == 2082
    assert r.data.quarter.value == 2
    assert r.data.roe == pytest.approx(14.93, rel=1e-3)


# ----------------------------------------------------------- get_technicals
def test_get_technicals_returns_indicators():
    r = get_technicals("NABIL")
    assert r.data.close > 0
    assert r.data.sma_20 is not None
    assert 0 <= r.data.rsi_14 <= 100


# ------------------------------------------------------ get_corporate_actions
def test_corp_actions_nabil_has_dividends():
    r = get_corporate_actions("NABIL", limit=5)
    assert len(r.data) > 0
    assert any(a.action_type.value == "cash_dividend" for a in r.data)


# ------------------------------------------------------------- get_valuation
def test_get_valuation_has_peer_comparison():
    r = get_valuation("NABIL")
    assert r.data.pe_trailing is not None
    assert r.data.peer_pe_median is not None
    assert r.data.pe_vs_peer_pct is not None


# ---------------------------------------------------------- screens & ranks
def test_stage1_screen_passed_only():
    r = stage1_screen(passed_only=True)
    assert all(res.passed for res in r.data)
    assert len(r.data) > 0


def test_stage2_bank_screen_nabil_has_composite():
    r = stage2_bank_screen(scrip="NABIL")
    assert len(r.data) >= 1
    latest = r.data[0]
    assert latest.sector == "Commercial Bank"
    assert 0 <= latest.composite_score <= 1


def test_stage2_screen_covers_non_bank_sector():
    # Sector filter works and non-BFI sectors are now screened (NPL/CAR/CD null).
    r = stage2_bank_screen(sector="Hydro Power")
    assert len(r.data) > 0
    top = r.data[0]
    assert top.sector == "Hydro Power"
    assert top.npl_ratio is None and top.car is None and top.cd_ratio is None
    assert 0 <= top.composite_score <= 1


def test_peer_rankings_nabil_on_roe():
    r = get_peer_rankings("NABIL", metric="roe")
    top = r.data[0]
    assert 1 <= top.rank_in_sector <= 19
    assert 0 <= top.percentile_in_sector <= 1


def test_peer_rankings_bad_metric_raises():
    with pytest.raises(ToolError) as excinfo:
        get_peer_rankings("NABIL", metric="not_a_metric")
    assert excinfo.value.reason == "bad_input"


# ------------------------------------------------------------------- news
def test_get_news_by_scrip():
    r = get_news(scrip="NABIL", limit=3)
    assert len(r.data) <= 3
    assert all("NABIL" in a.scrip_tags for a in r.data)


def test_get_news_keyword_search():
    r = get_news(search="interest rate", limit=5)
    assert len(r.data) > 0
    assert all("interest rate" in a.title.lower() for a in r.data)


# ------------------------------------------------------------- list_scrips
def test_list_scrips_active_default():
    r = list_scrips()
    assert len(r.data) == 19
    assert all(s.is_active for s in r.data)


def test_list_scrips_by_sector():
    r = list_scrips(sector="Commercial Bank", active_only=False)
    assert len(r.data) == 29  # 19 active + 10 merged
