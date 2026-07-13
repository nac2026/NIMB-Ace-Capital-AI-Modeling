"""CLI entry point for the market simulator.

Usage:
    nrc-simulate --scrips NABIL,EBL,NIMB
    nrc-simulate --scrips NABIL --speed 1 --date 2024-01-15
    nrc-simulate --all-banks  # simulate all 19 commercial banks

Each tick round: every listed scrip emits one tick, then the loop sleeps
for `speed` seconds. Press Ctrl-C to stop.
"""
from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import date

import typer

from nrc_storage import PostgresClient

from .engine import load_seed_data
from .publisher import publish_batch

app = typer.Typer(help="NEPSE market tick simulator")

_COMMERCIAL_BANKS = [
    "NABIL", "EBL", "SCB", "NIMB", "GBIME", "KBL", "MBL", "PCBL",
    "SBI", "SBL", "ADBL", "NBB", "CBL", "NBL", "PRVU", "NICA",
    "SANIMA", "MEGA", "CITIZENS",
]

_log = logging.getLogger("nrc_simulator.cli")
_running = True


def _sigint(_sig, _frame):
    global _running
    _running = False


@app.command()
def simulate(
    scrips: str = typer.Option(
        "",
        "--scrips",
        help="Comma-separated scrip symbols. Overrides --all-banks.",
    ),
    all_banks: bool = typer.Option(
        False,
        "--all-banks",
        help="Simulate all 19 commercial banks.",
    ),
    speed: float = typer.Option(
        2.0,
        "--speed",
        help="Seconds between tick rounds (one tick per scrip per round).",
        min=0.1,
    ),
    trade_date: str = typer.Option(
        "",
        "--date",
        help="Seed from this trading date (YYYY-MM-DD). Defaults to latest available.",
    ),
    ingest_url: str = typer.Option(
        "http://localhost:8080/ingest/ticks",
        "--ingest-url",
        help="Orchestrator batch ingest endpoint URL.",
    ),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    if scrips:
        target_scrips = [s.strip().upper() for s in scrips.split(",") if s.strip()]
    elif all_banks:
        target_scrips = list(_COMMERCIAL_BANKS)
    else:
        typer.echo("Provide --scrips or --all-banks", err=True)
        raise typer.Exit(1)

    seed_date: date | None = date.fromisoformat(trade_date) if trade_date else None

    _log.info("loading seed data for %d scrips from daily_bars...", len(target_scrips))
    pg = PostgresClient()
    states = load_seed_data(target_scrips, pg=pg, trade_date=seed_date)
    _log.info("loaded %d scrips — starting simulation at %.1fs per round", len(states), speed)
    for s in states:
        _log.info("  %s  seed price=%.2f  H=%.2f  L=%.2f", s.scrip, s.price, s.high, s.low)

    signal.signal(signal.SIGINT, _sigint)
    signal.signal(signal.SIGTERM, _sigint)

    tick_count = 0
    try:
        while _running:
            batch: list[dict] = []
            for state in states:
                if not _running:
                    break
                state.step()
                batch.append(state.to_tick_dict())

            if batch:
                publish_batch(batch, ingest_url=ingest_url)
                tick_count += len(batch)

            if _running:
                time.sleep(speed)

    except KeyboardInterrupt:
        pass
    finally:
        _log.info("simulator stopped — %d ticks published", tick_count)
        sys.exit(0)
