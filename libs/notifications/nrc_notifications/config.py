"""Email notification settings. Reads NOTIFICATIONS_* from the repo-root .env.

Used for outbound alert emails (speculation/manipulation alerts to the CEO and
assigned members). Transport is pluggable via NOTIFICATIONS_PROVIDER:
  • "resend"   — Resend HTTP API (API key; simplest, great deliverability)
  • "sendgrid" — SendGrid HTTP API (API key; single-sender or domain verified)
  • "smtp"     — plain SMTP/STARTTLS (e.g. Gmail app password)
Sending is gated by `enabled`; when false (default) the EmailSender no-ops so
pipelines/requests never fail just because email isn't configured."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class NotificationsSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    notifications_enabled: bool = Field(default=False)
    # transport: "resend" | "sendgrid" | "smtp"
    notifications_provider: str = Field(default="resend")
    # API-key providers (Resend / SendGrid)
    notifications_api_key: str = Field(default="")
    # From address shown to recipients (provider must allow it: a verified
    # single-sender or domain; Resend allows onboarding@resend.dev for testing).
    notifications_from_email: str = Field(default="")
    notifications_from_name: str = Field(default="NIMB Ace Alerts")
    # SMTP fallback transport
    notifications_smtp_host: str = Field(default="smtp.gmail.com")
    notifications_smtp_port: int = Field(default=587, ge=1)
    notifications_smtp_username: str = Field(default="")
    notifications_smtp_password: str = Field(default="")
    notifications_timeout_s: float = Field(default=30.0, gt=0)

    @property
    def provider(self) -> str:
        return (self.notifications_provider or "resend").strip().lower()

    @property
    def is_configured(self) -> bool:
        if not self.notifications_enabled:
            return False
        if self.provider in ("resend", "sendgrid"):
            return bool(self.notifications_api_key and self.sender)
        # smtp
        return bool(
            self.notifications_smtp_host
            and self.notifications_smtp_username
            and self.notifications_smtp_password
        )

    @property
    def sender(self) -> str:
        """The From email address."""
        return self.notifications_from_email or self.notifications_smtp_username

    def require(self) -> None:
        """Raise a helpful error if email is enabled but mis-configured."""
        if self.notifications_enabled and not self.is_configured:
            if self.provider in ("resend", "sendgrid"):
                raise RuntimeError(
                    f"NOTIFICATIONS_ENABLED=true (provider={self.provider}) but config is "
                    "incomplete. Set NOTIFICATIONS_API_KEY and NOTIFICATIONS_FROM_EMAIL in "
                    ".env at the repo root (template in .env.example)."
                )
            raise RuntimeError(
                "NOTIFICATIONS_ENABLED=true (provider=smtp) but SMTP settings are "
                "incomplete. Set NOTIFICATIONS_SMTP_USERNAME / NOTIFICATIONS_SMTP_PASSWORD."
            )


@lru_cache(maxsize=1)
def get_notifications_settings() -> NotificationsSettings:
    return NotificationsSettings()
