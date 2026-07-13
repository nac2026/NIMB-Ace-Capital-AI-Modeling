"""Bulk SMTM fundamentals ingest — every listed equity → serving `smtm_fundamentals`.

Loops the active equity universe (SMTM `company_list`, minus bonds/mutual funds),
pulls annual + quarterly key-stats for each and upserts every period. This is the
full-universe counterpart to the per-scrip on-demand `/api/scrip/{s}/financials`:
it materialises the whole market's key metrics so the platform can screen/rank
across all scrips at once (and serve fundamentals offline).

Heavier than the other refreshers (~2 calls/scrip, a few minutes for ~250
equities), so it runs on its own endpoint / schedule — NOT inline in the fast
`/refresh`. One SMTM session is reused across all scrips (token auto-refreshes).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from nrc_nepal import canonical_ticker
from nrc_smtm import SMTMClient
from nrc_storage import PostgresClient

_log = logging.getLogger("nrc_orchestrator.refresh_fundamentals")

# Sectors that aren't common equity — no meaningful key-stats to screen on.
_NON_EQUITY = ("bond", "mutual fund", "debenture")

_UPSERT = """
INSERT INTO smtm_fundamentals (
    scrip, frequency, fiscal_year, quarter, data_source,
    eps, pe, roe, roa, bvps, dps,
    total_revenue, net_income, net_income_margin, gross_profit_margin,
    market_cap, mps, npl, capital_adequacy, ingested_at, source
) VALUES (
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s, %s, %s, 'smtm'
)
ON CONFLICT (scrip, frequency, fiscal_year, quarter) DO UPDATE SET
    data_source = EXCLUDED.data_source,
    eps = EXCLUDED.eps, pe = EXCLUDED.pe, roe = EXCLUDED.roe, roa = EXCLUDED.roa,
    bvps = EXCLUDED.bvps, dps = EXCLUDED.dps,
    total_revenue = EXCLUDED.total_revenue, net_income = EXCLUDED.net_income,
    net_income_margin = EXCLUDED.net_income_margin,
    gross_profit_margin = EXCLUDED.gross_profit_margin,
    market_cap = EXCLUDED.market_cap, mps = EXCLUDED.mps,
    npl = EXCLUDED.npl, capital_adequacy = EXCLUDED.capital_adequacy,
    ingested_at = EXCLUDED.ingested_at
"""


def _equity_universe(client: SMTMClient) -> list[tuple[str, str]]:
    """Active, non-bond/MF equities as (raw_symbol, canonical_scrip) pairs.

    Union of two sources so nothing is missed: (1) SMTM `company_list` (the
    registry), and (2) `stock-live-v2` (the actively-traded market) — some listed
    equities appear only in one (e.g. NIC Asia's common share trades live but
    `company_list` carries only its bond / mutual-fund arms). We keep BOTH forms:
    SMTM's financials endpoint keys on the RAW symbol (e.g. `NICA`) while the rest
    of the platform keys on the canonical scrip (`NICASIA`) — so we fetch by raw
    and store by canonical. Non-equity sectors (bonds, mutual funds) are excluded;
    any straggler that slips through simply 404s and is reported as failed."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(symbol: str | None, sector: str | None) -> None:
        if not symbol:
            return
        if any(k in (sector or "").lower() for k in _NON_EQUITY):
            return
        scrip = canonical_ticker(symbol)
        if scrip and scrip not in seen:
            seen.add(scrip)
            out.append((symbol.strip().upper(), scrip))

    for c in client.company_list():
        if c.status == "A":
            _add(c.symbol, c.sector)
    for s in client.stock_live_v2():
        _add(s.symbol, s.sector)
    return out


def _rows_for(scrip: str, rows: list, frequency: str, now: datetime) -> list[tuple]:
    params: list[tuple] = []
    for r in rows:
        d = r.model_dump()
        year = d.get("year")
        if not year:
            continue
        params.append((
            scrip, frequency, year, int(d.get("quarter") or 0), d.get("data_source"),
            d.get("eps"), d.get("pe"), d.get("roe"), d.get("roa"),
            d.get("book_value_per_share"), d.get("dividend_per_share"),
            d.get("total_revenue"), d.get("net_income"), d.get("net_income_margin"),
            d.get("gross_profit_margin"), d.get("market_cap"), d.get("mps"),
            d.get("npl"), d.get("capital_adequacy"), now,
        ))
    return params


def refresh_smtm_fundamentals(
    pg: PostgresClient, *, limit: int | None = None, tickers: list[str] | None = None,
) -> dict:
    """Ingest annual + quarterly key-stats for every active equity into
    `smtm_fundamentals`. `tickers` restricts to an explicit list (top-up);
    otherwise the full equity universe is derived. `limit` caps the scrip count
    (testing). Returns a report dict ({scrips, with_data, empty, rows, failed})."""
    now = datetime.now(timezone.utc)
    scrips_done = with_data = empty = rows_written = 0
    failed: list[str] = []

    with SMTMClient() as c:
        # (raw_symbol, canonical_scrip): fetch by raw, store by canonical.
        if tickers:
            universe = [(t.strip().upper(), canonical_ticker(t)) for t in tickers]
        else:
            universe = _equity_universe(c)
        if limit:
            universe = universe[:limit]
        _log.info("bulk fundamentals: %d equities to ingest", len(universe))

        for i, (raw, scrip) in enumerate(universe, 1):
            try:
                annual = c.key_stats(raw, quarterly=False)
                quarterly = c.key_stats(raw, quarterly=True)
            except Exception as e:  # noqa: BLE001 — one bad scrip shouldn't kill the run
                _log.warning("fundamentals fetch failed for %s (raw=%s): %s", scrip, raw, e)
                failed.append(scrip)
                continue

            batch = _rows_for(scrip, annual, "annual", now) + \
                _rows_for(scrip, quarterly, "quarterly", now)
            for params in batch:
                pg.execute(_UPSERT, params)
            rows_written += len(batch)
            scrips_done += 1
            if batch:
                with_data += 1
            else:
                empty += 1
            if i % 25 == 0:
                _log.info("bulk fundamentals: %d/%d scrips, %d rows", i, len(universe), rows_written)

    report = {
        "scrips": scrips_done,
        "with_data": with_data,
        "empty": empty,
        "rows": rows_written,
        "failed": len(failed),
    }
    if failed:
        report["failed_scrips"] = failed[:20]
    _log.info("bulk fundamentals done: %s", report)
    return report
