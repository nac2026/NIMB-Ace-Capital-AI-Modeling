"""Speculation-alert evaluation + email dispatch.

Reads the fresh broker-flow serving tables (speculation_score,
broker_accumulation, broker_concentration_daily), decides which signals are
NEW vs already-notified (via alert_dispatch_log), resolves recipients
(alert_recipients ∪ scrip_assignments) and sends email through the
nrc_notifications EmailSender.

Two modes:
  • incremental — urgent: email only NEW/escalated signals (deduped); used by the
    intraday loop and the Dagster floorsheet tail. One email per scrip so the
    assigned member is addressed alongside the standing recipients.
  • digest      — daily recap: one email of ALL currently-active signals to the
    standing recipients + every assignee.

Kept SQL-only (PostgresClient) + nrc_notifications; no DuckDB needed at call time.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from nrc_notifications import (
    AlertItem,
    EmailSender,
    render_digest,
    render_internal_urgent,
    render_urgent,
)
from nrc_storage import PostgresClient

_log = logging.getLogger("nrc_processing.speculation_alerts")

# Cap so a pathological day can't produce a giant email / write storm.
_MAX_ITEMS = 60


# ---------------------------------------------------------------- evaluation
def _top_brokers(pg: PostgresClient) -> dict[str, dict]:
    """Per-scrip dominant broker (largest cumulative volume share) — for naming
    the broker in plain-English alert text."""
    rows = pg.fetch_all(
        """
        SELECT DISTINCT ON (scrip) scrip, broker, volume_share
        FROM broker_accumulation
        ORDER BY scrip, volume_share DESC NULLS LAST
        """
    )
    return {r["scrip"]: r for r in rows}


# Only alert on real equities (the scrips master excludes debentures/bonds,
# whose thin trading trips concentration by nature). Floor + cap below keep the
# alert set bounded and meaningful regardless of how the market looks that day.
_SPEC_FLOOR = 45.0   # ELEVATED and above
_SPEC_TOP_N = 10     # the most-suspicious N equities


def _evaluate_spec(pg: PostgresClient, top_brokers: dict[str, dict]) -> list[AlertItem]:
    """The N most-suspicious equities by composite speculation score (ranked,
    not a raw threshold flood). HIGH (>=70) → 'HIGH RISK'; ELEVATED (45-69) →
    'WATCH'. Always bounded to _SPEC_TOP_N."""
    rows = pg.fetch_all(
        """
        SELECT sp.scrip, s.company_name, s.sector,
               sp.speculation_score AS score, sp.speculation_tier AS tier,
               sp.c_concentration, sp.c_circular, sp.c_accumulation, sp.has_self_trade
        FROM speculation_score sp JOIN scrips s USING (scrip)
        WHERE s.is_active AND sp.speculation_score >= %s
        ORDER BY sp.speculation_score DESC
        LIMIT %s
        """,
        (_SPEC_FLOOR, _SPEC_TOP_N),
    )
    items: list[AlertItem] = []
    for r in rows:
        is_high = (r.get("tier") == "HIGH") or (r.get("score") or 0) >= 70
        tb = top_brokers.get(r["scrip"])
        broker = tb["broker"] if tb else None
        vs = float(tb["volume_share"]) if tb and tb.get("volume_share") is not None else None

        wash = (r.get("c_circular") or 0) > 0.2
        self_trade = bool(r.get("has_self_trade"))
        # Severity (3-tier, matches the alert-email design): a single broker
        # holding half the volume is CRITICAL; wash/self-trades or >=40% is
        # ELEVATED; otherwise WATCH.
        if (vs or 0) >= 0.50:
            severity = "critical"
        elif (vs or 0) >= 0.40 or wash or self_trade:
            severity = "elevated"
        else:
            severity = "watch"

        patterns: list[str] = []
        if wash:
            patterns.append("Matched (wash) trades")
        if self_trade:
            patterns.append("Self-trades")
        if not patterns:
            patterns.append("Concentration")

        # Plain-text detail (used in the text/fallback body).
        lead = (f"Broker #{broker} is the dominant trader ({vs*100:.0f}% of all volume)"
                if (broker is not None and vs) else "Trading is unusually concentrated")
        pat = [p.lower() for p in patterns if p != "Concentration"]
        why = (", with " + " and ".join(pat)) if pat else ""
        tail = "patterns consistent with price manipulation." if is_high else "worth watching for manipulation."
        detail = f"{lead}{why} — {tail}"

        items.append(AlertItem(
            scrip=r["scrip"], company_name=r.get("company_name"), sector=r.get("sector"),
            kind="Speculation risk", alert_type="spec",
            level="HIGH" if is_high else "WATCH",
            title="High manipulation risk" if is_high else "Elevated manipulation risk",
            detail=detail, score=r.get("score"),
            signal_key=f"spec:{r['scrip']}:{'HIGH' if is_high else 'WATCH'}",
            broker=broker, volume_share=vs, patterns=patterns, severity=severity,
        ))
    # Rank by single-broker concentration (the email is "by concentration").
    items.sort(key=lambda it: (-(it.volume_share or 0), -(it.score or 0)))
    return items


def _evaluate_accum(pg: PostgresClient) -> list[AlertItem]:
    rows = pg.fetch_all(
        """
        SELECT ba.scrip, s.company_name, s.sector, ba.broker,
               ba.volume_share, ba.days_net_buy, ba.days_active, ba.cum_net_qty
        FROM broker_accumulation ba JOIN scrips s USING (scrip)
        WHERE s.is_active AND ba.accumulation_flag
        ORDER BY ba.volume_share DESC
        LIMIT %s
        """,
        (_MAX_ITEMS,),
    )
    items: list[AlertItem] = []
    for r in rows:
        vs = (r.get("volume_share") or 0) * 100
        detail = (
            f"Broker #{r['broker']} is quietly building a position — has bought {vs:.0f}% of "
            f"all volume and was a net buyer on {r.get('days_net_buy') or 0} of "
            f"{r.get('days_active') or 0} trading days."
        )
        items.append(AlertItem(
            scrip=r["scrip"], company_name=r.get("company_name"), sector=r.get("sector"),
            kind="Broker accumulation", alert_type="accum", level="FLAG",
            title=f"Broker #{r['broker']} accumulating",
            detail=detail, score=None,
            signal_key=f"accum:{r['scrip']}:{r['broker']}",
        ))
    return items


def _evaluate_conc(pg: PostgresClient) -> list[AlertItem]:
    # Pull the flagged scrips AND the actual top buyer/seller broker for that day,
    # so the alert can name the broker instead of an abstract "top-1 share".
    rows = pg.fetch_all(
        """
        WITH latest AS (SELECT max(trade_date) AS d FROM broker_concentration_daily)
        SELECT bc.scrip, s.company_name, s.sector, bc.n_brokers,
               bc.top1_buy_share, bc.top3_buy_share, bc.top1_sell_share, bc.top3_sell_share,
               tb.broker AS top_buy_broker, ts.broker AS top_sell_broker
        FROM broker_concentration_daily bc JOIN scrips s USING (scrip), latest
        LEFT JOIN LATERAL (
            SELECT broker FROM broker_flow_daily f, latest
            WHERE f.scrip = bc.scrip AND f.trade_date = latest.d
            ORDER BY f.buy_qty DESC NULLS LAST LIMIT 1
        ) tb ON TRUE
        LEFT JOIN LATERAL (
            SELECT broker FROM broker_flow_daily f, latest
            WHERE f.scrip = bc.scrip AND f.trade_date = latest.d
            ORDER BY f.sell_qty DESC NULLS LAST LIMIT 1
        ) ts ON TRUE
        WHERE s.is_active AND bc.concentration_flag AND bc.trade_date = latest.d
        ORDER BY GREATEST(bc.top1_buy_share, bc.top1_sell_share) DESC
        LIMIT %s
        """,
        (_MAX_ITEMS,),
    )
    items: list[AlertItem] = []
    for r in rows:
        is_buy = (r.get("top1_buy_share") or 0) >= (r.get("top1_sell_share") or 0)
        side = "buying" if is_buy else "selling"
        t1 = (r.get("top1_buy_share" if is_buy else "top1_sell_share") or 0) * 100
        t3 = (r.get("top3_buy_share" if is_buy else "top3_sell_share") or 0) * 100
        broker = r.get("top_buy_broker") if is_buy else r.get("top_sell_broker")
        n = r.get("n_brokers") or 0
        who = f"Broker #{broker}" if broker is not None else "One broker"
        detail = (
            f"{who} did {t1:.0f}% of all {side} today, and the top 3 brokers did {t3:.0f}% "
            f"(out of {n} active) — {side} is dominated by very few hands."
        )
        items.append(AlertItem(
            scrip=r["scrip"], company_name=r.get("company_name"), sector=r.get("sector"),
            kind="Broker concentration", alert_type="conc", level="FLAG",
            title=f"{side.title()} concentrated in few brokers",
            detail=detail, score=None,
            signal_key=f"conc:{r['scrip']}",
        ))
    return items


def _sev(x: float, hi: float, mid: float) -> str:
    return "critical" if x >= hi else "elevated" if x >= mid else "watch"


_PER_TYPE = 10  # bound each detector


def evaluate_dist(pg: PostgresClient) -> list[AlertItem]:
    """Distribution / exit-liquidity — a broker offloading a built-up position,
    with the position timeline (when they started accumulating / flipped)."""
    rows = pg.fetch_all(
        """SELECT ba.scrip, s.company_name, s.sector, ba.broker, ba.volume_share,
                  ba.days_net_sell, ba.days_active,
                  bp.accum_start_date, bp.peak_date, bp.dist_start_date
           FROM broker_accumulation ba JOIN scrips s USING (scrip)
           LEFT JOIN broker_position bp ON bp.scrip = ba.scrip AND bp.broker = ba.broker
           WHERE s.is_active AND ba.distribution_flag
           ORDER BY ba.volume_share DESC NULLS LAST LIMIT %s""",
        (_PER_TYPE,),
    )
    out = []
    for r in rows:
        vs = float(r.get("volume_share") or 0)
        since = f" Accumulating since {r['accum_start_date']}." if r.get("accum_start_date") else ""
        flip = f" Started distributing {r['dist_start_date']}." if r.get("dist_start_date") else ""
        out.append(AlertItem(
            scrip=r["scrip"], company_name=r.get("company_name"), sector=r.get("sector"),
            kind="Distribution", alert_type="dist", level="WATCH",
            title="Broker distributing into the market",
            detail=(f"Broker #{r['broker']} is offloading — {vs*100:.0f}% of all volume, "
                    f"net seller on {r.get('days_net_sell') or 0} of {r.get('days_active') or 0} days.{since}{flip} "
                    f"Possible exit-liquidity / distribution phase."),
            score=round(min(100, vs * 100 * 1.4)), broker=r["broker"], volume_share=vs,
            patterns=["Distribution"], severity=_sev(vs, 0.50, 0.40),
            signal_key=f"dist:{r['scrip']}:{r['broker']}",
        ))
    return out


def evaluate_ring(pg: PostgresClient) -> list[AlertItem]:
    """Circular / wash ring — two brokers recycling shares (or self-trades)."""
    rows = pg.fetch_all(
        """SELECT g.scrip, s.company_name, s.sector, g.broker_lo, g.broker_hi,
                  g.circular_score, g.self_trade, g.reciprocal_balance, g.pair_volume_share
           FROM broker_pair_graph g JOIN scrips s USING (scrip)
           WHERE s.is_active AND g.circular_score >= 0.20
           ORDER BY g.circular_score DESC LIMIT %s""",
        (_PER_TYPE,),
    )
    out = []
    for r in rows:
        cs = float(r.get("circular_score") or 0)
        rb = float(r.get("reciprocal_balance") or 0)
        if r.get("self_trade") and r["broker_lo"] == r["broker_hi"]:
            detail = (f"Broker #{r['broker_lo']} is trading with itself (self-trades) — "
                      f"circular score {cs:.0%}. Fabricated volume / price-setting risk.")
        else:
            detail = (f"Brokers #{r['broker_lo']} and #{r['broker_hi']} are passing shares "
                      f"back-and-forth (reciprocal balance {rb:.0%}, circular score {cs:.0%}) — wash-trade pattern.")
        out.append(AlertItem(
            scrip=r["scrip"], company_name=r.get("company_name"), sector=r.get("sector"),
            kind="Wash / circular", alert_type="ring", level="WATCH",
            title="Circular / wash trading detected", detail=detail,
            score=round(cs * 100), broker=r["broker_lo"],
            patterns=["Self-trades"] if r.get("self_trade") else ["Matched (wash) trades"],
            severity=_sev(cs, 0.60, 0.40),
            signal_key=f"ring:{r['scrip']}:{r['broker_lo']}-{r['broker_hi']}",
        ))
    return out


def evaluate_insider(pg: PostgresClient) -> list[AlertItem]:
    """Pre-event accumulation — a broker built a position around a price-sensitive
    corporate action (dividend/bonus/rights). Heuristic flag for review."""
    rows = pg.fetch_all(
        """WITH ra AS (
               SELECT scrip, action_type, announcement_date FROM corporate_actions
               WHERE announcement_date IS NOT NULL AND announcement_date >= CURRENT_DATE - 365
           )
           SELECT DISTINCT ON (ba.scrip, ba.broker)
                  ba.scrip, s.company_name, s.sector, ba.broker, ba.volume_share,
                  ra.action_type, ra.announcement_date
           FROM broker_accumulation ba JOIN scrips s USING (scrip)
           JOIN ra ON ra.scrip = ba.scrip
           WHERE s.is_active AND ba.accumulation_flag
                 AND ba.first_day <= ra.announcement_date
                 AND ba.last_day  >= ra.announcement_date - 45
           ORDER BY ba.scrip, ba.broker, ba.volume_share DESC
           LIMIT %s""",
        (_PER_TYPE,),
    )
    out = []
    for r in rows:
        vs = float(r.get("volume_share") or 0)
        act = (r.get("action_type") or "corporate action").replace("_", " ")
        ann = r.get("announcement_date")
        out.append(AlertItem(
            scrip=r["scrip"], company_name=r.get("company_name"), sector=r.get("sector"),
            kind="Pre-event accumulation", alert_type="insider", level="WATCH",
            title="Accumulation around a corporate action",
            detail=(f"Broker #{r['broker']} accumulated {vs*100:.0f}% of volume around the "
                    f"{act} announced {ann} — review for information-led trading."),
            score=round(min(100, vs * 100 + 25)), broker=r["broker"], volume_share=vs,
            patterns=["Pre-event"], severity=_sev(vs, 0.40, 0.25),
            signal_key=f"insider:{r['scrip']}:{ann}:{r['broker']}",
        ))
    return out


def evaluate_pump(pg: PostgresClient) -> list[AlertItem]:
    """Pump-and-dump — a sharp run-up (pump) or a run-up now falling hard from its
    peak (the dump). Quiet when the market is flat."""
    rows = pg.fetch_all(
        """SELECT pr.scrip, s.company_name, s.sector,
                  pr.return_1m, pr.return_3m, pr.drawdown_from_peak
           FROM price_returns pr JOIN scrips s USING (scrip)
           WHERE s.is_active AND (
                 pr.return_1m >= 0.25
              OR (pr.return_3m >= 0.40 AND pr.drawdown_from_peak <= -0.20))
           ORDER BY GREATEST(COALESCE(pr.return_1m,0), COALESCE(pr.return_3m,0)) DESC
           LIMIT %s""",
        (_PER_TYPE,),
    )
    out = []
    for r in rows:
        r1m = float(r.get("return_1m") or 0)
        r3m = float(r.get("return_3m") or 0)
        dd = float(r.get("drawdown_from_peak") or 0)
        dumping = r3m >= 0.40 and dd <= -0.20
        if dumping:
            detail = (f"Ran up {r3m*100:.0f}% over 3 months then fell {abs(dd)*100:.0f}% from its peak "
                      f"— classic pump-then-distribute. Exit-liquidity risk.")
            mag = r3m + abs(dd)
        else:
            detail = f"Up {r1m*100:.0f}% in a month on a sharp run — possible pump; watch for distribution."
            mag = r1m
        out.append(AlertItem(
            scrip=r["scrip"], company_name=r.get("company_name"), sector=r.get("sector"),
            kind="Pump-and-dump", alert_type="pump", level="WATCH",
            title="Pump-and-dump pattern" if dumping else "Sharp run-up (possible pump)",
            detail=detail, score=round(min(100, mag * 100)),
            patterns=["Dump phase"] if dumping else ["Run-up"],
            severity=_sev(mag, 0.60, 0.35), signal_key=f"pump:{r['scrip']}",
        ))
    return out


def evaluate_volume(pg: PostgresClient) -> list[AlertItem]:
    """Abnormal volume / overbought with no news to justify it."""
    rows = pg.fetch_all(
        """WITH latest AS (SELECT scrip, max(date) d FROM indicators_daily GROUP BY scrip)
           SELECT i.scrip, s.company_name, s.sector, i.date, i.rsi_14,
                  db.volume, i.volume_sma_20,
                  (db.volume / NULLIF(i.volume_sma_20,0)) AS ratio
           FROM indicators_daily i
           JOIN latest l ON i.scrip = l.scrip AND i.date = l.d
           JOIN daily_bars db ON db.scrip = i.scrip AND db.date = i.date
           JOIN scrips s ON s.scrip = i.scrip AND s.is_active
           WHERE i.volume_sma_20 > 0 AND (db.volume / i.volume_sma_20) >= 3.0
             AND NOT EXISTS (
                 SELECT 1 FROM news_articles n
                 WHERE i.scrip = ANY(n.scrip_tags) AND n.published_at >= CURRENT_DATE - 5)
           ORDER BY ratio DESC LIMIT %s""",
        (_PER_TYPE,),
    )
    out = []
    for r in rows:
        ratio = float(r.get("ratio") or 0)
        rsi = float(r.get("rsi_14") or 0)
        out.append(AlertItem(
            scrip=r["scrip"], company_name=r.get("company_name"), sector=r.get("sector"),
            kind="Abnormal volume", alert_type="volume", level="WATCH",
            title="Unusual volume, no news",
            detail=(f"Volume {ratio:.1f}× the 20-day average"
                    + (f", RSI {rsi:.0f} (overbought)" if rsi >= 70 else "")
                    + " — spike with no news on the tape."),
            score=round(min(100, ratio * 20 + (rsi - 50 if rsi > 50 else 0))),
            patterns=["Volume spike"], severity=_sev(ratio, 5.0, 3.0),
            signal_key=f"volume:{r['scrip']}:{r['date']}",
        ))
    return out


# ------------------------------------------------- internal trade surveillance
# Our OWN fills flagged by the five-lens scoring (internal_trade_surveillance),
# grouped into fund × scrip × day cases — the same grain as the /surveillance
# board, so one alert == one case card. The trade-date window keeps reconcile
# stable: a case ages out of the detection set once (cleared, no re-alert) and
# can never reappear because its trade_date is fixed.
_SURV_MIN_SCORE = 25.0     # MODERATE and above — mirrors the board's case floor
_SURV_WINDOW_DAYS = 21
_SURV_MAX_CASES = 30


def evaluate_internal_surv(pg: PostgresClient) -> list[AlertItem]:
    """New internal-trade surveillance cases — emailed whenever fresh trade-book
    or floor-sheet data lands and the scoring flags one of our own fills."""
    rows = pg.fetch_all(
        """SELECT t.client_code, t.client_name, t.scrip, sc.company_name, sc.sector,
                  t.trade_date, t.side, t.our_qty, t.our_value,
                  t.surveillance_score, t.counterparty_broker, t.cp_surprise_z,
                  t.exit_liquidity_flag, t.cross_flag, t.churn_flag,
                  t.bought_near_peak_flag, t.worse_than_range_flag
           FROM internal_trade_surveillance t
           LEFT JOIN scrips sc ON sc.scrip = t.scrip
           WHERE t.surveillance_score >= %s
             AND t.trade_date >= CURRENT_DATE - %s
           ORDER BY t.trade_date, t.scrip""",
        (_SURV_MIN_SCORE, _SURV_WINDOW_DAYS),
    )
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["client_code"], r["scrip"], str(r["trade_date"]))].append(r)

    items: list[AlertItem] = []
    for (code, scrip, day), grp in groups.items():
        score = max(float(g["surveillance_score"] or 0) for g in grp)
        tier = "HIGH" if score >= 70 else "ELEVATED" if score >= 45 else "MODERATE"
        fund = (grp[0].get("client_name") or code).strip()
        qty = sum(float(g["our_qty"] or 0) for g in grp)
        val = sum(float(g["our_value"] or 0) for g in grp)
        sides = {g["side"] for g in grp}
        action = "bought" if sides == {"B"} else "sold" if sides == {"S"} else "traded"

        # Dominant counterparty across the case's fills (by our quantity faced).
        by_cp: dict[int, float] = defaultdict(float)
        for g in grp:
            if g.get("counterparty_broker") is not None:
                by_cp[g["counterparty_broker"]] += float(g["our_qty"] or 0)
        top_cp = max(by_cp, key=by_cp.__getitem__) if by_cp else None
        cp_share = (by_cp[top_cp] / qty) if (top_cp is not None and qty > 0) else None
        z = max((float(g["cp_surprise_z"]) for g in grp
                 if g.get("cp_surprise_z") is not None), default=None)

        patterns: list[str] = []
        if any(g.get("exit_liquidity_flag") for g in grp):
            patterns.append("Exit liquidity")
        if any(g.get("cross_flag") for g in grp):
            patterns.append("Intra-firm cross")
        if any(g.get("churn_flag") for g in grp):
            patterns.append("Churn")
        if any(g.get("bought_near_peak_flag") for g in grp):
            patterns.append("Bought near peak")
        if any(g.get("worse_than_range_flag") for g in grp):
            patterns.append("Outside day range")
        if z is not None and z >= 3:
            patterns.append("Repeat counterparty")
        if not patterns:
            patterns.append("Composite score")

        cp_txt = ""
        if top_cp is not None and cp_share:
            cp_txt = f" {cp_share * 100:.0f}% of the flow faced broker #{top_cp}"
            if z is not None and z >= 2:
                cp_txt += f" (surprise z={z:.1f})"
            cp_txt += "."
        detail = (
            f"{fund} {action} {qty:,.0f} {scrip} (Rs {val:,.0f}) across {len(grp)} "
            f"flagged fill(s) on {day} — surveillance score {score:.0f} ({tier})."
            f"{cp_txt} Review the case on the surveillance board."
        )
        items.append(AlertItem(
            scrip=scrip, company_name=grp[0].get("company_name"), sector=grp[0].get("sector"),
            kind="Internal trade", alert_type="surv",
            level="HIGH" if tier == "HIGH" else "WATCH",
            title=f"{tier.title()} internal-trade case — {fund.title()}",
            detail=detail, score=round(score),
            broker=top_cp, volume_share=cp_share, patterns=patterns,
            severity="critical" if tier == "HIGH" else "elevated" if tier == "ELEVATED" else "watch",
            signal_key=f"surv:{code}:{scrip}:{day}",
            tags=[fund.title(), tier, day],
        ))
    items.sort(key=lambda it: -(it.score or 0))
    return items[:_SURV_MAX_CASES]


# Detectors that feed the /alerts board. Types in EMAIL_TYPES are emailed:
# `spec` rides the market-surveillance urgent/digest emails; `surv` (our own
# trades) goes out as its own internal-surveillance email, incremental-only —
# cases never clear daily, so repeating them in every digest would be noise.
EMAIL_TYPES = {"spec", "surv"}


def detect_all(pg: PostgresClient) -> list[AlertItem]:
    """Run every detector — the full surveillance board (all types)."""
    top_brokers = _top_brokers(pg)
    return (
        _evaluate_spec(pg, top_brokers)
        + evaluate_pump(pg)
        + evaluate_insider(pg)
        + evaluate_ring(pg)
        + evaluate_volume(pg)
        + evaluate_dist(pg)
        + evaluate_internal_surv(pg)
    )


# Back-compat: a few call sites import `evaluate`.
def evaluate(pg: PostgresClient) -> list[AlertItem]:
    return detect_all(pg)


# ---------------------------------------------------------------- recipients
def _global_recipients(pg: PostgresClient) -> list[str]:
    rows = pg.fetch_all("SELECT email FROM alert_recipients WHERE is_active")
    return [r["email"] for r in rows]


def _assignees(pg: PostgresClient, scrip: str) -> list[str]:
    rows = pg.fetch_all("SELECT email FROM scrip_assignments WHERE scrip = %s", (scrip,))
    return [r["email"] for r in rows]


def _active_keys(pg: PostgresClient) -> set[str]:
    rows = pg.fetch_all("SELECT signal_key FROM alert_dispatch_log WHERE cleared_at IS NULL")
    return {r["signal_key"] for r in rows}


# ---------------------------------------------------------------- reconcile
def reconcile(pg: PostgresClient, items: list[AlertItem], now) -> list[AlertItem]:
    """Single owner of alert_dispatch_log across ALL detector types. Clears
    active rows whose signal is no longer present; inserts newly-detected
    signals (status='detected', no email). Returns the newly-inserted items.
    This is what populates the /alerts board — independent of email."""
    by_key = {it.signal_key: it for it in items}
    active = _active_keys(pg)
    gone = active - set(by_key)
    if gone:
        pg.execute(
            "UPDATE alert_dispatch_log SET cleared_at = %s WHERE cleared_at IS NULL AND signal_key = ANY(%s)",
            (now, list(gone)),
        )
    new_items = [it for k, it in by_key.items() if k not in active]
    for it in new_items:
        pg.execute(
            """INSERT INTO alert_dispatch_log
                   (signal_key, scrip, alert_type, level, score, title, detail, recipients, subject, mode, status, first_seen_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, '{}', NULL, 'detect', 'detected', %s)
               ON CONFLICT (signal_key) WHERE cleared_at IS NULL DO NOTHING""",
            (it.signal_key, it.scrip, it.alert_type, it.level, it.score, it.title, it.detail, now),
        )
    return new_items


# ---------------------------------------------------------------- dispatch
def dispatch(
    pg: PostgresClient,
    sender: EmailSender | None = None,
    *,
    mode: str = "incremental",
    web_base: str = "http://localhost:3000",
) -> dict:
    """Detect ALL types, persist them to the board (reconcile), then EMAIL only
    the types in EMAIL_TYPES (currently {'spec'}). Other types appear on the
    /alerts page but are not emailed. Returns a report dict."""
    sender = sender or EmailSender()
    now = datetime.now(timezone.utc)
    # Keep broker position timeline/phases fresh (cheap window queries) so the
    # distribution detail + floor-sheet tab show current "since/flipped" dates.
    try:
        from .broker_positions import refresh_broker_positions
        refresh_broker_positions(pg)
    except Exception as e:  # noqa: BLE001
        _log.warning("broker position refresh failed: %s", e)
    items = detect_all(pg)
    new_items = reconcile(pg, items, now)

    globals_ = _global_recipients(pg)
    scanned = (pg.fetch_one(
        "SELECT count(*) c FROM speculation_score sp JOIN scrips s USING (scrip) WHERE s.is_active"
    ) or {}).get("c")

    by_type: dict[str, int] = {}
    for it in items:
        by_type[it.alert_type] = by_type.get(it.alert_type, 0) + 1

    if mode == "digest":
        # Digest recaps the MARKET book only — internal cases stay incremental
        # (they never clear day-to-day, so a digest would repeat them forever).
        email_items = [it for it in items if it.alert_type in EMAIL_TYPES and it.alert_type != "surv"]
        rep = _dispatch_digest(pg, sender, email_items, globals_, now, web_base, scanned)
    else:
        new_email = [it for it in new_items if it.alert_type in EMAIL_TYPES]
        market = [it for it in new_email if it.alert_type != "surv"]
        internal = [it for it in new_email if it.alert_type == "surv"]
        rep = _dispatch_incremental(pg, sender, market, globals_, now, web_base, scanned)
        if internal:
            rep["internal"] = _dispatch_internal(pg, sender, internal, globals_, now, web_base)
    rep["detected_total"] = len(items)
    rep["by_type"] = by_type
    rep["new_detected"] = len(new_items)
    return rep


def _dispatch_incremental(pg, sender, new_email, globals_, now, web_base, scanned=None) -> dict:
    if not new_email:
        return {"mode": "incremental", "new": 0, "emails_sent": 0}
    # ONE consolidated email for all newly-detected EMAILABLE signals.
    recipients = set(globals_)
    for sc in {it.scrip for it in new_email}:
        recipients.update(_assignees(pg, sc))
    recipients = sorted(recipients)

    subject, html, text = render_urgent(new_email, web_base=web_base, scanned=scanned)
    status, error = "sent", None
    sent_count = 0
    try:
        ok = sender.send(subject=subject, html=html, text=text, to=recipients)
        status = "sent" if ok else "skipped"
        sent_count = 1 if ok else 0
    except Exception as e:  # noqa: BLE001
        status, error = "failed", str(e)
        _log.warning("urgent alert send failed: %s", e)
    # Promote the already-detected rows to 'sent' with recipients/subject.
    for it in new_email:
        pg.execute(
            """UPDATE alert_dispatch_log SET status = %s, recipients = %s, subject = %s, error = %s, sent_at = %s
               WHERE signal_key = %s AND cleared_at IS NULL""",
            (status, recipients, subject, error, now, it.signal_key),
        )
    return {"mode": "incremental", "new": len(new_email), "emails_sent": sent_count}


def _dispatch_internal(pg, sender, new_cases, globals_, now, web_base) -> dict:
    """One consolidated internal-surveillance email for all NEW cases — its own
    template (fund/side/notional framing, links to /surveillance), separate from
    the market-manipulation email so stakeholders can route/filter them apart."""
    recipients = set(globals_)
    for sc in {it.scrip for it in new_cases}:
        recipients.update(_assignees(pg, sc))
    recipients = sorted(recipients)

    subject, html, text = render_internal_urgent(new_cases, web_base=web_base)
    status, error = "sent", None
    sent_count = 0
    try:
        ok = sender.send(subject=subject, html=html, text=text, to=recipients)
        status = "sent" if ok else "skipped"
        sent_count = 1 if ok else 0
    except Exception as e:  # noqa: BLE001
        status, error = "failed", str(e)
        _log.warning("internal-surveillance alert send failed: %s", e)
    for it in new_cases:
        pg.execute(
            """UPDATE alert_dispatch_log SET status = %s, recipients = %s, subject = %s, error = %s, sent_at = %s
               WHERE signal_key = %s AND cleared_at IS NULL""",
            (status, recipients, subject, error, now, it.signal_key),
        )
    return {"new_cases": len(new_cases), "emails_sent": sent_count, "status": status}


def _dispatch_digest(pg, sender, items, globals_, now, web_base, scanned=None) -> dict:
    if not items:
        return {"mode": "digest", "active": 0, "emails_sent": 0}
    # Everyone on the standing list plus every assignee gets the daily recap.
    assignees: set[str] = set()
    for sc in {it.scrip for it in items}:
        assignees.update(_assignees(pg, sc))
    recipients = sorted(set(globals_) | assignees)
    as_of = now.astimezone().date().isoformat()
    subject, html, text = render_digest(items, as_of, web_base=web_base, scanned=scanned)
    sent = 0
    status, error = "sent", None
    try:
        ok = sender.send(subject=subject, html=html, text=text, to=recipients)
        status = "sent" if ok else "skipped"
        sent = 1 if ok else 0
    except Exception as e:  # noqa: BLE001
        status, error = "failed", str(e)
        _log.warning("digest send failed: %s", e)
    # One audit row for the digest (does not participate in the active dedup set).
    pg.execute(
        """INSERT INTO alert_dispatch_log
               (signal_key, scrip, alert_type, level, title, recipients, subject, mode, status, error, sent_at, cleared_at)
           VALUES (%s, %s, 'digest', NULL, %s, %s, %s, 'digest', %s, %s, %s, %s)""",
        (f"digest:{as_of}:{now.strftime('%H%M%S')}", "-", f"Daily digest — {len(items)} active",
         recipients, subject, status, error, now, now),
    )
    return {"mode": "digest", "active": len(items), "recipients": len(recipients), "emails_sent": sent}


def _log_signal(pg, it: AlertItem, recipients, subject, mode, status, error, now) -> None:
    """Insert an ACTIVE dispatch row for a new signal (dedup via the partial
    unique index on signal_key WHERE cleared_at IS NULL)."""
    pg.execute(
        """INSERT INTO alert_dispatch_log
               (signal_key, scrip, alert_type, level, score, title, detail, recipients, subject, mode, status, error, sent_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (signal_key) WHERE cleared_at IS NULL DO NOTHING""",
        (it.signal_key, it.scrip, it.alert_type, it.level, it.score, it.title, it.detail,
         recipients, subject, mode, status, error, now),
    )


def recent(pg: PostgresClient, limit: int = 30, active_only: bool = False) -> list[dict]:
    """Recent dispatched alerts for the UI bell feed + /alerts page (enriched
    with company/sector). Excludes digest audit rows."""
    where = "WHERE l.mode <> 'digest'" + (" AND l.cleared_at IS NULL" if active_only else "")
    return pg.fetch_all(
        f"""SELECT l.signal_key, l.scrip, s.company_name, s.sector,
                   l.alert_type, l.level, l.score, l.title, l.detail, l.mode, l.status,
                   l.first_seen_at, l.sent_at, l.cleared_at
            FROM alert_dispatch_log l
            LEFT JOIN scrips s ON s.scrip = l.scrip
            {where}
            ORDER BY (l.cleared_at IS NULL) DESC, l.first_seen_at DESC
            LIMIT %s""",
        (limit,),
    )
