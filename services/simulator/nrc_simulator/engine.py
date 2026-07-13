"""Tick generation engine.

For each scrip, seeds from that day's daily_bars row (open/high/low/close).
Generates a bounded Geometric Brownian Motion walk constrained to the
observed H/L range. Each call to next_tick() advances the walk by one step.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from nrc_storage import PostgresClient


@dataclass
class ScripState:
    scrip: str
    price: float
    open_: float
    high: float
    low: float
    close: float
    volume: int
    prev_close: float | None

    # Running intraday high/low for the simulated session
    session_high: float = field(init=False)
    session_low: float = field(init=False)
    session_volume: int = field(default=0, init=False)

    def __post_init__(self):
        self.session_high = self.price
        self.session_low = self.price

    def step(self, sigma: float = 0.002) -> None:
        """Advance price by one GBM step, clamped to the seed day's H/L range."""
        drift = 0.0
        shock = random.gauss(0, sigma)
        self.price *= math.exp(drift + shock)
        self.price = max(self.low, min(self.high, self.price))
        # Simulate a small burst of volume on each tick
        self.session_volume += max(1, int(random.expovariate(1.0 / max(1, self.volume // 200))))
        self.session_high = max(self.session_high, self.price)
        self.session_low = min(self.session_low, self.price)

    def to_tick_dict(self) -> dict:
        change_abs = round(self.price - self.prev_close, 2) if self.prev_close else None
        change_pct = round(change_abs / self.prev_close * 100, 4) if self.prev_close and change_abs is not None else None
        turnover = round(self.price * self.session_volume, 2)
        return {
            "scrip": self.scrip,
            "price": round(self.price, 2),
            "open": round(self.open_, 2),
            "high": round(self.session_high, 2),
            "low": round(self.session_low, 2),
            "volume": self.session_volume,
            "turnover": turnover,
            "change_abs": change_abs,
            "change_pct": change_pct,
            "prev_close": self.prev_close,
            "source": "simulator",
        }


def load_seed_data(
    scrips: list[str],
    *,
    pg: PostgresClient,
    trade_date: date | None = None,
) -> list[ScripState]:
    """Load the most recent (or specified) daily_bars row for each scrip as seed data."""
    ph = ", ".join(["%s"] * len(scrips))
    date_filter = "AND date = %s" if trade_date else ""
    params: tuple = tuple(scrips) + ((trade_date,) if trade_date else ())

    rows = pg.fetch_all(
        f"""
        WITH ranked AS (
            SELECT
                scrip, date, open, high, low, close, volume,
                LAG(close) OVER (PARTITION BY scrip ORDER BY date) AS prev_close,
                ROW_NUMBER() OVER (PARTITION BY scrip ORDER BY date DESC) AS rn
            FROM daily_bars
            WHERE scrip IN ({ph}) {date_filter}
        )
        SELECT scrip, date, open, high, low, close, volume, prev_close
        FROM ranked
        WHERE rn = 1
        ORDER BY scrip
        """,
        params,
    )

    if not rows:
        raise ValueError(f"No daily_bars data found for scrips: {scrips}")

    states = []
    for row in rows:
        # Start at open price, walk toward close direction
        states.append(ScripState(
            scrip=row["scrip"],
            price=float(row["open"]),
            open_=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]),
            prev_close=float(row["prev_close"]) if row["prev_close"] else None,
        ))

    return states
