"""Alerts API + background dispatch loop.

Endpoints (prefix /api/alerts):
  POST   /run?mode=incremental|digest   — evaluate + send now (manual / test)
  GET    /recent?limit=                  — recent dispatched alerts (UI bell feed)
  GET    /recipients                     — standing recipient list
  POST   /recipients                     — add/enable a recipient
  DELETE /recipients/{email}             — deactivate a recipient
  GET    /assignments                    — per-scrip member assignments
  POST   /assignments                    — assign a member to a scrip
  DELETE /assignments/{scrip}/{email}    — remove an assignment

`alerts_background_loop` is started from the server lifespan: it sends urgent
incremental alerts every ~15 min during the NEPSE session and one daily digest
after close. Everything no-ops cleanly when email is unconfigured.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Request
from pydantic import BaseModel

from nrc_notifications import EmailSender, get_notifications_settings
from nrc_processing.speculation_alerts import dispatch, recent

_log = logging.getLogger("nrc_orchestrator.api_alerts")

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

_NPT = timezone(timedelta(hours=5, minutes=45))
WEB_BASE = os.getenv("NRC_WEB_BASE", "http://localhost:3000")


def _sender() -> EmailSender:
    return EmailSender(get_notifications_settings())


# ----------------------------------------------------------------- run / feed
@router.post("/run")
def run_alerts(request: Request, mode: str = "incremental") -> dict:
    """Evaluate current signals and dispatch now. mode=incremental|digest."""
    pg = request.app.state.pg
    mode = "digest" if mode == "digest" else "incremental"
    try:
        report = dispatch(pg, _sender(), mode=mode, web_base=WEB_BASE)
        _log.info("alerts run (%s): %s", mode, report)
        return {"ok": True, **report}
    except Exception as e:  # noqa: BLE001
        _log.warning("alerts run failed: %s", e)
        return {"ok": False, "error": str(e)}


@router.get("/recent")
def recent_alerts(request: Request, limit: int = 30, active_only: bool = False) -> list[dict]:
    return recent(request.app.state.pg, min(max(limit, 1), 200), active_only=active_only)


# ----------------------------------------------------------------- recipients
class RecipientIn(BaseModel):
    email: str
    name: str | None = None
    role: str | None = None


@router.get("/recipients")
def list_recipients(request: Request) -> list[dict]:
    return request.app.state.pg.fetch_all(
        "SELECT id, email, name, role, is_active, created_at FROM alert_recipients ORDER BY created_at"
    )


@router.post("/recipients")
def add_recipient(request: Request, body: RecipientIn = Body(...)) -> dict:
    request.app.state.pg.execute(
        """INSERT INTO alert_recipients (email, name, role, is_active)
           VALUES (%s, %s, %s, TRUE)
           ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, role = EXCLUDED.role, is_active = TRUE""",
        (body.email.strip(), body.name, body.role),
    )
    return {"ok": True, "email": body.email.strip()}


@router.delete("/recipients/{email}")
def remove_recipient(request: Request, email: str) -> dict:
    request.app.state.pg.execute(
        "UPDATE alert_recipients SET is_active = FALSE WHERE email = %s", (email,)
    )
    return {"ok": True, "email": email}


# ----------------------------------------------------------------- assignments
class AssignmentIn(BaseModel):
    scrip: str
    email: str
    name: str | None = None


@router.get("/assignments")
def list_assignments(request: Request) -> list[dict]:
    return request.app.state.pg.fetch_all(
        "SELECT scrip, email, name, assigned_at FROM scrip_assignments ORDER BY scrip, email"
    )


@router.post("/assignments")
def add_assignment(request: Request, body: AssignmentIn = Body(...)) -> dict:
    request.app.state.pg.execute(
        """INSERT INTO scrip_assignments (scrip, email, name) VALUES (%s, %s, %s)
           ON CONFLICT (scrip, email) DO UPDATE SET name = EXCLUDED.name""",
        (body.scrip.strip().upper(), body.email.strip(), body.name),
    )
    return {"ok": True, "scrip": body.scrip.strip().upper(), "email": body.email.strip()}


@router.delete("/assignments/{scrip}/{email}")
def remove_assignment(request: Request, scrip: str, email: str) -> dict:
    request.app.state.pg.execute(
        "DELETE FROM scrip_assignments WHERE scrip = %s AND email = %s",
        (scrip.upper(), email),
    )
    return {"ok": True}


# ----------------------------------------------------------------- loop
async def alerts_background_loop(pg) -> None:
    """Urgent incremental alerts every ~15 min during the NEPSE session
    (11:00–15:30 NPT), plus one daily digest after 15:45 NPT. No-ops cleanly
    when email is disabled (but still reconciles the dispatch log)."""
    settings = get_notifications_settings()
    if not settings.notifications_enabled:
        _log.info("alerts loop: NOTIFICATIONS_ENABLED is false — loop idle (enable in .env to activate)")
        return
    sender = EmailSender(settings)
    last_incremental = datetime.min.replace(tzinfo=timezone.utc)
    last_digest_date = None
    _log.info("alerts loop: started (incremental ≤15m during session, daily digest after 15:45 NPT)")

    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.now(timezone.utc)
            npt = now.astimezone(_NPT)
            in_session = (npt.weekday() in (6, 0, 1, 2, 3)) and (
                (npt.hour, npt.minute) >= (11, 0) and (npt.hour, npt.minute) <= (15, 30)
            )
            # urgent: at most every 15 min, during the session
            if in_session and (now - last_incremental) >= timedelta(minutes=15):
                rep = await asyncio.to_thread(dispatch, pg, sender, mode="incremental", web_base=WEB_BASE)
                last_incremental = now
                if rep.get("emails_sent"):
                    _log.info("alerts loop incremental: %s", rep)
            # daily digest: once, after 15:45 NPT. Run an incremental pass first —
            # the 15:30 floorsheet/trade-book load lands new internal-surveillance
            # cases AFTER the session window closes, and they should email the
            # same evening, not at 11:00 the next day.
            today = npt.date()
            if npt.hour > 15 or (npt.hour == 15 and npt.minute >= 45):
                if last_digest_date != today:
                    rep_inc = await asyncio.to_thread(dispatch, pg, sender, mode="incremental", web_base=WEB_BASE)
                    if rep_inc.get("emails_sent") or rep_inc.get("internal"):
                        _log.info("alerts loop post-close incremental: %s", rep_inc)
                    rep = await asyncio.to_thread(dispatch, pg, sender, mode="digest", web_base=WEB_BASE)
                    last_digest_date = today
                    _log.info("alerts loop digest: %s", rep)
        except Exception as exc:  # noqa: BLE001
            _log.warning("alerts loop iteration failed: %s", exc)
