-- ============================================================================
-- 011_alerts.sql — Email alerting for speculation/manipulation signals.
--
-- Three operational tables (NOT lakehouse-synced — owned by the orchestrator /
-- alert dispatcher):
--   alert_recipients   — people always notified (e.g. the CEO).
--   scrip_assignments  — optional per-scrip owner ("assigned member").
--   alert_dispatch_log — every dispatched/active signal: dedup + audit trail.
-- ============================================================================

-- Always-notified recipients (the standing distribution list).
CREATE TABLE IF NOT EXISTS alert_recipients (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    name        TEXT,
    role        TEXT,                                   -- e.g. 'ceo', 'analyst'
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Optional per-scrip assignment — the member responsible for a scrip also gets
-- that scrip's alerts ("CEO / member assigned if any").
CREATE TABLE IF NOT EXISTS scrip_assignments (
    scrip        VARCHAR(20) NOT NULL,
    email        TEXT NOT NULL,
    name         TEXT,
    assigned_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scrip, email)
);
CREATE INDEX IF NOT EXISTS ix_scrip_assignments_scrip ON scrip_assignments(scrip);

-- Dispatch log — one row per (signal_key) while the signal is ACTIVE.
-- signal_key = '<alert_type>:<scrip>:<level>'  e.g. 'spec:HDHPC:HIGH'.
-- A signal is "new" (email-worthy) when no row with that signal_key and
-- cleared_at IS NULL exists. Each evaluation marks signals no longer active as
-- cleared_at = now(), so a scrip that clears and re-enters re-alerts.
CREATE TABLE IF NOT EXISTS alert_dispatch_log (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    signal_key    TEXT NOT NULL,
    scrip         VARCHAR(20) NOT NULL,
    alert_type    TEXT NOT NULL,                        -- 'spec' | 'accum' | 'conc'
    level         TEXT,                                 -- 'HIGH' | 'FLAG' | ...
    score         DOUBLE PRECISION,
    title         TEXT,
    detail        TEXT,
    recipients    TEXT[] NOT NULL DEFAULT '{}',
    subject       TEXT,
    mode          TEXT NOT NULL DEFAULT 'incremental',  -- 'incremental' | 'digest'
    status        TEXT NOT NULL DEFAULT 'sent',         -- 'sent' | 'failed' | 'skipped'
    error         TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at       TIMESTAMPTZ,
    cleared_at    TIMESTAMPTZ
);
-- At most one ACTIVE row per signal — the dedup guard.
CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_active_signal
    ON alert_dispatch_log (signal_key) WHERE cleared_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_alert_dispatch_recent ON alert_dispatch_log (first_seen_at DESC);
CREATE INDEX IF NOT EXISTS ix_alert_dispatch_scrip  ON alert_dispatch_log (scrip);

-- Seed the CEO as the default recipient (idempotent).
INSERT INTO alert_recipients (email, name, role)
VALUES ('xudip12@gmail.com', 'CEO', 'ceo')
ON CONFLICT (email) DO NOTHING;
