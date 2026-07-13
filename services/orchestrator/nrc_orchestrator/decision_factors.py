"""Decision-quality lenses + the integrated trade verdict.

The fill-level surveillance score (dbt `internal_trade_surveillance`) judges a trade
on MICROSTRUCTURE only — execution slippage, market manipulation, counterparty
collusion, intra-firm cross/churn, post-trade markout. That answers "does the trade
look manipulative or badly executed?" but NOT "was buying this stock, at that price,
on that day, a sound decision given the company and the chart?".

This module adds the missing investment-merit lenses and fuses everything into ONE
verdict, the way an analyst would: it looks through every lens — fundamentals,
technicals, plus the microstructure components already computed upstream — weighs
them together (re-normalising over whatever data is actually available), and escalates
when several independent lenses light up at once. Computed per case at build time
(few flagged cases, all serving tables are point-in-time), mirroring `_market_context`.

Point-in-time discipline: fundamentals are selected as of the most recent quarter whose
results would already be PUBLIC on the trade date (quarter end + a publication lag), so
a trade is never judged against numbers that did not yet exist when it was placed.

Lenses are SIDE-AWARE: buying a fundamentally weak / technically over-extended name is
concerning; selling one is usually prudent, so the same evidence scores differently for
a BUY than a SELL."""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from nrc_storage import PostgresClient

_log = logging.getLogger("nrc_orchestrator.decision_factors")

# Quarterly results are filed weeks after quarter-end; require the quarter to be
# this many days past its (approx) end before we treat it as known at trade time.
_PUBLISH_LAG_DAYS = 45
# BS fiscal-year start year = AD start year + 57 (Shrawan ≈ mid-July). See
# nrc_nepal.fiscal_year for the full convention.
_BS_TO_AD_OFFSET = 57


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _quarter_end_ad(fiscal_year_bs: int, quarter: int) -> _dt.date:
    """Approx Gregorian end date of a BS fiscal quarter (mid-month boundaries).

    Q1≈mid-Oct, Q2≈mid-Jan, Q3≈mid-Apr, Q4≈mid-Jul. Good to a few days — enough
    to order quarters against a trade date with a publication lag on top."""
    ad_start = fiscal_year_bs - _BS_TO_AD_OFFSET
    return {
        1: _dt.date(ad_start, 10, 15),
        2: _dt.date(ad_start + 1, 1, 15),
        3: _dt.date(ad_start + 1, 4, 15),
        4: _dt.date(ad_start + 1, 7, 15),
    }[quarter]


def _as_date(d: Any) -> _dt.date | None:
    if isinstance(d, _dt.date):
        return d
    if isinstance(d, str) and len(d) >= 10:
        try:
            return _dt.date.fromisoformat(d[:10])
        except ValueError:
            return None
    return None


# ------------------------------------------------------------------ fundamental lens

def fundamental_factor(
    pg: PostgresClient, scrip: str, trade_date: Any, side: str
) -> dict | None:
    """Point-in-time fundamental health of the company on the trade date.

    Built on `fundamental_quality_composite` (a sector-relative 0-100 quality score
    with profitability / asset-quality / growth / capital / efficiency / Piotroski
    pillars), hardened with the `stage2_bank_screen` stress flags (NPL_HIGH, CAR_LOW,
    LOSS, ...) and a few raw ratios for the narrative.

    Returns a side-aware concern score in [0,1] (BUY of a weak name scores high; SELL
    scores ~0), the readable posture, and the underlying numbers — or None when no
    quarter is known as of the trade date (lens then excluded from the verdict)."""
    td = _as_date(trade_date)
    if td is None:
        return None

    rows = pg.fetch_all(
        """
        SELECT fiscal_year_bs, quarter, quality_score_0_100, quality_tier,
               profitability_pct, asset_quality_pct, growth_pct, capital_pct,
               efficiency_pct, piotroski_pct
        FROM fundamental_quality_composite
        WHERE scrip = %s
        ORDER BY fiscal_year_bs DESC, quarter DESC
        """,
        (scrip,),
    )
    if not rows:
        return None

    # Most recent quarter publicly known on the trade date (quarter end + lag).
    chosen = next(
        (
            r for r in rows
            if _quarter_end_ad(r["fiscal_year_bs"], r["quarter"])
            + _dt.timedelta(days=_PUBLISH_LAG_DAYS) <= td
        ),
        None,
    )
    if chosen is None:
        return None

    fy, q = chosen["fiscal_year_bs"], chosen["quarter"]
    qs = chosen.get("quality_score_0_100")
    if qs is None:
        return None
    health = _clamp(float(qs) / 100.0)

    # Hard stress flags + raw ratios from the bank screen / raw snapshot (same quarter).
    screen = pg.fetch_all(
        "SELECT flags, npl_ratio, car, cd_ratio, roe FROM stage2_bank_screen "
        "WHERE scrip=%s AND fiscal_year_bs=%s AND quarter=%s",
        (scrip, fy, q),
    )
    flags = list(screen[0]["flags"]) if screen and screen[0].get("flags") else []
    # Hard distress (solvency / asset-quality / losses) weighs more and sets the
    # "Stressed" posture; soft flags (high CD, weak ROE) only nudge the score.
    hard = [f for f in flags if f in ("NPL_HIGH", "CAR_LOW", "LOSS")]
    soft = [f for f in flags if f in ("CD_HIGH", "ROE_LOW")]
    stress = hard + soft
    snap = pg.fetch_all(
        "SELECT npl_ratio, car, roe, pe_ratio, eps FROM fundamental_snapshots "
        "WHERE scrip=%s AND fiscal_year_bs=%s AND quarter=%s",
        (scrip, fy, q),
    )
    s0 = snap[0] if snap else {}

    def _pick(*vals):
        return next((v for v in vals if v is not None), None)

    # Ratios are stored as fractions (0.1341 = 13.41%); show as percent. P/E is a
    # raw multiple, left as-is.
    npl = _pick(screen[0]["npl_ratio"] if screen else None, s0.get("npl_ratio"))
    car = _pick(screen[0]["car"] if screen else None, s0.get("car"))
    roe = _pick(screen[0]["roe"] if screen else None, s0.get("roe"))
    pe = s0.get("pe_ratio")
    npl = float(npl) * 100 if npl is not None else None
    car = float(car) * 100 if car is not None else None
    roe = float(roe) * 100 if roe is not None else None
    pe = float(pe) if pe is not None else None

    # Profit trend (same quarter) + valuation vs peers — extra substance so the
    # fundamental lens reads with the same depth as the broker lens.
    growth = pg.fetch_all(
        "SELECT net_profit_yoy_pct FROM quarterly_growth "
        "WHERE scrip=%s AND fiscal_year_bs=%s AND quarter=%s",
        (scrip, fy, q),
    )
    profit_yoy = growth[0]["net_profit_yoy_pct"] if growth else None
    val = pg.fetch_all(
        "SELECT pe_trailing, pb, peer_pe_median, pe_vs_peer_pct FROM valuation "
        "WHERE scrip=%s AND date<=%s ORDER BY date DESC LIMIT 1",
        (scrip, td),
    )
    v0 = val[0] if val else {}

    stress_bump = min(0.30, 0.15 * len(hard) + 0.06 * len(soft))
    side = (side or "").upper()
    # BUY/CROSS of a weak name is the concern; selling a weak name is prudent, so the
    # merit lens barely fires on sells.
    score = _clamp(0.15 * (1.0 - health)) if side == "SELL" else _clamp((1.0 - health) + stress_bump)

    posture = "Healthy" if health >= 0.66 else "Mixed" if health >= 0.40 else "Stressed"
    if hard and side != "SELL":
        posture = "Stressed"

    bits = [f"quality {float(qs):.0f}/100 ({chosen.get('quality_tier') or posture})"]
    if npl is not None:
        bits.append(f"NPL {float(npl):.1f}%")
    if car is not None:
        bits.append(f"CAR {float(car):.1f}%")
    if roe is not None:
        bits.append(f"ROE {float(roe):.1f}%")
    if pe is not None:
        bits.append(f"P/E {float(pe):.1f}")
    if stress:
        bits.append("flags: " + ", ".join(stress))
    basis = f"Q{q} FY{fy}/{(fy + 1) % 100:02d}: " + ", ".join(bits)

    def _pct01(v):
        return round(float(v) * 100, 0) if v is not None else None

    return {
        "score": round(score, 3),
        "health": round(health, 3),
        "posture": posture,
        "tier": chosen.get("quality_tier"),
        "quality_score": round(float(qs), 0),
        "flags": stress,
        "fiscal_year_bs": fy,
        "quarter": q,
        "npl_ratio": float(npl) if npl is not None else None,
        "car": float(car) if car is not None else None,
        "roe": float(roe) if roe is not None else None,
        "pe_ratio": float(pe) if pe is not None else None,
        # Sector-relative quality pillars (percentiles, 0-100) + profit trend + valuation.
        "pillars": {
            "profitability": _pct01(chosen.get("profitability_pct")),
            "asset_quality": _pct01(chosen.get("asset_quality_pct")),
            "capital": _pct01(chosen.get("capital_pct")),
            "growth": _pct01(chosen.get("growth_pct")),
            "efficiency": _pct01(chosen.get("efficiency_pct")),
        },
        "profit_yoy_pct": float(profit_yoy) if profit_yoy is not None else None,
        "pe_vs_peer_pct": float(v0["pe_vs_peer_pct"]) if v0.get("pe_vs_peer_pct") is not None else None,
        "peer_pe": float(v0["peer_pe_median"]) if v0.get("peer_pe_median") is not None else None,
        "pb": float(v0["pb"]) if v0.get("pb") is not None else None,
        "basis": basis,
    }


# ------------------------------------------------------------------- technical lens

def technical_factor(
    pg: PostgresClient,
    scrip: str,
    trade_date: Any,
    side: str,
    *,
    price: float | None = None,
) -> dict | None:
    """Point-in-time entry quality on the trade date.

    Reads `indicators_daily` as of the trade date (RSI-14, SMA-20/50) and the trailing
    20-day close range, then locates the fill within it. BUY-side concern rises when the
    stock was bought near the top of its range (chasing), overbought (RSI>60), or
    stretched above its 20-day average; SELL-side concern rises on capitulation (sold
    near range low / oversold).

    Returns a side-aware concern score in [0,1] + readable posture, or None when no
    indicator data exists on/before the trade date."""
    td = _as_date(trade_date)
    if td is None:
        return None

    # As-of row (latest ≤ trade date) plus trailing 20-session range, SMA-50, and the
    # close ~21 sessions back (for 1-month momentum).
    rows = pg.fetch_all(
        """
        SELECT date, close, rsi_14, sma_20, sma_50, low_20, high_20, close_21 FROM (
            SELECT date, close, rsi_14, sma_20, sma_50,
                   MIN(close) OVER w AS low_20,
                   MAX(close) OVER w AS high_20,
                   LEAD(close, 21) OVER (ORDER BY date DESC) AS close_21
            FROM indicators_daily
            WHERE scrip = %s AND date <= %s
            WINDOW w AS (ORDER BY date DESC ROWS BETWEEN CURRENT ROW AND 19 FOLLOWING)
        ) q
        ORDER BY date DESC
        LIMIT 1
        """,
        (scrip, td),
    )
    if not rows:
        return None
    r = rows[0]
    rsi = r.get("rsi_14")
    sma20 = r.get("sma_20")
    sma50 = r.get("sma_50")
    close = r.get("close")
    low20, high20 = r.get("low_20"), r.get("high_20")
    close21 = r.get("close_21")
    dist_sma20 = (float(close) / float(sma20) - 1.0) if (close and sma20 and float(sma20) > 0) else None
    dist_sma50 = (float(close) / float(sma50) - 1.0) if (close and sma50 and float(sma50) > 0) else None
    mom_1m = (float(close) / float(close21) - 1.0) if (close and close21 and float(close21) > 0) else None

    # Where the fill sits in the trailing 20-day range (1.0 = at the high). Falls back
    # to the as-of close when the fill price isn't available.
    ref = price if price is not None else close
    pos = None
    if ref is not None and low20 is not None and high20 is not None and float(high20) > float(low20):
        pos = _clamp((float(ref) - float(low20)) / (float(high20) - float(low20)))

    side = (side or "").upper()
    parts: list[tuple[float, float]] = []  # (weight, signal)
    notes: list[str] = []

    if side == "SELL":
        if pos is not None:
            near_low = _clamp((0.30 - pos) / 0.30)
            parts.append((0.6, near_low))
            if near_low > 0:
                notes.append(f"sold at {pos:.0%} of 20-day range (near low)")
        if rsi is not None:
            oversold = _clamp((40.0 - float(rsi)) / 40.0)
            parts.append((0.4, oversold))
            if oversold > 0:
                notes.append(f"RSI {float(rsi):.0f} (oversold)")
    else:  # BUY / CROSS
        if pos is not None:
            near_peak = _clamp((pos - 0.70) / 0.30)
            parts.append((0.5, near_peak))
            if near_peak > 0:
                notes.append(f"bought at {pos:.0%} of 20-day range (near peak)")
        if rsi is not None:
            overbought = _clamp((float(rsi) - 60.0) / 40.0)
            parts.append((0.3, overbought))
            if overbought > 0:
                notes.append(f"RSI {float(rsi):.0f} (overbought)")
        if sma20 and close and float(sma20) > 0:
            stretch = _clamp((float(close) / float(sma20) - 1.0) / 0.10)
            parts.append((0.2, stretch))
            if stretch > 0:
                notes.append(f"{(float(close) / float(sma20) - 1.0):+.0%} vs 20-day average")

    if not parts:
        return None
    wsum = sum(w for w, _ in parts)
    score = _clamp(sum(w * s for w, s in parts) / wsum) if wsum else 0.0

    if score >= 0.5:
        posture = "Poor entry"
    elif score >= 0.25:
        posture = "Mixed entry"
    else:
        posture = "Reasonable entry"
    basis = "; ".join(notes) if notes else (
        f"RSI {float(rsi):.0f}" if rsi is not None else "no extended signals"
    )

    return {
        "score": round(score, 3),
        "posture": posture,
        "rsi": round(float(rsi), 1) if rsi is not None else None,
        "pos_in_range": round(pos, 3) if pos is not None else None,
        "dist_sma20_pct": round(dist_sma20 * 100, 1) if dist_sma20 is not None else None,
        "dist_sma50_pct": round(dist_sma50 * 100, 1) if dist_sma50 is not None else None,
        "mom_1m_pct": round(mom_1m * 100, 1) if mom_1m is not None else None,
        "as_of": r["date"].isoformat() if r.get("date") else None,
        "basis": basis,
    }


# ---------------------------------------------------------------- integrated verdict

# Lens weights for the integrated verdict (re-normalised over whatever lenses have
# data on a given case). Microstructure lenses come from the upstream fill score;
# fundamental + technical are the new investment-merit lenses.
_WEIGHTS = {
    "manip": 0.18,
    "counterparty": 0.18,
    "fundamental": 0.16,
    "exec": 0.14,
    "technical": 0.12,
    "outcome": 0.12,
    "cross": 0.10,
}
_LENS_LABELS = {
    "manip": "Market manipulation",
    "counterparty": "Counterparty concentration",
    "fundamental": "Fundamental health",
    "exec": "Execution quality",
    "technical": "Technical entry",
    "outcome": "Post-trade outcome",
    "cross": "Intra-firm cross / churn",
}
_CODEV_LAMBDA = 0.15   # escalation per extra lit lens
_CODEV_CAP = 1.5       # max co-deviation multiplier
_LIT_THRESHOLD = 0.5   # a lens is "lit" at or above this concern level


def _tier(score: float) -> str:
    return "HIGH" if score >= 70 else "ELEVATED" if score >= 45 else "MODERATE" if score >= 25 else "LOW"


def integrate(
    micro: dict,
    fundamental: dict | None,
    technical: dict | None,
    *,
    micro_score: float | None = None,
    notes: dict[str, str] | None = None,
) -> dict:
    """Fuse all available lenses into one verdict (0-100 + tier + factor breakdown).

    `micro` carries the upstream microstructure components (exec/manip/counterparty/
    cross/outcome, each 0-1). Weighted base is re-normalised over the lenses that
    actually have data, then escalated by a small capped multiplier when several
    independent lenses are lit at once — the analyst's "everything points the same
    way" intuition.

    The merit lenses (fundamentals/technicals) can only ESCALATE: the verdict is
    floored at the upstream microstructure score (`micro_score`, 0-100) so a benign
    chart or healthy balance sheet can never wash out a wash-trade / concentration
    signal. Returns the score, tier, and a sorted factor breakdown for display and
    for the LLM note."""
    notes = notes or {}
    values: dict[str, float] = {
        "exec": float(micro.get("exec") or 0),
        "manip": float(micro.get("manip") or 0),
        "counterparty": float(micro.get("counterparty") or 0),
        "cross": float(micro.get("cross") or 0),
        "outcome": float(micro.get("outcome") or 0),
    }
    if fundamental is not None:
        values["fundamental"] = float(fundamental.get("score") or 0)
        notes.setdefault("fundamental", fundamental.get("basis", ""))
    if technical is not None:
        values["technical"] = float(technical.get("score") or 0)
        notes.setdefault("technical", technical.get("basis", ""))

    wsum = sum(_WEIGHTS[k] for k in values)
    base = sum(_WEIGHTS[k] * v for k, v in values.items()) / wsum if wsum else 0.0

    n_lit = sum(1 for v in values.values() if v >= _LIT_THRESHOLD)
    mult = min(1.0 + _CODEV_LAMBDA * (n_lit - 1), _CODEV_CAP) if n_lit > 1 else 1.0
    # Floor at the microstructure score — merit lenses escalate, never excuse.
    score = round(_clamp(max(100.0 * base * mult, float(micro_score or 0)), 0.0, 100.0), 1)

    factors = sorted(
        (
            {
                "lens": k,
                "label": _LENS_LABELS[k],
                "value": round(values[k], 3),
                "weight": round(_WEIGHTS[k] / wsum, 3),
                "contribution": round(_WEIGHTS[k] / wsum * values[k], 3),
                "note": notes.get(k, ""),
            }
            for k in values
        ),
        key=lambda f: -f["contribution"],
    )
    drivers = [f for f in factors if f["value"] >= 0.4]

    return {
        "score": score,
        "tier": _tier(score),
        "factors": factors,
        "drivers": drivers,
        "n_lit": n_lit,
        "multiplier": round(mult, 2),
    }
