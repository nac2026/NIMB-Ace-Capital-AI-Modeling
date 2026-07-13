"""Broker position timeline + phase summary.

Adds the temporal trajectory that `broker_accumulation` (a single cumulative
aggregate) lacks: the running cumulative net position per (scrip, broker) over
the loaded floor-sheet days, and a derived phase summary — when accumulation
started, when the position peaked, and when the broker flipped to distributing.

Computed directly in Postgres from the already-synced `broker_flow_daily`
serving table (no dbt run; survives Gold→Postgres syncs since the two target
tables aren't lakehouse-synced). Bounded to material brokers (volume_share ≥ 5%)
so the timeline table stays small."""
from __future__ import annotations

import logging

from nrc_storage import PostgresClient

_log = logging.getLogger("nrc_processing.broker_positions")

_MIN_SHARE = 0.05  # only track brokers with >=5% of a scrip's volume


def refresh_broker_positions(pg: PostgresClient | None = None) -> dict:
    """Rebuild broker_position_timeline + broker_position from broker_flow_daily."""
    pg = pg or PostgresClient()
    # 1) running cumulative position per (scrip, broker, day), material brokers only.
    pg.execute("TRUNCATE broker_position_timeline")
    pg.execute(
        """
        INSERT INTO broker_position_timeline (scrip, broker, trade_date, daily_net_qty, cum_net_qty, computed_at)
        SELECT f.scrip, f.broker, f.trade_date, f.net_qty,
               SUM(f.net_qty) OVER (PARTITION BY f.scrip, f.broker ORDER BY f.trade_date
                                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
               now()
        FROM broker_flow_daily f
        JOIN broker_accumulation ba ON ba.scrip = f.scrip AND ba.broker = f.broker
        WHERE COALESCE(ba.volume_share, 0) >= %s
        """,
        (_MIN_SHARE,),
    )

    # 2) phase summary from the timeline.
    pg.execute("TRUNCATE broker_position")
    pg.execute(
        """
        WITH tl AS (SELECT scrip, broker, trade_date, daily_net_qty, cum_net_qty FROM broker_position_timeline),
        peak AS (
            SELECT DISTINCT ON (scrip, broker) scrip, broker, trade_date AS peak_date, cum_net_qty AS peak_cum_qty
            FROM tl ORDER BY scrip, broker, cum_net_qty DESC, trade_date ASC
        ),
        last AS (
            SELECT DISTINCT ON (scrip, broker) scrip, broker, trade_date AS last_day, cum_net_qty AS last_cum
            FROM tl ORDER BY scrip, broker, trade_date DESC
        ),
        astart AS (
            SELECT scrip, broker, min(trade_date) AS accum_start_date
            FROM tl WHERE daily_net_qty > 0 GROUP BY scrip, broker
        ),
        dstart AS (
            SELECT t.scrip, t.broker, min(t.trade_date) AS dist_start_date
            FROM tl t JOIN peak p USING (scrip, broker)
            WHERE t.trade_date > p.peak_date AND t.daily_net_qty < 0
            GROUP BY t.scrip, t.broker
        )
        INSERT INTO broker_position
            (scrip, broker, phase, accum_start_date, peak_date, peak_cum_qty, dist_start_date, days_since_peak, cum_net_qty, computed_at)
        SELECT p.scrip, p.broker,
               CASE
                   WHEN d.dist_start_date IS NOT NULL AND l.last_cum < p.peak_cum_qty * 0.95 THEN 'distributing'
                   WHEN l.last_cum > 0 THEN 'accumulating'
                   ELSE 'flat'
               END,
               a.accum_start_date, p.peak_date, p.peak_cum_qty, d.dist_start_date,
               (l.last_day - p.peak_date), l.last_cum, now()
        FROM peak p
        JOIN last l USING (scrip, broker)
        LEFT JOIN astart a USING (scrip, broker)
        LEFT JOIN dstart d USING (scrip, broker)
        """
    )
    n_tl = (pg.fetch_one("SELECT count(*) c FROM broker_position_timeline") or {}).get("c", 0)
    n_pos = (pg.fetch_one("SELECT count(*) c FROM broker_position") or {}).get("c", 0)
    _log.info("broker positions refreshed: timeline=%s positions=%s", n_tl, n_pos)
    return {"timeline_rows": n_tl, "position_rows": n_pos}
