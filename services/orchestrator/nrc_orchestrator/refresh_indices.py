"""Live NEPSE index refresh — SMTM `indices-live` → serving `index_snapshots`.

Why this exists: the lakehouse `index_snapshots` was historically fed by the
retired Sharesansar **scraper** CSV (`bronze_scraper_index_history` → silver →
serving), which froze when we cut over to SMTM. SMTM exposes a live indices
endpoint (`indices_live()`), but it was never wired into ingestion — so the
dashboard's NEPSE/sub-index values + "As of" date stayed stuck at the last
scraper day while per-scrip prices kept updating.

This refresh fetches the live index values (NEPSE + ~16 sub-indices) plus the
market-summary turnover and upserts one snapshot row per index for the current
trading day directly into the serving table the dashboard reads. The live
endpoint only returns the latest value (no OHLC), so open/high/low/close are all
set to that value — sufficient for the dashboard's close/change/turnover use.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from nrc_smtm import SMTMClient
from nrc_storage import PostgresClient


def _parse_day(ts: str | None) -> date:
    if ts:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(ts[: len(fmt) + 2], fmt).date()
            except ValueError:
                continue
    return datetime.now(timezone.utc).astimezone().date()


def refresh_index_snapshots(pg: PostgresClient) -> dict:
    """Pull live indices from SMTM and upsert today's snapshot rows. Returns a
    small report dict ({rows, as_of, nepse})."""
    with SMTMClient() as c:
        c.login()
        indices = c.indices_live()
        turnover = None
        try:
            turnover = c.market_summary().total_turnover
        except Exception:  # market-summary is best-effort; indices are the point
            turnover = None

    now = datetime.now(timezone.utc)
    rows = 0
    as_of: date | None = None
    nepse_val: float | None = None
    for x in indices:
        val = x.latest_value
        if val is None:
            continue
        day = _parse_day(x.timestamp)
        as_of = max(as_of, day) if as_of else day
        is_nepse = x.indices_name.strip().upper() == "NEPSE"
        if is_nepse:
            nepse_val = val
        pg.execute(
            """
            INSERT INTO index_snapshots
                (index_name, date, open, high, low, close, turnover, change, percent_change, computed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (index_name, date) DO UPDATE SET
                close          = EXCLUDED.close,
                high           = GREATEST(index_snapshots.high, EXCLUDED.close),
                low            = LEAST(index_snapshots.low, EXCLUDED.close),
                turnover       = COALESCE(EXCLUDED.turnover, index_snapshots.turnover),
                change         = EXCLUDED.change,
                percent_change = EXCLUDED.percent_change,
                computed_at    = EXCLUDED.computed_at
            """,
            (
                x.indices_name.strip(),
                day,
                val, val, val, val,
                turnover if is_nepse else None,
                x.point_change,
                x.percentage_change,
                now,
            ),
        )
        rows += 1

    return {"rows": rows, "as_of": as_of.isoformat() if as_of else None, "nepse": nepse_val}
