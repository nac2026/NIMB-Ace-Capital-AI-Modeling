"""Pluggable email sender — Resend / SendGrid HTTP APIs or plain SMTP.

Stdlib only (urllib + smtplib), so the lib stays dependency-light. When
notifications are disabled or unconfigured, `send()` returns False and logs
once rather than raising, so callers (Dagster ops, the orchestrator loop) never
crash on a missing mail setup. A hard transport failure raises so the dispatch
log can record the error."""
from __future__ import annotations

import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

from .config import NotificationsSettings, get_notifications_settings

_log = logging.getLogger("nrc_notifications.email")

_RESEND_URL = "https://api.resend.com/emails"
_SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


class EmailSender:
    def __init__(self, settings: NotificationsSettings | None = None):
        self.settings = settings or get_notifications_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.is_configured

    def _from(self) -> str:
        name = self.settings.notifications_from_name
        addr = self.settings.sender
        return f"{name} <{addr}>" if name else addr

    def send(
        self,
        *,
        subject: str,
        html: str,
        text: str,
        to: list[str],
        cc: list[str] | None = None,
    ) -> bool:
        """Send one multipart (text + html) email. Returns True on success,
        False if disabled/unconfigured or no recipients."""
        recipients = sorted({e.strip() for e in to if e and e.strip()})
        cc_list = sorted({e.strip() for e in (cc or []) if e and e.strip()} - set(recipients))
        if not recipients and not cc_list:
            _log.info("email skipped: no recipients (subject=%r)", subject)
            return False
        if not self.settings.is_configured:
            _log.warning(
                "email NOT sent (notifications disabled/unconfigured): subject=%r to=%s",
                subject, recipients,
            )
            return False

        provider = self.settings.provider
        if provider == "resend":
            self._send_resend(subject, html, text, recipients, cc_list)
        elif provider == "sendgrid":
            self._send_sendgrid(subject, html, text, recipients, cc_list)
        else:
            self._send_smtp(subject, html, text, recipients, cc_list)
        _log.info("email sent via %s: subject=%r to=%s cc=%s", provider, subject, recipients, cc_list)
        return True

    # ----------------------------------------------------------- transports
    def _post_json(self, url: str, payload: dict, api_key: str) -> None:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                # Resend/SendGrid sit behind Cloudflare, which blocks the default
                # "Python-urllib/x.y" UA (HTTP 403, code 1010). Use a normal UA.
                "User-Agent": "nrc-notifications/0.1 (+https://nimbace.local)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.settings.notifications_timeout_s) as resp:
                if resp.status >= 300:
                    raise RuntimeError(f"HTTP {resp.status}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"email API {e.code}: {detail}") from e

    def _send_resend(self, subject, html, text, to, cc) -> None:
        payload = {
            "from": self._from(),
            "to": to,
            "subject": subject,
            "html": html,
            "text": text,
        }
        if cc:
            payload["cc"] = cc
        self._post_json(_RESEND_URL, payload, self.settings.notifications_api_key)

    def _send_sendgrid(self, subject, html, text, to, cc) -> None:
        personalization: dict = {"to": [{"email": e} for e in to]}
        if cc:
            personalization["cc"] = [{"email": e} for e in cc]
        payload = {
            "personalizations": [personalization],
            "from": {"email": self.settings.sender, "name": self.settings.notifications_from_name or None},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text},
                {"type": "text/html", "value": html},
            ],
        }
        self._post_json(_SENDGRID_URL, payload, self.settings.notifications_api_key)

    def _send_smtp(self, subject, html, text, to, cc) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.settings.sender
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        ctx = ssl.create_default_context()
        with smtplib.SMTP(
            self.settings.notifications_smtp_host,
            self.settings.notifications_smtp_port,
            timeout=self.settings.notifications_timeout_s,
        ) as smtp:
            smtp.starttls(context=ctx)
            smtp.login(self.settings.notifications_smtp_username, self.settings.notifications_smtp_password)
            smtp.send_message(msg, to_addrs=to + cc)
