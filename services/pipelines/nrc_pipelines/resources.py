"""Shared Dagster resources.

Two resources are injected into every asset that needs them:

  * `StorageResource` — wraps `nrc_storage.get_settings()` so assets get the
    same MinIO / Postgres / Redis connection state the CLI tools use. This
    is a thin adapter; the real configuration lives in env vars + .env.
  * `ClientDocsResource` — the root OneDrive path that client CSV adapters
    read from. Overridable via the `NRC_CLIENT_DOCS_DIR` env var so CI and
    engineers can point at different test fixtures without editing code.

Keep resources thin. Heavy objects (DuckDB connections, Delta tables) are
constructed inside assets on demand because they're cheap enough per run
and pool poorly across Dagster's process model."""
from __future__ import annotations
import os
from pathlib import Path

from dagster import ConfigurableResource
from pydantic import Field

from nrc_storage import StorageSettings, get_settings


class StorageResource(ConfigurableResource):
    """Thin facade over `nrc_storage.get_settings()`.

    The underlying StorageSettings singleton is populated from env / .env at
    process start; this resource simply makes it addressable by Dagster's
    dependency injection and surfaces the key connection endpoints in the
    UI for quick sanity checks."""

    @property
    def settings(self) -> StorageSettings:
        return get_settings()

    @property
    def minio_endpoint(self) -> str:
        return self.settings.minio_endpoint

    @property
    def lakehouse_uri(self) -> str:
        return self.settings.lakehouse_uri

    @property
    def postgres_url(self) -> str:
        return self.settings.postgres_url


class ClientDocsResource(ConfigurableResource):
    """Root path to the client-provided OneDrive data dump.

    Layout expected under `root`:
      CB Data by Shreyas/cb*.csv
      Commercial bank/Commercial bank balance sheet/<TICKER>.csv
      Commercial bank/Commercial bank Income Statement/<TICKER>.csv
      Commercial bank/Commercial bank key stats/<TICKER>.csv
      Commercial bank/Commercial bank Price 5 years/<TICKER>.csv

    Override with the NRC_CLIENT_DOCS_DIR env var when pointing at a
    different drop location (CI fixture, alternate client, etc.)."""

    root: str = Field(
        default_factory=lambda: os.getenv(
            "NRC_CLIENT_DOCS_DIR",
            str(
                Path(__file__).resolve().parents[4]
                / "client-docs"
                / "OneDrive_1_4-24-2026"
            ),
        ),
        description="Root OneDrive directory containing client CSV drops.",
    )

    @property
    def path(self) -> Path:
        return Path(self.root)

    @property
    def shreyas_dir(self) -> Path:
        return self.path / "CB Data by Shreyas"

    @property
    def automation_dir(self) -> Path:
        return self.path / "Data for Automation"

    @property
    def format_b_dir(self) -> Path:
        return self.path / "Commercial bank"

    @property
    def format_b_prices_dir(self) -> Path:
        return self.format_b_dir / "Commercial bank Price 5 years"

    @property
    def internal_trades_dir(self) -> Path:
        """The firm's trade-book xlsx drop folder (sibling dir, not OneDrive).

        Override with NRC_INTERNAL_TRADES_DIR when the desk's drop location
        moves (e.g. a shared drive once the daily feed is automated)."""
        return Path(
            os.getenv(
                "NRC_INTERNAL_TRADES_DIR",
                str(Path(__file__).resolve().parents[4] / "internal-trade-data"),
            )
        )
