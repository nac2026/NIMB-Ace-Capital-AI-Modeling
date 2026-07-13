"""Live NEPSE broker-directory refresh — SMTM `broker_list` → serving `brokers`.

The `brokers` dimension (broker code → firm name + logo) was originally
hand-seeded in 015_brokers.sql from a scraped public directory (hamroshare).
SMTM exposes the authoritative directory, so this refresh upserts it directly
into the serving table the surveillance board / alerts / broker tools read —
keeping firm names current and adding official logos, with no hand-maintained
SQL. Slowly-changing reference data (a new broker licence is months apart), but
the call is a single cheap request so it rides along with the live refresh.
"""
from __future__ import annotations

from datetime import datetime, timezone

from nrc_smtm import SMTMClient
from nrc_storage import PostgresClient


def _abs_icon(icon: str | None) -> str | None:
    """SMTM returns a host-relative logo path (images.smtmcapital.com.np/...);
    normalise to an absolute https URL the UI can load directly."""
    if not icon:
        return None
    icon = icon.strip()
    if not icon:
        return None
    if icon.startswith(("http://", "https://")):
        return icon
    return "https://" + icon.lstrip("/")


def refresh_brokers(pg: PostgresClient) -> dict:
    """Pull the broker directory from SMTM and upsert into serving `brokers`.

    `member_type` is left untouched on conflict (SMTM doesn't carry it, so the
    seeded value is preserved). Returns a small report dict ({rows, source})."""
    with SMTMClient() as c:
        c.login()
        brokers = c.broker_list()

    now = datetime.now(timezone.utc)
    rows = 0
    for b in brokers:
        if b.broker is None or not b.name:
            continue
        pg.execute(
            """
            INSERT INTO brokers (broker, name, member_type, icon, source, updated_at)
            VALUES (%s, %s, NULL, %s, 'smtm', %s)
            ON CONFLICT (broker) DO UPDATE SET
                name       = EXCLUDED.name,
                icon       = COALESCE(EXCLUDED.icon, brokers.icon),
                source     = 'smtm',
                updated_at = EXCLUDED.updated_at
            """,
            (b.broker, b.name.strip(), _abs_icon(b.icon), now),
        )
        rows += 1

    return {"rows": rows, "source": "smtm"}
