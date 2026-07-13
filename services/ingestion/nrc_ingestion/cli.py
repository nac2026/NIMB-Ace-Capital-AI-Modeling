"""CLI entry for client-CSV ingestion — the default/primary Bronze path.

This CLI does NOT run scrapers. Scraping is an opt-in, manual operation —
use the separate `nrc-scrape` entry point when you need emergency backfill
or to validate against Sharesansar. Client-provided CSV dumps are the
authoritative source.

Usage:
  uv run nrc-ingest shreyas                       # Shreyas tidy CSVs → Bronze
  uv run nrc-ingest automation                    # Multi-sector tidy CSVs → Bronze
  uv run nrc-ingest format-b                      # Format B wide fundamentals
  uv run nrc-ingest format-b-prices               # Format B close-only prices
  uv run nrc-ingest all                           # Run all adapters
  uv run nrc-ingest all --input-dir /some/path   # Override OneDrive location
"""
from __future__ import annotations
from pathlib import Path

import typer

from .sources.client_csv import (
    ingest_client_csv_automation,
    ingest_client_csv_format_b_fundamentals,
    ingest_client_csv_format_b_prices,
    ingest_client_csv_shreyas,
)
from .sources.client_internal import ingest_client_internal_trades
from .sources.github_prices import ingest_github_nepse_prices

app = typer.Typer(
    add_completion=False,
    help="Client-CSV → Bronze ingestion (primary data path).",
)

# Default OneDrive location inside the client-docs sibling repo. Override
# via --input-dir on the command line or NRC_CLIENT_DOCS_DIR env if needed.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CLIENT_DIR = _REPO_ROOT.parent / "client-docs" / "OneDrive_1_4-24-2026"
_DEFAULT_SHREYAS = _DEFAULT_CLIENT_DIR / "CB Data by Shreyas"
_DEFAULT_AUTOMATION = _DEFAULT_CLIENT_DIR / "Data for Automation"
_DEFAULT_FORMAT_B = _DEFAULT_CLIENT_DIR / "Commercial bank"
_DEFAULT_FORMAT_B_PRICES = _DEFAULT_FORMAT_B / "Commercial bank Price 5 years"
# The firm's own trade-book dumps live in a sibling repo, not the OneDrive dump.
_DEFAULT_INTERNAL_TRADES = _REPO_ROOT.parent / "internal-trade-data"


@app.callback()
def _root() -> None:
    """Top-level callback keeps Typer in multi-command mode."""


@app.command("shreyas")
def shreyas_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_SHREYAS,
        "--input-dir", "-i",
        help="Directory containing the three cb*_*.csv files.",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Ingest Shreyas tidy CSVs → bronze.fundamentals_raw (long) + bronze.additional_info_raw (wide).

    Tagged CLIENT_AUTHORITATIVE — wins over any other source in Silver dedup."""
    reports = ingest_client_csv_shreyas(input_dir, mode=mode)
    for r in reports:
        typer.echo(r.summary())


@app.command("automation")
def automation_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_AUTOMATION,
        "--input-dir", "-i",
        help="Directory containing the per-sector '<SECTOR> {BS,IS,KS}.csv' files.",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Ingest the multi-sector 'Data for Automation' tidy CSVs → bronze.fundamentals_raw.

    Cross-sector key metrics for 10 sectors (banks, insurance, hydro, etc.).
    Tagged CLIENT_AUTHORITATIVE — wins over other sources in Silver dedup."""
    typer.echo(ingest_client_csv_automation(input_dir, mode=mode).summary())


@app.command("github-prices")
def github_prices_cmd(
    input_dir: Path = typer.Option(
        None,
        "--input-dir", "-i",
        help="Local dir of company-wise *.csv to ingest. Omit to download from GitHub.",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Backfill bronze.prices_raw from the Aabishkar2/nepse-data GitHub repo.

    Fallback / historical price source tagged SCRAPED — SMTM's live EOD feed
    always wins on overlapping days; this fills the deep history SMTM lacks.
    Covers ~7 sectors (banks, finance, hydro, investment, hotels, life ins).
    With no --input-dir it downloads the repo's company-wise CSVs first."""
    typer.echo(ingest_github_nepse_prices(input_dir, mode=mode).summary())


@app.command("format-b")
def format_b_fundamentals_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_FORMAT_B,
        "--input-dir", "-i",
        help="Root 'Commercial bank/' folder containing the three per-scrip subfolders.",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Ingest Format B wide per-scrip CSVs → bronze.fundamentals_raw.

    Tagged CLIENT_HISTORICAL — used for long-range backfill (2010/11→) but
    loses to Shreyas at Silver-merge time on any overlapping quarter."""
    report = ingest_client_csv_format_b_fundamentals(input_dir, mode=mode)
    typer.echo(report.summary())


@app.command("format-b-prices")
def format_b_prices_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_FORMAT_B_PRICES,
        "--input-dir", "-i",
        help="Directory containing per-scrip close-only CSVs (date, close).",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Ingest Format B close-only daily price CSVs → bronze.closes_raw.

    ~14 years of daily close history per scrip (2011-07-17 onwards). No OHLCV;
    candlestick-drawing tools should query silver.prices (scraper/live-API)
    separately."""
    report = ingest_client_csv_format_b_prices(input_dir, mode=mode)
    typer.echo(report.summary())


@app.command("internal-trades")
def internal_trades_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_INTERNAL_TRADES,
        "--input-dir", "-i",
        help="Directory of Trade_Book_Details *.xlsx dumps.",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Ingest the firm's trade-book xlsx dumps → bronze.internal_trades_raw.

    The firm's own executions (one fill per row). `contract_number` joins to
    silver.floorsheet downstream to recover broker/counterparty for surveillance.
    Tagged CLIENT_AUTHORITATIVE."""
    report = ingest_client_internal_trades(input_dir, mode=mode)
    typer.echo(report.summary())


@app.command("all")
def all_cmd(
    input_dir: Path = typer.Option(
        _DEFAULT_CLIENT_DIR,
        "--input-dir", "-i",
        help="Root OneDrive dump folder containing both 'CB Data by Shreyas' and 'Commercial bank' subfolders.",
    ),
    mode: str = typer.Option("overwrite", "--mode", "-m", help="Delta write mode."),
) -> None:
    """Run every client-CSV adapter against the default OneDrive layout.

    This is the full default Bronze refresh. Scraping is NOT included —
    invoke `nrc-scrape` separately if you need it."""
    shreyas_dir = input_dir / "CB Data by Shreyas"
    automation_dir = input_dir / "Data for Automation"
    format_b_dir = input_dir / "Commercial bank"
    format_b_prices_dir = format_b_dir / "Commercial bank Price 5 years"

    for r in ingest_client_csv_shreyas(shreyas_dir, mode=mode):
        typer.echo(r.summary())
    typer.echo(ingest_client_csv_automation(automation_dir, mode=mode).summary())
    typer.echo(ingest_client_csv_format_b_fundamentals(format_b_dir, mode=mode).summary())
    typer.echo(ingest_client_csv_format_b_prices(format_b_prices_dir, mode=mode).summary())


if __name__ == "__main__":
    app()
