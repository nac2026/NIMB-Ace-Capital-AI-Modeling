"""CLI entry for scraper-backed Bronze ingestion — manual, opt-in only.

Scraping is the fallback data path. Client-provided CSV dumps are the
primary/authoritative source (see `nrc-ingest`). This CLI is kept
available for:

  * Emergency backfill when the client hasn't sent an updated CSV yet.
  * Cross-validation against a second source.
  * Pulling data outside the commercial-bank universe the client covers.

**This CLI is NEVER invoked automatically.** It has no Prefect task
wrapper in the default daily_eod flow, no cron schedule, no hook. Run
it manually when you actually need it:

  uv run nrc-scrape prices
  uv run nrc-scrape fundamentals
  uv run nrc-scrape all           # all six scraper-backed ingests

Rows written by this path are tagged `source_tier='scraped'` — they lose
to any client_* tier row covering the same (scrip, fy, quarter, metric)
key in Silver-layer dedup.
"""
from __future__ import annotations
from pathlib import Path

import typer

from .bronze_corporate_actions import ingest_corporate_actions
from .bronze_fundamentals import ingest_fundamentals
from .bronze_index_history import ingest_index_history
from .bronze_news import ingest_news
from .bronze_prices import ingest_prices
from .bronze_scrip_master import ingest_scrip_master

app = typer.Typer(
    add_completion=False,
    help="Sharesansar scraper → Bronze. Manual / fallback use only.",
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SCRAPE_DIR = _REPO_ROOT / "scrapers" / "output"


@app.callback()
def _root() -> None:
    """Top-level callback keeps Typer in multi-command mode."""


@app.command("prices")
def prices_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_SCRAPE_DIR / "prices",
        "--input-dir", "-i",
        help="Directory containing per-scrip price CSVs.",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Ingest scraped OHLCV CSVs into bronze.prices_raw."""
    typer.echo(ingest_prices(input_dir, mode=mode).summary())


@app.command("corporate-actions")
def corporate_actions_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_SCRAPE_DIR / "dividends",
        "--input-dir", "-i",
        help="Directory containing *_dividends.csv and *_rights.csv.",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Ingest scraped dividends + rights into bronze.corporate_actions_raw."""
    typer.echo(ingest_corporate_actions(input_dir, mode=mode).summary())


@app.command("fundamentals")
def fundamentals_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_SCRAPE_DIR / "fundamentals",
        "--input-dir", "-i",
        help="Directory containing *_fundamentals_long.csv files.",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Ingest scraped per-scrip fundamentals into bronze.fundamentals_raw.

    Tagged source_tier='scraped' — loses to any client_* tier row in Silver."""
    typer.echo(ingest_fundamentals(input_dir, mode=mode).summary())


@app.command("news")
def news_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_SCRAPE_DIR / "news",
        "--input-dir", "-i",
        help="Directory containing *_news_index.csv files.",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Ingest scraped per-scrip news indices into bronze.news_raw."""
    typer.echo(ingest_news(input_dir, mode=mode).summary())


@app.command("scrip-master")
def scrip_master_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_SCRAPE_DIR / "company_info",
        "--input-dir", "-i",
        help="Directory containing scrip_master.csv.",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Ingest scrip_master.csv into bronze.scrip_master_raw."""
    typer.echo(ingest_scrip_master(input_dir, mode=mode).summary())


@app.command("index-history")
def index_history_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_SCRAPE_DIR / "index",
        "--input-dir", "-i",
        help="Directory containing *_history.csv files (NEPSE, BANKING, ...).",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Ingest NEPSE + sector index daily history into bronze.index_history_raw."""
    typer.echo(ingest_index_history(input_dir, mode=mode).summary())


@app.command("all")
def all_cmd(
    scrape_dir: Path = typer.Option(
        _DEFAULT_SCRAPE_DIR,
        "--scrape-dir", "-d",
        help="Root scraper output directory (contains prices/, fundamentals/, news/, etc.).",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Run every scraper-backed Bronze ingest.

    Equivalent of the old `nrc-ingest all` before the client-first refactor.
    Use this only when the client CSV dumps are unavailable or stale."""
    for fn, sub in [
        (ingest_scrip_master, "company_info"),
        (ingest_prices, "prices"),
        (ingest_corporate_actions, "dividends"),
        (ingest_fundamentals, "fundamentals"),
        (ingest_news, "news"),
        (ingest_index_history, "index"),
    ]:
        typer.echo(fn(scrape_dir / sub, mode=mode).summary())


if __name__ == "__main__":
    app()
