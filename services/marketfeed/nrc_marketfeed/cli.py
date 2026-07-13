"""marketfeed CLI — run the live pollers.

  nrc-marketfeed quotes      # poll stock-live-v2 → /ingest/ticks
  nrc-marketfeed floorsheet  # incremental floor-sheet → bronze
  nrc-marketfeed quotes --once --no-market-gate   # one cycle (testing, off-hours)
"""
from __future__ import annotations

import logging

import typer

from .floorsheet_puller import run_floorsheet_puller
from .quote_poller import run_quote_poller

app = typer.Typer(help="Live NEPSE feed pollers (SMTM).", no_args_is_help=True)


@app.command()
def quotes(
    interval: float = typer.Option(30.0, help="Seconds between polls."),
    ingest_url: str = typer.Option("http://localhost:8080/ingest/ticks"),
    once: bool = typer.Option(False, help="Run a single cycle and exit."),
    market_gate: bool = typer.Option(True, help="Only poll when the market is live."),
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    run_quote_poller(interval_s=interval, ingest_url=ingest_url, once=once,
                     respect_market_status=market_gate)


@app.command()
def floorsheet(
    interval: float = typer.Option(90.0, help="Seconds between pulls."),
    page_size: int = typer.Option(500, help="Floor-sheet page size."),
    once: bool = typer.Option(False, help="Run a single cycle and exit."),
    market_gate: bool = typer.Option(True, help="Only pull when the market is live."),
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    run_floorsheet_puller(interval_s=interval, page_size=page_size, once=once,
                          respect_market_status=market_gate)


if __name__ == "__main__":
    app()
