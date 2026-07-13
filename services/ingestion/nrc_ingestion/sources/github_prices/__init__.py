"""GitHub community NEPSE price history — fallback / backfill source.

Pulls per-company daily OHLCV from the public `Aabishkar2/nepse-data` repo
(`data/company-wise/<TICKER>.csv`) into bronze.prices_raw. This is a stop-gap
historical backfill for the ~7 sectors it covers (commercial/development banks,
finance, hydro, investment, hotels, life insurance) until SMTM supplies full
history. Tagged source_tier='scraped' — the LOWEST tier — so SMTM's live EOD
feed always wins on any overlapping (scrip, date); this only fills the deep
history SMTM doesn't have yet.

Not covered by the repo (no company files): microfinance, non-life insurance,
manufacturing, trading, others."""
from __future__ import annotations

from .nepse_data import ingest_github_nepse_prices

__all__ = ["ingest_github_nepse_prices"]
