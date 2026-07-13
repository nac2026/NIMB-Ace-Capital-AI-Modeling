"""SMTM floor-sheet incremental puller → bronze.floorsheet_raw.

Persists its cursor (last ingested contract_number) in the feed_cursors
Postgres table, so it resumes mid-day and across restarts. Each cycle fetches
only trades newer than the cursor and appends them to Bronze (Silver dedups on
contract_number). The Dagster floorsheet_job remains the authoritative EOD
reconcile; this keeps Bronze fresh intraday."""
from __future__ import annotations

import logging
import time

from nrc_ingestion import write_floorsheet_trades
from nrc_smtm import SMTMClient
from nrc_storage import PostgresClient, StorageSettings, get_settings

_log = logging.getLogger("nrc_marketfeed.floorsheet_puller")
_FEED = "floorsheet"


def _read_cursor(pg: PostgresClient) -> int | None:
    rows = pg.fetch_all("SELECT cursor FROM feed_cursors WHERE feed = %s", (_FEED,))
    if rows and rows[0]["cursor"]:
        try:
            return int(rows[0]["cursor"])
        except (TypeError, ValueError):
            return None
    return None


def _write_cursor(pg: PostgresClient, value: int) -> None:
    pg.execute(
        """
        INSERT INTO feed_cursors (feed, cursor, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (feed) DO UPDATE SET cursor = EXCLUDED.cursor, updated_at = NOW()
        """,
        (_FEED, str(value)),
    )


def run_floorsheet_puller(
    *,
    interval_s: float = 90.0,
    page_size: int = 500,
    client: SMTMClient | None = None,
    settings: StorageSettings | None = None,
    once: bool = False,
    respect_market_status: bool = True,
) -> None:
    """Pull new floor-sheet trades since the persisted cursor each interval."""
    settings = settings or get_settings()
    smtm = client or SMTMClient()
    smtm.login()
    pg = PostgresClient(settings)
    pg.open()
    _log.info("floorsheet_puller started (interval=%.0fs)", interval_s)
    try:
        while True:
            t0 = time.time()
            try:
                if respect_market_status and not smtm.market_status():
                    _log.debug("market closed — skipping floor-sheet pull")
                else:
                    cursor = _read_cursor(pg)
                    trades = smtm.fetch_new_trades(after_contract=cursor, page_size=page_size)
                    if trades:
                        report = write_floorsheet_trades(trades, settings=settings)
                        max_contract = max(t.contract_number for t in trades)
                        _write_cursor(pg, max_contract)
                        _log.info("%s (cursor→%d)", report.summary(), max_contract)
                    else:
                        _log.debug("no new trades since cursor")
            except Exception:  # noqa: BLE001 — never die on a transient error
                _log.exception("floor-sheet pull failed; will retry next interval")
            if once:
                return
            elapsed = time.time() - t0
            if elapsed < interval_s:
                time.sleep(interval_s - elapsed)
    finally:
        pg.close()
