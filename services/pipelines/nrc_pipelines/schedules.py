"""Dagster schedules.

One schedule is defined for now:
  daily_eod_schedule — runs daily_eod_job at 20:00 NPT (= 14:15 UTC).

The schedule is **stopped by default** — Dagster creates it in the
`STOPPED` state, so deploying this package won't start auto-runs. Flip
it to running from the UI (or via `dagster schedule start`) when you're
ready for hands-off operation.

Adding more schedules later (e.g. a faster intraday cycle once live data
is wired) should follow the same pattern: pair a cron expression with an
existing job."""
from __future__ import annotations

from dagster import DefaultScheduleStatus, ScheduleDefinition

from .jobs import daily_eod_job, floorsheet_job, github_prices_backfill_job, news_job

# Timezone note: NEPSE trades 11:00–15:00 NPT. EOD data is typically
# published by ~19:30 NPT. 20:00 gives a small buffer before downstream
# consumers expect fresh Gold tables.
daily_eod_schedule = ScheduleDefinition(
    name="daily_eod_schedule",
    job=daily_eod_job,
    cron_schedule="0 20 * * *",
    execution_timezone="Asia/Kathmandu",
    default_status=DefaultScheduleStatus.STOPPED,
    description=(
        "Triggers daily_eod_job at 20:00 NPT every day. Stopped by default — "
        "start from the Dagster UI when ready to automate."
    ),
)

# Floor-sheet reconcile at 15:30 NPT — just after the 15:00 market close, when
# the full day's floor-sheet is available. The marketfeed floorsheet_puller
# handles live intraday incremental pulls; this is the authoritative EOD pass
# that rebuilds the broker-flow Gold + internal-surveillance + serving tables.
#
# RUNNING by default — unlike every other schedule. SMTM's API exposes ONLY the
# current session's floor-sheet (verified: date params ignored, no history
# endpoints, live-data scope), so a missed trading day is unrecoverable data
# loss. The Dagster daemon must be up at 15:30 NPT Sun–Thu for this to fire.
floorsheet_schedule = ScheduleDefinition(
    name="floorsheet_schedule",
    job=floorsheet_job,
    cron_schedule="30 15 * * 0-4",   # Sun–Thu (NEPSE trades Sun–Thu)
    execution_timezone="Asia/Kathmandu",
    default_status=DefaultScheduleStatus.RUNNING,
    description=(
        "Triggers floorsheet_job at 15:30 NPT on trading days (Sun–Thu) for the "
        "full-day broker-flow + internal-surveillance reconcile. RUNNING by "
        "default — SMTM only exposes the current session, so a missed day's "
        "floor-sheet is lost forever."
    ),
)

# Intraday broker-flow refresh during the 11:00–15:00 NPT session (every 30 min,
# Sun–Thu). floorsheet_job re-pulls the day's floor-sheet (Bronze append; Silver
# dedups on contract_number) so broker signals stay fresh through the session.
# The marketfeed floorsheet_puller service is the lighter incremental
# alternative; this is the Dagster-native option. Stopped by default.
floorsheet_intraday_schedule = ScheduleDefinition(
    name="floorsheet_intraday_schedule",
    job=floorsheet_job,
    cron_schedule="*/30 11-15 * * 0-4",
    execution_timezone="Asia/Kathmandu",
    default_status=DefaultScheduleStatus.STOPPED,
    description="Refreshes broker-flow every 30 min during the trading session (Sun–Thu). Stopped by default.",
)

# Live news: a cycle every 30 min from ~10:00–21:00 NPT (market + after-hours
# coverage). Keeps news_articles + scrip_sentiment current for the dashboard,
# company-360 News tab, and chat sentiment context. Stopped by default.
news_schedule = ScheduleDefinition(
    name="news_schedule",
    job=news_job,
    cron_schedule="*/30 10-21 * * *",
    execution_timezone="Asia/Kathmandu",
    default_status=DefaultScheduleStatus.STOPPED,
    description="Runs the live news ingestion + sentiment cycle every 30 min (10:00–21:00 NPT). Stopped by default.",
)

# GitHub community price backfill — weekly fallback. The repo auto-updates daily,
# so a weekly re-pull keeps the historical/fallback OHLCV reasonably fresh until
# SMTM supplies full all-sector history. Saturdays 06:00 NPT (non-trading day,
# off the daily-EOD path). Stopped by default.
github_prices_schedule = ScheduleDefinition(
    name="github_prices_schedule",
    job=github_prices_backfill_job,
    cron_schedule="0 6 * * 6",
    execution_timezone="Asia/Kathmandu",
    default_status=DefaultScheduleStatus.STOPPED,
    description=(
        "Weekly GitHub price backfill (Sat 06:00 NPT) — refreshes the fallback "
        "OHLCV history in bronze.prices_raw and rebuilds price Gold. Stopped by default."
    ),
)
