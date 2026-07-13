"""End-to-end ingestion test for the Shreyas tidy CSV adapter.

Uses the real client CSV fixture checked into ../client-docs/OneDrive_*.
Skipped if MinIO isn't reachable."""
from __future__ import annotations
import socket
from pathlib import Path
from urllib.parse import urlparse

import pytest

from nrc_compute import DuckDBEngine
from nrc_ingestion import ingest_client_csv_shreyas
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
_SHREYAS_DIR = _REPO_ROOT.parent / "client-docs" / "OneDrive_1_4-24-2026" / "CB Data by Shreyas"


pytestmark = [
    pytest.mark.skipif(not _minio_up(_SETTINGS.minio_endpoint), reason="MinIO not running"),
    pytest.mark.skipif(not _SHREYAS_DIR.exists(), reason="client-docs OneDrive fixture missing"),
]


@pytest.fixture(scope="module")
def shreyas_ingested():
    """Run the Shreyas ingest once per module — downstream tests query Bronze."""
    MinIOClient(_SETTINGS, bucket=_SETTINGS.minio_bucket_lakehouse).ensure_bucket()
    reports = ingest_client_csv_shreyas(_SHREYAS_DIR, mode="overwrite")
    return reports


def test_shreyas_writes_two_bronze_tables(shreyas_ingested):
    reports = shreyas_ingested
    assert len(reports) == 2
    tables = {r.table for r in reports}
    assert tables == {"bronze.fundamentals_raw", "bronze.additional_info_raw"}
    for r in reports:
        assert r.rows_written > 0, f"{r.table} had 0 rows"


def test_shreyas_rows_tagged_client_authoritative():
    """Every Shreyas row must carry source_tier='client_authoritative'."""
    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("bf", "bronze.fundamentals_raw")
        rows = engine.sql(
            "SELECT DISTINCT source, source_tier FROM bf WHERE source = 'client_csv_shreyas'"
        ).to_pylist()
    assert len(rows) == 1
    assert rows[0]["source_tier"] == "client_authoritative"


def test_shreyas_nica_alias_resolved_to_nicasia():
    """Ticker aliases (NICA → NICASIA) must collapse at the Bronze boundary —
    no raw 'NICA' rows should reach Bronze from the client CSV path."""
    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("bf", "bronze.fundamentals_raw")
        rows = engine.sql("""
            SELECT DISTINCT scrip
            FROM bf
            WHERE source = 'client_csv_shreyas' AND scrip LIKE 'NIC%'
            ORDER BY scrip
        """).to_pylist()
    scrips = {r["scrip"] for r in rows}
    assert "NICA" not in scrips, "NICA alias should have been canonicalized"
    assert "NICASIA" in scrips


def test_shreyas_nabil_published_number():
    """NABIL Q4 FY 2023-24 (BS 2080/4) NetProfitOrLoss should be 7,060,033
    (NPR '000s). Cross-validated against the published NABIL interim
    financial report for Q4 FY 2023-24. This is the unit-convention gate —
    if it drifts, the '000s assumption has broken."""
    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("bf", "bronze.fundamentals_raw")
        row = engine.sql("""
            SELECT value_num
            FROM bf
            WHERE source = 'client_csv_shreyas'
              AND scrip = 'NABIL'
              AND fiscal_year_bs = 2080
              AND quarter = 4
              AND section = 'shreyas_is'
              AND metric = 'NetProfitOrLoss'
        """).to_pylist()
    assert len(row) == 1, "NABIL NetProfitOrLoss for 2080/Q4 not found"
    assert row[0]["value_num"] == 7_060_033.0


def test_shreyas_fiscal_year_conversion():
    """AD '2020/21' → BS 2077, 2023/24 → 2080, 2025/26 → 2082."""
    with DuckDBEngine(_SETTINGS) as engine:
        engine.register_table("bf", "bronze.fundamentals_raw")
        fy_range = engine.sql("""
            SELECT MIN(fiscal_year_bs) AS min_fy, MAX(fiscal_year_bs) AS max_fy
            FROM bf
            WHERE source = 'client_csv_shreyas'
        """).to_pylist()[0]
    # Shreyas covers ~2020/21 (BS 2077) onwards at minimum. Upper bound tracks the
    # latest published quarter.
    assert fy_range["min_fy"] <= 2077
    assert fy_range["max_fy"] >= 2080
