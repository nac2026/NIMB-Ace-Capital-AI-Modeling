"""End-to-end test of Silver-layer source-tier precedence.

Two sources (client_csv_shreyas, client_csv_format_b) both cover many of
the same (scrip, fy, quarter, metric) keys. When they conflict, Silver's
QUALIFY ROW_NUMBER() dedup must pick CLIENT_AUTHORITATIVE (Shreyas) over
CLIENT_HISTORICAL (Format B).

Skipped if MinIO isn't reachable."""
from __future__ import annotations
import socket
from pathlib import Path
from urllib.parse import urlparse

import pytest

from nrc_compute import DuckDBEngine
from nrc_ingestion import (
    ingest_client_csv_format_b_fundamentals,
    ingest_client_csv_format_b_prices,
    ingest_client_csv_shreyas,
    ingest_scrip_master,
)
from nrc_processing import (
    transform_additional_info,
    transform_closes,
    transform_fundamentals,
    transform_scrip_master,
)
from nrc_storage import MinIOClient, StorageSettings


def _minio_up(url: str) -> bool:
    u = urlparse(url)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((u.hostname or "localhost", u.port or 9000))
            return True
        except OSError:
            return False


_SETTINGS = StorageSettings()
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLIENT_DIR = _REPO_ROOT.parent / "client-docs" / "OneDrive_1_4-24-2026"
_SCRAPER_CI_DIR = _REPO_ROOT / "scrapers" / "output" / "company_info"

pytestmark = [
    pytest.mark.skipif(not _minio_up(_SETTINGS.minio_endpoint), reason="MinIO not running"),
    pytest.mark.skipif(not _CLIENT_DIR.exists(), reason="client-docs OneDrive fixture missing"),
    pytest.mark.skipif(not _SCRAPER_CI_DIR.exists(), reason="scrapers/output/company_info missing"),
]


@pytest.fixture(scope="module")
def pipeline_run():
    """Bronze + Silver + supporting scrip_master in a single pass. Run once per
    module since this is an expensive end-to-end fixture."""
    MinIOClient(_SETTINGS, bucket=_SETTINGS.minio_bucket_lakehouse).ensure_bucket()

    # One-time scrip master from the Sharesansar scrape (canonicalized in Silver).
    ingest_scrip_master(_SCRAPER_CI_DIR, mode="overwrite")

    # Both client sources — landed in the same Bronze table, partition-isolated
    # by source tag so Shreyas and Format B coexist.
    ingest_client_csv_shreyas(_CLIENT_DIR / "CB Data by Shreyas", mode="overwrite")
    ingest_client_csv_format_b_fundamentals(_CLIENT_DIR / "Commercial bank", mode="overwrite")
    ingest_client_csv_format_b_prices(
        _CLIENT_DIR / "Commercial bank" / "Commercial bank Price 5 years", mode="overwrite"
    )

    # Transform to Silver.
    transform_scrip_master()
    transform_fundamentals()
    transform_additional_info()
    transform_closes()
    return True


def test_bronze_contains_both_client_sources(pipeline_run):
    """Both CLIENT_AUTHORITATIVE and CLIENT_HISTORICAL rows must coexist
    in bronze.fundamentals_raw after ingest. The partition-aware upsert
    guarantees neither overwrote the other."""
    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("bf", "bronze.fundamentals_raw")
        rows = engine.sql("""
            SELECT source_tier, COUNT(*) AS n
            FROM bf
            WHERE source LIKE 'client_csv_%'
            GROUP BY source_tier
        """).to_pylist()
    by_tier = {r["source_tier"]: r["n"] for r in rows}
    assert by_tier["client_authoritative"] > 0
    assert by_tier["client_historical"] > 0


def test_shreyas_wins_over_format_b_on_overlap(pipeline_run):
    """For NABIL 2080/Q4 net_profit both sources wrote 7,060,033. Silver
    must pick the Shreyas (CLIENT_AUTHORITATIVE) row, not Format B."""
    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("fl", "silver.fundamentals_long")
        row = engine.sql("""
            SELECT value, source, source_tier
            FROM fl
            WHERE scrip = 'NABIL'
              AND fiscal_year_bs = 2080
              AND quarter = 4
              AND metric_name = 'net_profit'
        """).to_pylist()
    assert len(row) == 1, "exactly one winner expected after tier dedup"
    assert row[0]["source"] == "client_csv_shreyas"
    assert row[0]["source_tier"] == "client_authoritative"
    assert row[0]["value"] == 7_060_033.0


def test_nabil_published_values_in_silver_snapshot(pipeline_run):
    """Silver snapshot for NABIL 2080/Q4 must carry NPR '000s values
    matching the published NABIL Q4 FY 2023-24 interim financial report:
      due_from_nrb         = 20,182,905 (thousand)
      placement_with_bfis  = 14,287,531 (thousand)
      loans_to_customers   = 373,977,599 (thousand)
    If any of these drift, the unit convention has broken somewhere in
    the Bronze → Silver path."""
    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("fs", "silver.fundamentals_snapshots")
        row = engine.sql("""
            SELECT due_from_nrb, placement_with_bfis, loans_to_customers, net_profit
            FROM fs
            WHERE scrip = 'NABIL' AND fiscal_year_bs = 2080 AND quarter = 4
        """).to_pylist()[0]
    assert row["due_from_nrb"] == 20_182_905.0
    assert row["placement_with_bfis"] == 14_287_531.0
    assert row["loans_to_customers"] == 373_977_599.0
    assert row["net_profit"] == 7_060_033.0


def test_nicasia_appears_in_silver(pipeline_run):
    """NICA (scrip_master) and NICASIA (client CSVs) must both resolve to
    NICASIA via canonical_ticker — if scrip_master wasn't canonicalized,
    the active_only JOIN would drop all NICASIA rows."""
    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("fs", "silver.fundamentals_snapshots")
        row = engine.sql(
            "SELECT COUNT(*) AS n FROM fs WHERE scrip = 'NICASIA'"
        ).to_pylist()[0]
    assert row["n"] > 0, "NICASIA dropped from Silver — canonical_ticker gap"


def test_format_b_prices_reach_silver_closes(pipeline_run):
    """silver.closes must carry the Format B ~14-year close series for
    18 of the 19 banks (SCB is the known gap — client hasn't sent a
    price file for it yet)."""
    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("sc", "silver.closes")
        summary = engine.sql("""
            SELECT COUNT(DISTINCT scrip) AS scrip_count,
                   MIN(date) AS first_date,
                   MAX(date) AS last_date,
                   COUNT(*)  AS total_rows
            FROM sc
        """).to_pylist()[0]
    assert summary["scrip_count"] == 18, "expected 18 banks (SCB excluded)"
    # Coverage starts in July 2011.
    assert summary["first_date"].year == 2011
    assert summary["total_rows"] > 50_000


def test_scb_has_fundamentals_but_no_closes(pipeline_run):
    """SCB sanity check: present in fundamentals (from Shreyas + Format B)
    but absent from silver.closes because the client didn't ship a price
    CSV. Documented data gap in the README."""
    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("fs", "silver.fundamentals_snapshots")
        engine.register_table("sc", "silver.closes")
        fund_count = engine.sql(
            "SELECT COUNT(*) AS n FROM fs WHERE scrip = 'SCB'"
        ).to_pylist()[0]["n"]
        close_count = engine.sql(
            "SELECT COUNT(*) AS n FROM sc WHERE scrip = 'SCB'"
        ).to_pylist()[0]["n"]
    assert fund_count > 0
    assert close_count == 0
