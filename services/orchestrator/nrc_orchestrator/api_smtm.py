"""On-demand SMTM Data API passthrough — fundamentals + intraday/index timeseries.

These endpoints fetch live from SMTM per request (not from the lakehouse) and
cache in Redis, because the data is either deep-but-slow-moving (financials:
up to ~19 years of statements, refreshed quarterly) or inherently live (intraday
minute bars). They complement the CSV-sourced `fundamental_snapshots` (shallow
snapshots for ~233 scrips) with SMTM's full statement history for ANY ticker.

All handlers are sync `def` so FastAPI runs them in its threadpool; the SMTM
client is created per-request but a cache hit avoids the login+fetch entirely.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from nrc_smtm import SMTMClient, SMTMError

_log = logging.getLogger("nrc_orchestrator.api_smtm")

router = APIRouter(prefix="/api", tags=["smtm"])

# Cache TTLs (seconds): financials move quarterly; intraday/index are live.
_TTL_FINANCIALS = 6 * 3600
_TTL_INTRADAY = 60
_TTL_INDEX = 60

# Cross-sector key-stats fields the UI charts (snake_case = KeyStatsRow fields).
_KEY_STATS_FIELDS = (
    "eps", "pe", "roe", "roa", "book_value_per_share", "dividend_per_share",
    "total_revenue", "net_income", "net_income_margin", "gross_profit_margin",
    "market_cap", "mps", "npl", "capital_adequacy",
)


def _fy_key(row: dict) -> tuple:
    """Sort key for a financial period. `Year` is a fiscal label 'YYYY/YY' (or
    KeyStatsRow.year); leading 4 digits order it. Quarter breaks ties."""
    y = str(row.get("year") or row.get("Year") or "")
    q = row.get("quarter") or row.get("Quarter") or 0
    return (y[:4], y, q or 0)


def _key_stats_series(rows: list) -> list[dict]:
    """KeyStatsRow list → compact period dicts, oldest→newest for charting."""
    out = []
    for r in rows:
        d = r.model_dump()
        period = {
            "year": d.get("year"),
            "quarter": d.get("quarter"),
            "label": (f"{d.get('year')} Q{d.get('quarter')}"
                      if d.get("quarter") else d.get("year")),
            "data_source": d.get("data_source"),
        }
        for f in _KEY_STATS_FIELDS:
            period[f] = d.get(f)
        out.append(period)
    out.sort(key=_fy_key)
    return out


def _statement_slice(rows: list[dict], limit: int) -> list[dict]:
    """Latest `limit` statement periods (newest first), unchanged line items."""
    rows = sorted(rows, key=_fy_key, reverse=True)
    return rows[:limit]


# ============================================================ fundamentals

@router.get("/scrip/{scrip}/financials")
def scrip_financials(scrip: str, request: Request, statements: int = 6) -> dict:
    """Deep SMTM fundamentals for one ticker: annual + quarterly key-stats
    series (EPS, PE, ROE, ROA, BVPS, DPS, revenue, margins, NPL, CAR, MPS) plus
    the latest `statements` periods of the full income / balance / cash-flow
    statements. Cached ~6h. Works for any listed scrip, not just the 19 banks."""
    ticker = scrip.strip().upper()
    redis = request.app.state.redis
    cache_key = f"smtm:financials:{ticker}:{statements}"
    cached = redis.get_json(cache_key)
    if cached is not None:
        return cached

    def _safe(fn, label):
        """A single statement type missing (common — e.g. microfinances file no
        cash-flow) must not sink the whole response. Degrade that piece to []."""
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            _log.info("financials: %s unavailable for %s (%s)", label, ticker, str(e)[:80])
            return []

    try:
        with SMTMClient() as c:  # __enter__ logs in; a session failure 502s below
            annual_ks = _safe(lambda: c.key_stats(ticker, quarterly=False), "annual-key-stats")
            quarterly_ks = _safe(lambda: c.key_stats(ticker, quarterly=True), "quarterly-key-stats")
            income = _safe(lambda: c.income_statement(ticker, quarterly=False), "income")
            balance = _safe(lambda: c.balance_sheet(ticker, quarterly=False), "balance")
            cashflow = _safe(lambda: c.cash_flow(ticker), "cash-flow")
    except SMTMError as e:
        raise HTTPException(status_code=502, detail=f"SMTM unavailable: {e}") from e
    except Exception as e:  # noqa: BLE001 — login/session-level failure only
        _log.warning("financials session failed for %s: %s", ticker, e)
        raise HTTPException(status_code=502, detail="SMTM fetch failed") from e

    annual = _key_stats_series(annual_ks)
    quarterly = _key_stats_series(quarterly_ks)
    latest = quarterly[-1] if quarterly else (annual[-1] if annual else None)

    payload = {
        "scrip": ticker,
        "has_data": bool(annual or quarterly),
        "data_source": "smtm",
        "latest": latest,
        "annual": annual,
        "quarterly": quarterly[-16:],           # last ~4y of quarters for charts
        "statements": {
            "income": _statement_slice(income, statements),
            "balance": _statement_slice(balance, statements),
            "cashflow": _statement_slice(cashflow, statements),
        },
        "counts": {
            "annual": len(annual),
            "quarterly": len(quarterly),
            "income": len(income),
            "balance": len(balance),
            "cashflow": len(cashflow),
        },
    }
    redis.set_json(cache_key, payload, ttl_seconds=_TTL_FINANCIALS)
    return payload


# ============================================================ timeseries

@router.get("/scrip/{scrip}/intraday")
def scrip_intraday(scrip: str, request: Request) -> dict:
    """Intraday minute bars for the CURRENT session (SMTM stock-timeseries).
    Returned oldest→newest for direct charting. Cached ~60s."""
    ticker = scrip.strip().upper()
    redis = request.app.state.redis
    cache_key = f"smtm:intraday:{ticker}"
    cached = redis.get_json(cache_key)
    if cached is not None:
        return cached

    try:
        with SMTMClient() as c:
            points = c.stock_timeseries(ticker)
    except Exception as e:  # noqa: BLE001
        _log.warning("intraday fetch failed for %s: %s", ticker, e)
        raise HTTPException(status_code=502, detail="SMTM fetch failed") from e

    series = [
        {"t": p.timestamp, "price": p.closing_price, "volume": p.volume, "amount": p.amount}
        for p in points if p.closing_price is not None
    ]
    series.sort(key=lambda r: r["t"])
    payload = {"scrip": ticker, "points": len(series), "series": series}
    redis.set_json(cache_key, payload, ttl_seconds=_TTL_INTRADAY)
    return payload


@router.get("/fundamentals/screen")
def fundamentals_screen(
    request: Request,
    frequency: str = "annual",
    min_roe: float | None = None,
    max_pe: float | None = None,
    max_npl: float | None = None,
    min_eps: float | None = None,
    sector: str | None = None,
    limit: int = 500,
) -> dict:
    """Cross-universe fundamentals screen over the bulk-ingested
    `smtm_fundamentals` — the LATEST period per scrip, with optional filters
    (min_roe / max_pe / max_npl / min_eps as fractions or raw; sector). Powered
    by refresh_smtm_fundamentals; returns [] until that bulk ingest has run."""
    pg = request.app.state.pg
    freq = "quarterly" if frequency.lower().startswith("q") else "annual"

    where = ["f.frequency = %s"]
    params: list = [freq]
    if min_roe is not None:
        where.append("f.roe >= %s"); params.append(min_roe)
    if max_pe is not None:
        where.append("f.pe > 0 AND f.pe <= %s"); params.append(max_pe)
    if max_npl is not None:
        where.append("(f.npl IS NULL OR f.npl <= %s)"); params.append(max_npl)
    if min_eps is not None:
        where.append("f.eps >= %s"); params.append(min_eps)
    if sector:
        where.append("s.sector = %s"); params.append(sector)
    params.append(limit)

    # latest period per scrip via DISTINCT ON, then apply the metric filters
    sql = f"""
        WITH latest AS (
            SELECT DISTINCT ON (scrip) *
            FROM smtm_fundamentals
            WHERE frequency = %s
            ORDER BY scrip, fiscal_year DESC, quarter DESC
        )
        SELECT f.scrip, s.company_name, s.sector, f.fiscal_year, f.quarter,
               f.data_source, f.eps, f.pe, f.roe, f.roa, f.bvps, f.dps,
               f.net_income, f.market_cap, f.mps, f.npl, f.capital_adequacy
        FROM latest f
        LEFT JOIN scrips s ON s.scrip = f.scrip
        WHERE {' AND '.join(where)}
        ORDER BY f.roe DESC NULLS LAST
        LIMIT %s
    """
    # note: first %s (CTE) consumes freq; `where`/limit params follow in order
    rows = pg.fetch_all(sql, [freq, *params])
    return {"frequency": freq, "count": len(rows), "results": rows}


@router.get("/index/{slug}/timeseries")
def index_timeseries(slug: str, request: Request) -> dict:
    """Index value/turnover timeseries for `slug` (e.g. 'nepse'), oldest→newest.
    Cached ~60s."""
    key = slug.strip().lower()
    redis = request.app.state.redis
    cache_key = f"smtm:index-ts:{key}"
    cached = redis.get_json(cache_key)
    if cached is not None:
        return cached

    try:
        with SMTMClient() as c:
            points = c.indices_timeseries(key)
    except Exception as e:  # noqa: BLE001
        _log.warning("index timeseries fetch failed for %s: %s", key, e)
        raise HTTPException(status_code=502, detail="SMTM fetch failed") from e

    series = [
        {"t": p.timestamp, "value": p.value, "turnover": p.turnover}
        for p in points if p.value is not None
    ]
    series.sort(key=lambda r: r["t"])
    name = points[0].indices_name if points else key.upper()
    payload = {"slug": key, "name": name, "points": len(series), "series": series}
    redis.set_json(cache_key, payload, ttl_seconds=_TTL_INDEX)
    return payload
