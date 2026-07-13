"""Shared processing report — returned by every Silver/Gold transform."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ProcessingReport:
    """Outcome of one Silver or Gold transform.

    `rows_read` is the upstream Bronze/Silver row count; `rows_written` is the
    final row count after any conformance, filtering, or pivot. Gaps between
    the two should be explainable (dropped invalid rows, pivoted long→wide)."""
    table: str
    rows_read: int
    rows_written: int
    delta_version: int
    started_at: datetime
    finished_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    warnings: list[str] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    def summary(self) -> str:
        warn = f"  ⚠ {len(self.warnings)} warnings" if self.warnings else ""
        return (
            f"[{self.table}] {self.rows_read:,} → {self.rows_written:,} rows "
            f"in {self.duration_s:.1f}s (delta version={self.delta_version}){warn}"
        )
