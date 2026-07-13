"""SMTM Data API connection settings. Reads SMTM_* from the repo-root .env.

The live NEPSE feed is provided by SMTM Capital (LaganiSutra). Credentials are
client-owned; keep them in .env (git-ignored), never in source. The documented
rate limit is 100/min but the server actually advertises a far more generous
policy via `ratelimit-*` response headers — the client respects those headers
at runtime, so SMTM_RATE_LIMIT_PER_MIN is only a conservative fallback ceiling."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class SMTMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    smtm_base_url: str = Field(default="https://dataapi.smtmcapital.com.np")
    smtm_username: str = Field(default="")
    smtm_password: str = Field(default="")

    # Conservative fallback ceiling; the client prefers the server's ratelimit-* headers.
    smtm_rate_limit_per_min: int = Field(default=100, ge=1)
    smtm_timeout_seconds: float = Field(default=60.0, gt=0)
    # Refresh the access token this many seconds before its JWT `exp`.
    smtm_token_refresh_margin_s: int = Field(default=60, ge=0)

    def require_credentials(self) -> tuple[str, str]:
        """Return (username, password) or raise a helpful error."""
        if not self.smtm_username or not self.smtm_password:
            raise RuntimeError(
                "SMTM_USERNAME / SMTM_PASSWORD are not set. Add them to .env at the "
                "repo root (template in .env.example). Provided by SMTM Capital."
            )
        return self.smtm_username, self.smtm_password


@lru_cache(maxsize=1)
def get_smtm_settings() -> SMTMSettings:
    return SMTMSettings()
