"""Source abstraction for Bronze-layer ingestion.

Every ingester (scraper CSV, client CSV dump, future NEPSE API, future live
floor-sheet feed) emits rows into canonical Bronze tables. Each row carries a
BronzeStamp describing where it came from and how authoritative it is.

Silver-layer dedup uses the `source_tier` rank to pick winners across sources
for the same (scrip, period, metric) key — see `source_tier_rank_sql` below
for the SQL form."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from nrc_contracts import SOURCE_TIER_RANK, SourceTier

from ._report import IngestionReport


@dataclass(frozen=True)
class BronzeStamp:
    """Lineage columns stamped on every Bronze row by its Source.

    `source` is a free-form slug identifying the concrete producer
    (e.g. 'sharesansar', 'client_csv_shreyas', 'client_csv_format_b',
    'nepse_api_v1'). `source_tier` fixes precedence at Silver merge time.
    `source_file` is the filename/URL/key the row was read from — useful for
    debugging which snapshot a bad row came from."""
    source: str
    source_tier: SourceTier
    ingested_at: datetime
    source_file: str | None = None


class Source(Protocol):
    """Contract every Bronze ingester must implement.

    Sources are free to emit into multiple Bronze tables (one run of the
    Shreyas adapter, for example, populates both bronze.fundamentals_raw and
    bronze.additional_info_raw) — return one IngestionReport per table
    touched."""

    name: str
    tier: SourceTier

    def ingest(
        self,
        input_dir: Path,
        *,
        mode: str = "overwrite",
    ) -> list[IngestionReport]:
        """Run the ingest and return a report per Bronze table written."""
        ...


def source_tier_rank_sql(source_tier_col: str = "source_tier") -> str:
    """SQL CASE expression mapping `source_tier` values to precedence rank.

    Lower rank wins. Used at Silver merge time inside
    `QUALIFY ROW_NUMBER() OVER (PARTITION BY key ORDER BY tier_rank ASC,
    ingested_at DESC) = 1`. Unknown/NULL source_tier defaults to the worst
    rank so anonymous rows can never overwrite tier-stamped ones."""
    max_rank = max(SOURCE_TIER_RANK.values()) + 1
    cases = "\n        ".join(
        f"WHEN {source_tier_col} = '{tier.value}' THEN {rank}"
        for tier, rank in SOURCE_TIER_RANK.items()
    )
    return f"""CASE
        {cases}
        ELSE {max_rank}
    END"""
