"""Client-provided CSV dump adapters.

Two formats coexist in the same OneDrive folder:

  * **Shreyas tidy format** (`CB Data by Shreyas/*.csv`) — one row per
    (ticker, year, quarter), 2020/21→present, cleanest. Tagged
    `CLIENT_AUTHORITATIVE` — highest precedence.
  * **Format B wide-pivoted** (`Commercial bank/.../<TICKER>.csv`) — year/
    quarter as columns, covers 2010/11→present, needed for long-range
    historical backfill but less consistent. Tagged `CLIENT_HISTORICAL`.

Both feed into the same Bronze tables; Silver-layer dedup with
`source_tier` precedence picks Shreyas over Format B when the same
(scrip, fy, quarter, metric) key is covered by both."""
from __future__ import annotations

from .automation_fundamentals import ingest_client_csv_automation
from .format_b_fundamentals import ingest_client_csv_format_b_fundamentals
from .format_b_prices import ingest_client_csv_format_b_prices
from .shreyas_fundamentals import ingest_client_csv_shreyas

__all__ = [
    "ingest_client_csv_shreyas",
    "ingest_client_csv_automation",
    "ingest_client_csv_format_b_fundamentals",
    "ingest_client_csv_format_b_prices",
]
