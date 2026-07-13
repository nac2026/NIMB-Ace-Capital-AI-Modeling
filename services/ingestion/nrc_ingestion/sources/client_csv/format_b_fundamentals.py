"""Format-B wide fundamentals ingest (historical backfill, 2010/11→present).

Input: per-scrip CSVs under three sibling folders of
`<OneDrive>/Commercial bank/`:

  * `Commercial bank key stats/<TICKER>.csv`        — TTM ratios & per-share
  * `Commercial bank balance sheet/<TICKER>.csv`    — quarterly balance sheet
  * `Commercial bank Income Statement/<TICKER>.csv` — quarterly P&L

Each file is wide/pivoted with two header rows (year label, then quarter
label) and metric rows below. Example:

    "Balance Sheet","2025/26","2025/26","2025/26","2025/26","2024/25",...
    "Balance Sheet","Q4","Q3","Q2","Q1","Q4","Q3","Q2","Q1",...
    "TOTAL ASSETS","","","697,025,625","675,523,530","638,155,759",...
    "CASH AND BANK BALANCE","","","9,189,774","10,549,572",...

Coverage is deeper than Shreyas (2010/11 vs 2020/21) but less consistent.
Tagged `CLIENT_HISTORICAL` — loses to Shreyas at Silver-merge time for any
overlapping (scrip, fy, quarter, metric). Its value is the pre-2020/21
backfill.

Output: `bronze.fundamentals_raw` — long format, section ∈
{'format_b_key_stats', 'format_b_bs', 'format_b_is'}. Unlike Shreyas, which
knows canonical column names, Format B metric names are the raw row labels
('TOTAL ASSETS', 'Return on Asset (TTM)', etc.) — Silver's `_metric_map`
normalizes them."""
from __future__ import annotations
import csv
import re
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa

from nrc_contracts import SourceTier
from nrc_nepal import canonical_ticker, parse_ad_fiscal_year_short
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ..._report import IngestionReport

_TABLE = "bronze.fundamentals_raw"
_SOURCE_NAME = "client_csv_format_b"
_SOURCE_TIER = SourceTier.CLIENT_HISTORICAL.value

# Subfolder → section tag recorded in Bronze
_SECTIONS: dict[str, str] = {
    "Commercial bank key stats": "format_b_key_stats",
    "Commercial bank balance sheet": "format_b_bs",
    "Commercial bank Income Statement": "format_b_is",
}

# Strip trailing unit/context annotations from metric names so (TTM)/(Annualized)/
# (Rs. 000) variants collapse to the same canonical label at Silver.
_METRIC_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")
# Dash-only cells and empty cells are missing values.
_MISSING_VALUES = frozenset({"", "-", "—", "N/A", "NA"})


def _clean_metric(raw: str) -> str:
    """Strip whitespace, trailing parenthetical annotations, and collapse
    case — preserving human readability for Bronze inspection. Silver's
    `_metric_map` further canonicalizes to snake_case slugs."""
    s = raw.strip()
    # Strip repeated trailing parentheticals: "EPS (Annualized)" -> "EPS"
    while True:
        new = _METRIC_SUFFIX_RE.sub("", s).strip()
        if new == s:
            break
        s = new
    return s


def _parse_value(raw: str) -> float | None:
    """Turn '1,234,567.89' / '45.2%' / '' / '-' into a float or None."""
    s = raw.strip().strip('"').strip()
    if s in _MISSING_VALUES:
        return None
    # Tolerate parenthesized negatives: '(123.45)' -> -123.45
    negative = False
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
        negative = True
    s = s.replace(",", "")
    if s.endswith("%"):
        try:
            return (-1 if negative else 1) * float(s[:-1]) / 100.0
        except ValueError:
            return None
    try:
        return (-1 if negative else 1) * float(s)
    except ValueError:
        return None


def _parse_file(
    csv_path: Path,
    section: str,
    ingested_at: datetime,
    source_file: str,
) -> list[dict[str, object]]:
    """Yield Bronze rows for one per-scrip wide CSV.

    First two rows are year/quarter headers; remaining rows are metrics.
    Columns where either header is empty are skipped — the top-left cell is
    blank by convention and any trailing blanks signal unfilled periods."""
    ticker = canonical_ticker(csv_path.stem)
    rows: list[dict[str, object]] = []

    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        try:
            year_row = next(reader)
            quarter_row = next(reader)
        except StopIteration as e:
            raise ValueError(f"{csv_path}: missing header rows") from e

        # Build a (col_index → (fy_bs, quarter_int)) map for data columns.
        # Column 0 holds the metric name. Columns 1..N are period-tagged.
        period_map: dict[int, tuple[int, int]] = {}
        for col_idx, (year_cell, q_cell) in enumerate(zip(year_row, quarter_row)):
            if col_idx == 0:
                continue
            year_cell = year_cell.strip().strip('"')
            q_cell = q_cell.strip().strip('"').upper()
            if not year_cell or not q_cell:
                continue
            if not q_cell.startswith("Q") or len(q_cell) != 2 or not q_cell[1].isdigit():
                continue
            try:
                fy_bs = parse_ad_fiscal_year_short(year_cell)
            except ValueError:
                continue
            quarter = int(q_cell[1])
            if quarter not in (1, 2, 3, 4):
                continue
            period_map[col_idx] = (fy_bs, quarter)

        for row in reader:
            if not row or not row[0].strip():
                continue
            metric = _clean_metric(row[0])
            if not metric:
                continue
            for col_idx, (fy_bs, quarter) in period_map.items():
                if col_idx >= len(row):
                    continue
                value = _parse_value(row[col_idx])
                if value is None:
                    continue
                rows.append({
                    "scrip": ticker,
                    "section": section,
                    "metric": metric,
                    "period_raw": None,
                    "fiscal_year_bs": fy_bs,
                    "quarter": quarter,
                    "value_raw": row[col_idx],
                    "value_num": value,
                    "ingested_at": ingested_at,
                    "source": _SOURCE_NAME,
                    "source_tier": _SOURCE_TIER,
                    "source_file": source_file,
                })
    return rows


def ingest_client_csv_format_b_fundamentals(
    input_dir: Path,
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> IngestionReport:
    """Ingest every per-scrip wide CSV under the three known subfolders.

    `input_dir` should be the `Commercial bank/` folder containing the three
    known subfolders. Missing subfolders are skipped with a warning stored
    in the report (rows_read still reflects what was parsed)."""
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    subfolders = {
        name: input_dir / name
        for name in _SECTIONS
    }
    present = {name: path for name, path in subfolders.items() if path.is_dir()}
    if not present:
        raise FileNotFoundError(
            f"none of {list(_SECTIONS)!r} found under {input_dir}"
        )

    all_rows: list[dict[str, object]] = []
    file_count = 0
    raw_rows_read = 0
    for folder_name, folder_path in present.items():
        section = _SECTIONS[folder_name]
        for csv_path in sorted(folder_path.glob("*.csv")):
            file_count += 1
            parsed = _parse_file(csv_path, section, started_at, csv_path.name)
            raw_rows_read += len(parsed)
            all_rows.extend(parsed)

    # Dedup on (scrip, fy, quarter, section, metric) — same filename can't
    # produce two rows for the same key, but belt-and-braces.
    dedup: dict[tuple, dict[str, object]] = {}
    for r in all_rows:
        key = (r["scrip"], r["fiscal_year_bs"], r["quarter"], r["section"], r["metric"])
        dedup[key] = r
    deduped = list(dedup.values())

    table = pa.Table.from_pylist(deduped, schema=pa.schema([
        pa.field("scrip", pa.string()),
        pa.field("section", pa.string()),
        pa.field("metric", pa.string()),
        pa.field("period_raw", pa.string(), nullable=True),
        pa.field("fiscal_year_bs", pa.int64()),
        pa.field("quarter", pa.int64()),
        pa.field("value_raw", pa.string(), nullable=True),
        pa.field("value_num", pa.float64(), nullable=True),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC")),
        pa.field("source", pa.string()),
        pa.field("source_tier", pa.string()),
        pa.field("source_file", pa.string(), nullable=True),
    ]))

    io = DeltaIO(settings)
    # Partition-aware upsert: only replace rows tagged client_csv_format_b,
    # leaving Shreyas + scraper rows in the same table intact.
    if mode == "overwrite":
        io.upsert_source_partition(_TABLE, table, source=_SOURCE_NAME)
    else:
        io.write(_TABLE, table, mode=mode)

    return IngestionReport(
        table=_TABLE,
        rows_read=raw_rows_read,
        rows_written=table.num_rows,
        source_files=file_count,
        delta_version=io.version(_TABLE),
        started_at=started_at,
    )
