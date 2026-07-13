"""Dagster orchestration for the NEPSE research copilot lakehouse.

Entry point: `nrc_pipelines:defs` — loads Bronze/Silver/Gold assets,
jobs, schedules, and resources. Run locally with
`uv run dagster dev -m nrc_pipelines --port 3001`."""
__version__ = "0.1.0"

# Re-export so `dagster dev -m nrc_pipelines` finds the Definitions object
# at the top level of the module (Dagster's default discovery mechanism).
from .definitions import defs  # noqa: F401

__all__ = ["defs"]
