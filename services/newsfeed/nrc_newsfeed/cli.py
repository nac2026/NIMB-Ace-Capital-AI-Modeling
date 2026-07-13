"""newsfeed CLI.

  nrc-newsfeed run          # continuous loop (every newsfeed_interval_s)
  nrc-newsfeed run --once   # a single fetch→enrich→store→rollup cycle
"""
from __future__ import annotations

import logging

import typer

from .pipeline import run_newsfeed

app = typer.Typer(help="Live NEPSE news ingestion + sentiment.", no_args_is_help=True)


@app.command()
def run(once: bool = typer.Option(False, help="Run a single cycle and exit.")) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    run_newsfeed(once=once)


if __name__ == "__main__":
    app()
