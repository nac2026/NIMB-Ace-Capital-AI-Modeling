"""Pipeline trigger endpoint — fires the Dagster daily_eod_job on demand.

POST /api/pipeline/refresh — submit daily_eod_job to the running `dagster dev`
                              instance via its GraphQL API.
GET  /api/pipeline/status  — poll the most recent run from Dagster.

Implementation: posts a `launchRun` mutation to http://localhost:3001/graphql
(the URL exposed by `dagster dev -m nrc_pipelines --port 3001`). Because the
run is submitted *through* the dev instance, it appears in the Dagster UI
with full logs — and the user can drill into asset materialisations there.

Requires `dagster dev` to be running on port 3001 (Tab 5 in the demo setup).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Body, Request
from pydantic import BaseModel

from .refresh_brokers import refresh_brokers
from .refresh_fundamentals import refresh_smtm_fundamentals
from .refresh_indices import refresh_index_snapshots

_log = logging.getLogger("nrc_orchestrator.api_pipeline")

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

DAGSTER_URL = os.getenv("DAGSTER_GRAPHQL_URL", "http://localhost:3001/graphql")
DAGSTER_UI_URL = os.getenv("DAGSTER_UI_URL", "http://localhost:3001")
LOCATION_NAME = "nrc_pipelines"     # matches `dagster dev -m nrc_pipelines`
REPOSITORY_NAME = "__repository__"  # default for Definitions() objects

# A "Refresh" reloads ALL live data: universe + fundamentals (daily_eod_job),
# floor-sheet broker flow (floorsheet_job), and news + sentiment (news_job).
# Each job ends by syncing its tables into Postgres so the app sees the result.
DATA_JOBS = ["daily_eod_job", "floorsheet_job", "news_job"]

# Jobs that touch no SMTM live data — skip the inline index-snapshot refresh
# when a refresh request launches only these (e.g. the surveillance board's
# "Load new trade-book data" button firing tradebook_job).
_NO_SMTM_JOBS = {"tradebook_job", "postgres_sync_job"}


# ─── State (run ids from the last refresh) ──────────────────────────
_last_run_ids: list[str] = []


class RefreshRequest(BaseModel):
    jobs: list[str] | None = None   # default: all DATA_JOBS


# ─── Response model ─────────────────────────────────────────────────
class PipelineState(BaseModel):
    status: Literal["idle", "running", "succeeded", "failed", "queued", "canceled"] = "idle"
    run_id: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    exit_code: int | None = None  # Kept for FE compatibility; always None here.
    message: str | None = None
    dagster_url: str | None = None
    jobs: list[str] = []          # job names launched by the last refresh


# ─── GraphQL helpers ────────────────────────────────────────────────
_LAUNCH_RUN_MUTATION = """
mutation LaunchRun($selector: JobOrPipelineSelector!) {
  launchPipelineExecution(
    executionParams: {
      selector: $selector
      runConfigData: {}
      mode: "default"
    }
  ) {
    __typename
    ... on LaunchRunSuccess { run { runId status } }
    ... on RunConfigValidationInvalid { errors { message } }
    ... on PipelineNotFoundError { message }
    ... on InvalidSubsetError { message }
    ... on PythonError { message stack }
  }
}
"""

_RUN_STATUS_QUERY = """
query RunStatus($runId: ID!) {
  pipelineRunOrError(runId: $runId) {
    __typename
    ... on Run {
      runId
      status
      startTime
      endTime
    }
    ... on RunNotFoundError { message }
    ... on PythonError { message }
  }
}
"""

DAGSTER_STATUS_MAP: dict[str, Literal["idle", "running", "succeeded", "failed", "queued", "canceled"]] = {
    "QUEUED": "queued",
    "NOT_STARTED": "queued",
    "STARTING": "running",
    "STARTED": "running",
    "MANAGED": "running",
    "SUCCESS": "succeeded",
    "FAILURE": "failed",
    "CANCELED": "canceled",
    "CANCELING": "running",
}


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


async def _gql(query: str, variables: dict) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            DAGSTER_URL,
            json={"query": query, "variables": variables},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


# ─── Endpoints ──────────────────────────────────────────────────────
async def _launch(job_name: str) -> tuple[str | None, str | None]:
    """Launch one Dagster job. Returns (run_id, error_message)."""
    selector = {
        "repositoryLocationName": LOCATION_NAME,
        "repositoryName": REPOSITORY_NAME,
        "jobName": job_name,
    }
    try:
        data = await _gql(_LAUNCH_RUN_MUTATION, {"selector": selector})
    except httpx.ConnectError:
        return None, f"Cannot reach Dagster at {DAGSTER_URL}. Is `dagster dev` running?"
    except Exception as e:  # noqa: BLE001
        _log.exception("Dagster GraphQL call failed for %s", job_name)
        return None, f"GraphQL request failed: {e}"

    if "errors" in data:
        return None, f"GraphQL error: {data['errors'][0].get('message', 'unknown')}"

    payload = data.get("data", {}).get("launchPipelineExecution", {})
    if payload.get("__typename") == "LaunchRunSuccess":
        return payload["run"]["runId"], None
    msg = payload.get("message") or f"Unexpected response type: {payload.get('__typename')}"
    return None, msg


@router.post("/refresh-indices")
def refresh_indices_now(request: Request) -> dict:
    """Refresh the live NEPSE + sub-index snapshot directly from SMTM (no
    Dagster needed). Keeps `index_snapshots` — and the dashboard's index strip
    + 'As of' date — current even though indices aren't part of the Dagster
    daily_eod_job."""
    pg = request.app.state.pg
    try:
        report = refresh_index_snapshots(pg)
        _log.info("refresh-indices: %s", report)
        return {"ok": True, **report}
    except Exception as e:  # noqa: BLE001
        _log.warning("refresh-indices failed: %s", e)
        return {"ok": False, "error": str(e)}


@router.post("/refresh-brokers")
def refresh_brokers_now(request: Request) -> dict:
    """Refresh the NEPSE broker directory (code → firm name + logo) directly from
    SMTM's authoritative `broker_list` into the serving `brokers` dimension.
    Surveillance/alerts/broker tools read this table, so names + logos update
    everywhere without editing the hand-seeded 015_brokers.sql."""
    pg = request.app.state.pg
    try:
        report = refresh_brokers(pg)
        _log.info("refresh-brokers: %s", report)
        return {"ok": True, **report}
    except Exception as e:  # noqa: BLE001
        _log.warning("refresh-brokers failed: %s", e)
        return {"ok": False, "error": str(e)}


@router.post("/refresh-fundamentals")
def refresh_fundamentals_now(request: Request, limit: int | None = None) -> dict:
    """Bulk-ingest SMTM fundamentals (annual + quarterly key-stats) for EVERY
    active equity into `smtm_fundamentals`, enabling cross-universe screening.
    Heavier (~2 calls/scrip, a few minutes) — run on-demand / on a schedule, not
    inline in the fast refresh. `?limit=N` caps the scrip count (testing)."""
    pg = request.app.state.pg
    try:
        report = refresh_smtm_fundamentals(pg, limit=limit)
        return {"ok": True, **report}
    except Exception as e:  # noqa: BLE001
        _log.warning("refresh-fundamentals failed: %s", e)
        return {"ok": False, "error": str(e)}


@router.get("/tradebook-files")
def tradebook_files() -> dict:
    """List the trade-book xlsx drop folder (NRC_INTERNAL_TRADES_DIR) so the
    surveillance board can show what the server will ingest before the user
    launches tradebook_job. Mirrors the ingestion glob: *.xlsx minus Excel
    lock files, subfolders ignored."""
    folder = Path(os.getenv(
        "NRC_INTERNAL_TRADES_DIR",
        str(Path(__file__).resolve().parents[4] / "internal-trade-data"),
    ))
    files = []
    if folder.is_dir():
        for f in folder.glob("*.xlsx"):
            if f.name.startswith("~$"):
                continue
            st = f.stat()
            files.append({
                "name": f.name,
                "size": st.st_size,
                "modified_at": datetime.fromtimestamp(
                    st.st_mtime, tz=timezone.utc
                ).isoformat(timespec="seconds"),
            })
    files.sort(key=lambda r: r["modified_at"], reverse=True)
    return {"dir": str(folder), "count": len(files), "files": files}


@router.post("/refresh", response_model=PipelineState)
async def refresh_pipeline(request: Request, body: RefreshRequest | None = Body(default=None)) -> PipelineState:
    """Launch all live-data jobs (universe+fundamentals, floor-sheet, news) on the
    running Dagster dev instance. Pass {jobs:[...]} to launch a subset.
    Also refreshes the live index snapshot inline (direct SMTM upsert)."""
    global _last_run_ids
    jobs = (body.jobs if body and body.jobs else DATA_JOBS)
    _log.info("refresh: launching jobs=%s", jobs)

    # Indices come from SMTM live (not a Dagster asset) — refresh inline so the
    # button keeps the index strip + 'As of' current. Skipped when the request
    # launches only lakehouse-local jobs (tradebook reload etc).
    idx_note = ""
    if not all(j in _NO_SMTM_JOBS for j in jobs):
        try:
            rep = refresh_index_snapshots(request.app.state.pg)
            idx_note = f" Indices refreshed ({rep.get('rows', 0)} indices, as of {rep.get('as_of')})."
        except Exception as e:  # noqa: BLE001
            _log.warning("inline index refresh failed: %s", e)
            idx_note = " Index refresh skipped (SMTM unavailable)."
        # Broker directory (code → firm name + logo) — cheap single call, keeps
        # the surveillance counterparty names current from SMTM's directory.
        try:
            brep = refresh_brokers(request.app.state.pg)
            idx_note += f" Brokers refreshed ({brep.get('rows', 0)})."
        except Exception as e:  # noqa: BLE001
            _log.warning("inline broker refresh failed: %s", e)

    launched: list[tuple[str, str]] = []   # (job, run_id)
    errors: list[tuple[str, str]] = []
    for job in jobs:
        run_id, err = await _launch(job)
        if run_id:
            launched.append((job, run_id))
        else:
            errors.append((job, err or "unknown"))

    _last_run_ids = [rid for _, rid in launched]

    if not launched:
        return PipelineState(status="failed",
                             message="; ".join(f"{j}: {e}" for j, e in errors) + idx_note)

    msg = f"Launched {len(launched)} job(s): {', '.join(j for j, _ in launched)}."
    if errors:
        msg += " Failed to launch: " + ", ".join(j for j, _ in errors) + "."
    return PipelineState(
        status="running",
        run_id=launched[0][1],
        started_at=_iso(__import__("time").time()),
        message=msg + idx_note + " Watch progress in the Dagster UI.",
        dagster_url=f"{DAGSTER_UI_URL}/runs",
        jobs=[j for j, _ in launched],
    )


async def _run_status(run_id: str) -> str:
    """Mapped status for one run ('running' on any error so polling continues)."""
    try:
        data = await _gql(_RUN_STATUS_QUERY, {"runId": run_id})
    except Exception:  # noqa: BLE001
        return "running"
    payload = data.get("data", {}).get("pipelineRunOrError", {})
    if payload.get("__typename") != "Run":
        return "running"
    return DAGSTER_STATUS_MAP.get(payload.get("status", ""), "running")


@router.get("/status", response_model=PipelineState)
async def pipeline_status() -> PipelineState:
    """Aggregate status across all runs launched by the last refresh:
    failed if any failed, running if any still running, else succeeded."""
    if not _last_run_ids:
        return PipelineState(status="idle")

    statuses = [await _run_status(rid) for rid in _last_run_ids]
    if any(s == "failed" for s in statuses):
        agg: Literal["running", "succeeded", "failed", "canceled"] = "failed"
    elif any(s in ("running", "queued") for s in statuses):
        agg = "running"
    elif any(s == "canceled" for s in statuses):
        agg = "canceled"
    else:
        agg = "succeeded"

    done = sum(1 for s in statuses if s in ("succeeded", "failed", "canceled"))
    return PipelineState(
        status=agg,
        run_id=_last_run_ids[0],
        message=f"{done}/{len(statuses)} job(s) finished · {agg}",
        dagster_url=f"{DAGSTER_UI_URL}/runs",
    )
