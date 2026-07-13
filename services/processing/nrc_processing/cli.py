"""CLI entry for Silver + Postgres-sync transforms.

Gold transforms moved to dbt (see `<repo>/dbt/`). Run them with:
  cd dbt && dbt build                     # all Gold models + tests
  cd dbt && dbt run --select indicators_daily

Usage (this CLI — Silver only):
  uv run nrc-process scrip-master
  uv run nrc-process silver-all
  uv run nrc-process sync-postgres
"""
from __future__ import annotations
import typer

from .postgres_schema import apply_migrations
from .silver_additional_info import transform_additional_info
from .silver_closes import transform_closes
from .silver_corporate_actions import transform_corporate_actions
from .sync_postgres import sync_all as sync_postgres_all
from .silver_fundamentals import transform_fundamentals
from .silver_index import transform_index_snapshots
from .silver_news import transform_news
from .silver_prices import transform_prices
from .silver_scrip_master import transform_scrip_master

app = typer.Typer(add_completion=False, help="Bronze → Silver transforms + Postgres sync.")


@app.callback()
def _root() -> None:
    """Multi-command CLI; this callback keeps Typer from flattening single subcommand."""


@app.command("scrip-master")
def scrip_master_cmd(
    mode: str = typer.Option("overwrite", "--mode", "-m"),
) -> None:
    """Conform bronze.scrip_master_raw → silver.scrip_master."""
    report = transform_scrip_master(mode=mode)
    typer.echo(report.summary())
    for w in report.warnings[:5]:
        typer.echo(f"  warn: {w}")


@app.command("prices")
def prices_cmd(
    mode: str = typer.Option("overwrite", "--mode", "-m"),
    active_only: bool = typer.Option(True, "--active-only/--all-scrips"),
) -> None:
    """Conform bronze.prices_raw → silver.prices (DailyBar contract)."""
    report = transform_prices(mode=mode, active_only=active_only)
    typer.echo(report.summary())
    for w in report.warnings[:5]:
        typer.echo(f"  warn: {w}")


@app.command("closes")
def closes_cmd(
    mode: str = typer.Option("overwrite", "--mode", "-m"),
    active_only: bool = typer.Option(True, "--active-only/--all-scrips"),
) -> None:
    """Conform bronze.closes_raw → silver.closes (DailyClose contract — close-only)."""
    report = transform_closes(mode=mode, active_only=active_only)
    typer.echo(report.summary())
    for w in report.warnings[:5]:
        typer.echo(f"  warn: {w}")


@app.command("additional-info")
def additional_info_cmd(
    mode: str = typer.Option("overwrite", "--mode", "-m"),
    active_only: bool = typer.Option(True, "--active-only/--all-scrips"),
) -> None:
    """Conform bronze.additional_info_raw → silver.additional_info (Shreyas ratio block)."""
    report = transform_additional_info(mode=mode, active_only=active_only)
    typer.echo(report.summary())
    for w in report.warnings[:5]:
        typer.echo(f"  warn: {w}")


@app.command("corporate-actions")
def corporate_actions_cmd(
    mode: str = typer.Option("overwrite", "--mode", "-m"),
    active_only: bool = typer.Option(True, "--active-only/--all-scrips"),
) -> None:
    """Conform bronze.corporate_actions_raw → silver.corporate_actions."""
    report = transform_corporate_actions(mode=mode, active_only=active_only)
    typer.echo(report.summary())
    for w in report.warnings[:5]:
        typer.echo(f"  warn: {w}")


@app.command("fundamentals")
def fundamentals_cmd(
    mode: str = typer.Option("overwrite", "--mode", "-m"),
    active_only: bool = typer.Option(True, "--active-only/--all-scrips"),
) -> None:
    """Conform fundamentals into long + snapshots (wide) tables."""
    long_r, wide_r = transform_fundamentals(mode=mode, active_only=active_only)
    typer.echo(long_r.summary())
    typer.echo(wide_r.summary())
    for w in (long_r.warnings + wide_r.warnings)[:5]:
        typer.echo(f"  warn: {w}")


@app.command("news")
def news_cmd(
    mode: str = typer.Option("overwrite", "--mode", "-m"),
    active_only: bool = typer.Option(True, "--active-only/--all-scrips"),
) -> None:
    """Pivot bronze.news_raw → silver.news_articles (one row per URL)."""
    report = transform_news(mode=mode, active_only=active_only)
    typer.echo(report.summary())
    for w in report.warnings[:5]:
        typer.echo(f"  warn: {w}")


@app.command("index")
def index_cmd(
    mode: str = typer.Option("overwrite", "--mode", "-m"),
) -> None:
    """Conform bronze.index_history_raw → silver.index_snapshots."""
    report = transform_index_snapshots(mode=mode)
    typer.echo(report.summary())
    for w in report.warnings[:5]:
        typer.echo(f"  warn: {w}")


@app.command("silver-all")
def silver_all_cmd(
    mode: str = typer.Option("overwrite", "--mode", "-m"),
) -> None:
    """Run every Silver transform in dependency order."""
    typer.echo(transform_scrip_master(mode=mode).summary())
    typer.echo(transform_prices(mode=mode).summary())
    typer.echo(transform_closes(mode=mode).summary())
    typer.echo(transform_corporate_actions(mode=mode).summary())
    long_r, wide_r = transform_fundamentals(mode=mode)
    typer.echo(long_r.summary())
    typer.echo(wide_r.summary())
    typer.echo(transform_additional_info(mode=mode).summary())
    typer.echo(transform_news(mode=mode).summary())
    typer.echo(transform_index_snapshots(mode=mode).summary())


# Gold transforms (indicators, peer_rankings, stage1, stage2, valuation)
# moved to the dbt project — see <repo>/dbt/models/gold/. Run them via
# `dbt build` or `make dbt-run` / `make dbt-test` targets.


@app.command("apply-schema")
def apply_schema_cmd() -> None:
    """Apply pending Postgres schema migrations from infra/postgres/schema/."""
    applied = apply_migrations()
    if not applied:
        typer.echo("[postgres] schema already up to date")
    for v in applied:
        typer.echo(f"[postgres] applied {v}")


@app.command("sync-postgres")
def sync_postgres_cmd(
    days_of_bars: int = typer.Option(365, "--days-of-bars", help="How many recent days of daily_bars to keep."),
) -> None:
    """Sync lakehouse Gold/Silver → Postgres serving tables (TRUNCATE + COPY)."""
    reports = sync_postgres_all(days_of_bars=days_of_bars)
    for r in reports:
        typer.echo(r.summary())


if __name__ == "__main__":
    app()
