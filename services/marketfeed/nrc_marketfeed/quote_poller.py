"""SMTM live-quote poller → orchestrator /ingest/ticks.

Replaces the simulator's publisher with real SMTM data. One stock-live-v2 call
returns the whole market (~354 scrips), which we map to the orchestrator's
TickIngestRequest shape and POST as a single batch — reusing the existing
UPSERT live_quotes + tick_history + Redis pub/sub (which feeds the web SSE
stream). Gated on market-status so we don't spin when NEPSE is closed."""
from __future__ import annotations

import logging
import time

import httpx

from nrc_nepal import canonical_ticker
from nrc_smtm import SMTMClient

_log = logging.getLogger("nrc_marketfeed.quote_poller")
_DEFAULT_INGEST_URL = "http://localhost:8080/ingest/ticks"


def _to_tick(s) -> dict | None:
    if s.ltp is None or s.ltp <= 0 or not s.symbol:
        return None
    return {
        "scrip": canonical_ticker(s.symbol),
        "price": s.ltp,
        "open": s.open,
        "high": s.high,
        "low": s.low,
        "volume": int(s.volume) if s.volume is not None else 0,
        "turnover": s.turnover or 0.0,
        "change_abs": s.point_change,
        "change_pct": s.percentage_change,
        "prev_close": s.previous_closing,
        "source": "smtm",
    }


def _publish(ticks: list[dict], ingest_url: str) -> None:
    if not ticks:
        return
    for attempt in range(3):
        try:
            r = httpx.post(ingest_url, json=ticks, timeout=httpx.Timeout(10.0))
            r.raise_for_status()
            return
        except httpx.HTTPStatusError as exc:
            _log.error("ingest rejected status=%d body=%s",
                       exc.response.status_code, exc.response.text[:200])
            return
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            if attempt == 2:
                _log.warning("ingest unreachable after 3 attempts: %s", exc)


def run_quote_poller(
    *,
    interval_s: float = 30.0,
    ingest_url: str = _DEFAULT_INGEST_URL,
    client: SMTMClient | None = None,
    once: bool = False,
    respect_market_status: bool = True,
) -> None:
    """Poll stock-live-v2 every interval_s and publish ticks. Runs until killed."""
    smtm = client or SMTMClient()
    smtm.login()
    _log.info("quote_poller started (interval=%.0fs, ingest=%s)", interval_s, ingest_url)
    while True:
        t0 = time.time()
        try:
            if respect_market_status and not smtm.market_status():
                _log.debug("market closed — skipping poll")
            else:
                quotes = smtm.stock_live_v2()
                ticks = [t for t in (_to_tick(q) for q in quotes) if t]
                _publish(ticks, ingest_url)
                _log.info("published %d ticks", len(ticks))
        except Exception:  # noqa: BLE001 — poller must never die on a transient error
            _log.exception("quote poll failed; will retry next interval")
        if once:
            return
        elapsed = time.time() - t0
        if elapsed < interval_s:
            time.sleep(interval_s - elapsed)
