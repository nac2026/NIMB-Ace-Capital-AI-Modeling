"""Shared ingestion report + helpers. Every bronze_* module returns one of these."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class IngestionReport:
    """Outcome of one Bronze ingestion run. Logged + (later) persisted to Postgres.

    `rows_written` is post-dedup. `rows_read` is raw count from source files.
    The difference is the dedup yield; large gaps are a red flag (double-scrape)."""
    table: str
    rows_read: int
    rows_written: int
    source_files: int
    delta_version: int
    started_at: datetime
    finished_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def duration_s(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    def summary(self) -> str:
        dedup_note = f" (deduped {self.rows_read - self.rows_written})" if self.rows_read != self.rows_written else ""
        return (
            f"[{self.table}] wrote {self.rows_written:,} rows{dedup_note} from "
            f"{self.source_files} file(s) in {self.duration_s:.1f}s "
            f"(delta version={self.delta_version})"
        )
