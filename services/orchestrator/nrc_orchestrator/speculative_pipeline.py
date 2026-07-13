"""Speculative analysis engine — rules + LLM narrative.

Given a list of tickers and a PostgresClient, this module:

1. Pulls latest-row metrics from every relevant Gold table in one batch.
2. Evaluates a set of declarative rules per ticker → red/amber/green outcome.
3. Aggregates to a single per-ticker flag + score.
4. Generates a markdown narrative report via the LLM synthesizer.

Called synchronously from POST /api/speculative/{id}/analyze. Designed for
≤20 tickers — finishes in <8s end-to-end (SQL ~300ms + LLM ~3-5s).

Rule thresholds live in the THRESHOLDS block at the top of this file so they
can be tuned without code archaeology.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from nrc_llm import get_router
from nrc_llm.types import Message, Role
from nrc_storage import PostgresClient

_log = logging.getLogger("nrc_orchestrator.speculative_pipeline")


# ─── Tunable thresholds ─────────────────────────────────────────────
THRESHOLDS = {
    # Asset quality
    "npl_red":          5.0,   # NPL ratio above this → RED
    "npl_amber":        3.0,
    "npl_yoy_red":      1.0,   # YoY NPL change worse than this → RED
    "npl_yoy_amber":    0.3,
    # Capital
    "car_red":         11.0,   # NRB minimum is 11%
    "car_amber":       13.0,
    # Piotroski
    "f_score_red":        3,
    "f_score_amber":      5,
    # Quality composite
    "quality_red":     40.0,
    "quality_amber":   60.0,
    # Valuation vs own history
    "pe_pct_red":      80.0,   # very expensive vs own 5y history
    "pe_pct_amber":    60.0,
    # Momentum (6m return)
    "return6m_red":   -15.0,
    "return6m_amber":   0.0,
    # Drawdown from peak
    "drawdown_red":   -30.0,
    "drawdown_amber": -15.0,
    # Realized volatility (daily, 20d window)
    "vol_red":         0.04,   # ~63% annualized
    "vol_amber":       0.025,
}


# ─── SQL — one batch query for all metrics, all tickers ─────────────
# Many useful fields are pre-baked into `investment_scorecard` (single row
# per scrip). For the rest we scalar-subselect the latest fiscal quarter.
# `quality_momentum_matrix` derives its own `quadrant` server-side but the
# column is computed in the dbt model; we approximate it from quality_score
# + return_6m + sector medians using thresholds in Python if needed.
_BATCH_SQL = """
WITH t AS (SELECT UNNEST(%(tickers)s::text[]) AS scrip)
SELECT
    t.scrip,
    s.company_name,
    s.sector,
    -- investment_scorecard already collapses many useful fields
    sc.scorecard_0_100,
    sc.quality_pct, sc.valuation_pct, sc.momentum_pct, sc.risk_pct, sc.income_pct,
    sc.quality_score_0_100,
    sc.pe_self_pct_5y,
    sc.return_6m AS sc_return_6m,
    sc.sharpe_ratio_2y,
    sc.total_dividend_yield,
    -- latest asset_quality_trends
    (SELECT npl_ratio FROM asset_quality_trends x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS npl_ratio,
    (SELECT npl_yoy_change_abs FROM asset_quality_trends x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS npl_yoy_change_abs,
    (SELECT asset_quality_tier FROM asset_quality_trends x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS asset_quality_tier,
    -- latest capital_strength
    (SELECT car FROM capital_strength x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS car,
    (SELECT capital_tier FROM capital_strength x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS capital_tier,
    -- latest piotroski: prefer the explicit f_score if present, otherwise sum p1..p9
    (SELECT COALESCE(
              NULLIF((p1_positive_profit::int + p2_positive_roa + p3_profit_grew
                    + p4_roa_improved + p5_npl_not_worse + p6_car_not_worse
                    + p7_no_large_issuance + p8_nim_improved + p9_cti_improved), 0),
              NULL)
       FROM piotroski_f_score x
      WHERE x.scrip = t.scrip
      ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS f_score,
    -- latest valuation_history (no `date` column — use fiscal year/quarter)
    (SELECT pe_self_pct_5y FROM valuation_history x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS pe_self_pct_5y_latest,
    (SELECT self_valuation_tier FROM valuation_history x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS self_valuation_tier,
    -- price_returns single row per scrip
    pr.return_1m, pr.return_3m, pr.return_6m,
    pr.drawdown_from_peak, pr.realized_vol_20d,
    -- quadrant matrix
    qm.quality_tier AS quadrant_quality_tier,
    qm.is_high_quality, qm.is_high_momentum,
    -- dividend_yield (no `date` column either)
    (SELECT yield_tier FROM dividend_yield x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC LIMIT 1) AS yield_tier,
    -- ─── Research-team report columns ─────────────────────────────────
    -- Latest per-quarter snapshot: EPS, BVPS, ROE, PE, PB
    (SELECT eps      FROM fundamental_snapshots x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS eps,
    (SELECT bvps     FROM fundamental_snapshots x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS bvps,
    (SELECT roe      FROM fundamental_snapshots x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS roe,
    (SELECT pe_ratio FROM fundamental_snapshots x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS pe_ratio,
    (SELECT pb_ratio FROM fundamental_snapshots x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS pb_ratio,
    -- Latest YoY growth metrics
    (SELECT net_profit_yoy_pct  FROM quarterly_growth x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS net_profit_yoy_pct,
    (SELECT total_operating_income_yoy_pct FROM quarterly_growth x
      WHERE x.scrip = t.scrip ORDER BY fiscal_year_bs DESC, quarter DESC LIMIT 1) AS operating_income_yoy_pct,
    -- LTP + market cap
    mc.latest_close       AS last_price,
    mc.market_cap_npr     AS market_cap,
    mc.market_cap_tier
FROM t
LEFT JOIN scrips                     s  ON s.scrip = t.scrip
LEFT JOIN investment_scorecard       sc ON sc.scrip = t.scrip
LEFT JOIN price_returns              pr ON pr.scrip = t.scrip
LEFT JOIN quality_momentum_matrix    qm ON qm.scrip = t.scrip
LEFT JOIN market_cap_metrics         mc ON mc.scrip = t.scrip
"""


def _derive_quadrant(row: dict) -> str | None:
    """Quadrant label from is_high_quality / is_high_momentum booleans."""
    hq = row.get("is_high_quality")
    hm = row.get("is_high_momentum")
    if hq is None or hm is None:
        return None
    if hq and hm:     return "QUALITY_LEADER"
    if hq and not hm: return "CONTRARIAN_BET"
    if not hq and hm: return "MOMENTUM_TRAP"
    return "AVOID"


# ─── Cohort classifier — Research team's Value/Fundamental/Out taxonomy ──
# Thresholds mirror the BFIs - Fundamental Universe Excel's Criterion sheet:
#   PE Ratio:           < 25
#   Dividend Yield:     ≥ 3%
#   EPS:                > 0
#   Net Profit Growth:  ≥ 5%
#   Credit Rating:      ≥ BBB+   (we don't ingest yet — leave for phase 2)
COHORT_THRESHOLDS = {
    "pe_value_max":          25.0,
    "div_yield_value_min":    3.0,    # percentage points
    "net_profit_growth_min":  5.0,    # percentage points YoY
    "npl_disqualifying":      6.0,    # NPL above → out_of_universe
    "pe_disqualifying":      40.0,    # PE above → out_of_universe
    "car_disqualifying":     11.0,    # NRB minimum
}


def _classify_cohort(row: dict) -> tuple[str, str]:
    """Classify a ticker into one of: value_universe, fundamental_universe,
    out_of_universe, unknown. Returns (cohort, reason_str)."""
    if row.get("company_name") is None:
        return "unknown", "Ticker not in active universe."

    pe        = row.get("pe_ratio")
    eps       = row.get("eps")
    npl_pct   = (row.get("npl_ratio") or 0.0) * 100.0  # fraction → percent
    car_pct   = (row.get("car") or 0.0) * 100.0
    div_yield_pct  = row.get("total_dividend_yield")   # already in percent
    profit_yoy_pct = row.get("net_profit_yoy_pct")     # already in percent
    has_car   = row.get("car") is not None
    has_npl   = row.get("npl_ratio") is not None

    th = COHORT_THRESHOLDS

    # ─── Out of universe — any hard disqualifier ──────────────
    disqualifiers: list[str] = []
    if pe is not None and pe > th["pe_disqualifying"]:
        disqualifiers.append(f"PE {pe:.1f} > {th['pe_disqualifying']:.0f}")
    if has_npl and npl_pct > th["npl_disqualifying"]:
        disqualifiers.append(f"NPL {npl_pct:.1f}% > {th['npl_disqualifying']:.1f}%")
    if has_car and car_pct < th["car_disqualifying"]:
        disqualifiers.append(f"CAR {car_pct:.1f}% < {th['car_disqualifying']:.0f}% (NRB minimum)")
    if eps is not None and eps <= 0:
        disqualifiers.append(f"EPS {eps:.2f} ≤ 0")
    if disqualifiers:
        return "out_of_universe", "; ".join(disqualifiers)

    # ─── Value universe — clean fundamentals + PE under 25 ────
    if pe is None or eps is None:
        # Without these we can't make a value/fundamental call confidently
        return "fundamental_universe", "Limited fundamentals available; tracking as Fundamental Universe."

    value_checks_pass: list[str] = []
    value_checks_fail: list[str] = []

    if pe < th["pe_value_max"]:
        value_checks_pass.append(f"PE {pe:.1f} < {th['pe_value_max']:.0f}")
    else:
        value_checks_fail.append(f"PE {pe:.1f} ≥ {th['pe_value_max']:.0f}")

    if eps > 0:
        value_checks_pass.append(f"EPS {eps:.2f} > 0")
    else:
        value_checks_fail.append(f"EPS not positive")

    if div_yield_pct is not None:
        if div_yield_pct >= th["div_yield_value_min"]:
            value_checks_pass.append(f"yield {div_yield_pct:.1f}% ≥ {th['div_yield_value_min']:.0f}%")
        else:
            value_checks_fail.append(f"yield {div_yield_pct:.1f}% < {th['div_yield_value_min']:.0f}%")

    if profit_yoy_pct is not None:
        if profit_yoy_pct >= th["net_profit_growth_min"]:
            value_checks_pass.append(f"profit growth {profit_yoy_pct:+.1f}% ≥ {th['net_profit_growth_min']:.0f}%")
        else:
            value_checks_fail.append(f"profit growth {profit_yoy_pct:+.1f}% < {th['net_profit_growth_min']:.0f}%")

    # All must pass for Value Universe
    if not value_checks_fail:
        return "value_universe", "Meets all value criteria: " + " · ".join(value_checks_pass) + "."

    # Otherwise — fundamentals are OK enough to track, but with caveats
    return (
        "fundamental_universe",
        "Tracking as Fundamental Universe. Outside Value criteria: " + " · ".join(value_checks_fail) + ".",
    )


def _evaluate_rules(row: dict) -> list[dict]:
    """Run every rule against the row; return a list of outcome dicts."""
    outcomes: list[dict] = []

    def add(rule: str, status: str, value: Any, threshold: str) -> None:
        outcomes.append({
            "rule": rule, "status": status,
            "value": value, "threshold": threshold,
        })

    # NPL, CAR, NPL YoY change, valuation percentile are stored as
    # fractions (0.0425 = 4.25%). Convert before comparing to thresholds.
    npl_raw = row.get("npl_ratio")
    if npl_raw is not None:
        npl = npl_raw * 100.0
        if   npl > THRESHOLDS["npl_red"]:   add("asset_quality", "red",   npl, f"NPL > {THRESHOLDS['npl_red']:.1f}%")
        elif npl > THRESHOLDS["npl_amber"]: add("asset_quality", "amber", npl, f"NPL > {THRESHOLDS['npl_amber']:.1f}%")
        else:                                add("asset_quality", "green", npl, f"NPL ≤ {THRESHOLDS['npl_amber']:.1f}%")

    npl_yoy_raw = row.get("npl_yoy_change_abs")
    if npl_yoy_raw is not None:
        npl_yoy = npl_yoy_raw * 100.0
        if   npl_yoy > THRESHOLDS["npl_yoy_red"]:   add("npl_trend", "red",   npl_yoy, f"NPL YoY worsened by > {THRESHOLDS['npl_yoy_red']:.1f}pp")
        elif npl_yoy > THRESHOLDS["npl_yoy_amber"]: add("npl_trend", "amber", npl_yoy, f"NPL YoY worsened by > {THRESHOLDS['npl_yoy_amber']:.1f}pp")
        else:                                        add("npl_trend", "green", npl_yoy, "NPL trend stable or improving")

    car_raw = row.get("car")
    if car_raw is not None:
        car = car_raw * 100.0
        if   car < THRESHOLDS["car_red"]:   add("capital", "red",   car, f"CAR < {THRESHOLDS['car_red']:.1f}% (regulatory minimum)")
        elif car < THRESHOLDS["car_amber"]: add("capital", "amber", car, f"CAR < {THRESHOLDS['car_amber']:.1f}%")
        else:                                add("capital", "green", car, f"CAR ≥ {THRESHOLDS['car_amber']:.1f}%")

    fs = row.get("f_score")
    if fs is not None:
        if   fs <= THRESHOLDS["f_score_red"]:   add("piotroski", "red",   fs, f"F-score ≤ {THRESHOLDS['f_score_red']}")
        elif fs <= THRESHOLDS["f_score_amber"]: add("piotroski", "amber", fs, f"F-score ≤ {THRESHOLDS['f_score_amber']}")
        else:                                    add("piotroski", "green", fs, f"F-score > {THRESHOLDS['f_score_amber']}")

    q = row.get("quality_score_0_100")
    if q is not None:
        if   q < THRESHOLDS["quality_red"]:   add("quality_composite", "red",   q, f"Quality composite < {THRESHOLDS['quality_red']:.0f}")
        elif q < THRESHOLDS["quality_amber"]: add("quality_composite", "amber", q, f"Quality composite < {THRESHOLDS['quality_amber']:.0f}")
        else:                                  add("quality_composite", "green", q, f"Quality composite ≥ {THRESHOLDS['quality_amber']:.0f}")

    pe_pct_raw = row.get("pe_self_pct_5y")
    if pe_pct_raw is not None:
        # Stored as 0-1 percentile fraction; convert to percentile points
        pe_pct = pe_pct_raw * 100.0
        if   pe_pct > THRESHOLDS["pe_pct_red"]:   add("valuation_self", "red",   pe_pct, f"P/E in top {100 - THRESHOLDS['pe_pct_red']:.0f}% of own 5y history")
        elif pe_pct > THRESHOLDS["pe_pct_amber"]: add("valuation_self", "amber", pe_pct, f"P/E in top {100 - THRESHOLDS['pe_pct_amber']:.0f}% of own 5y history")
        else:                                      add("valuation_self", "green", pe_pct, "P/E below historical median")

    r6 = row.get("return_6m")
    if r6 is not None:
        # return columns are stored as fractions (0.05 = 5%); convert for thresholds
        r6_pct = r6 * 100.0
        if   r6_pct < THRESHOLDS["return6m_red"]:   add("momentum", "red",   r6_pct, f"6-month return < {THRESHOLDS['return6m_red']:.0f}%")
        elif r6_pct < THRESHOLDS["return6m_amber"]: add("momentum", "amber", r6_pct, "6-month return negative")
        else:                                        add("momentum", "green", r6_pct, "6-month return positive")

    dd = row.get("drawdown_from_peak")
    if dd is not None:
        dd_pct = dd * 100.0
        if   dd_pct < THRESHOLDS["drawdown_red"]:   add("drawdown", "red",   dd_pct, f"Drawdown from peak > {abs(THRESHOLDS['drawdown_red']):.0f}%")
        elif dd_pct < THRESHOLDS["drawdown_amber"]: add("drawdown", "amber", dd_pct, f"Drawdown from peak > {abs(THRESHOLDS['drawdown_amber']):.0f}%")
        else:                                        add("drawdown", "green", dd_pct, "Near 12-month highs")

    vol = row.get("realized_vol_20d")
    if vol is not None:
        if   vol > THRESHOLDS["vol_red"]:   add("volatility", "red",   vol, f"20-day vol > {THRESHOLDS['vol_red']:.3f}")
        elif vol > THRESHOLDS["vol_amber"]: add("volatility", "amber", vol, f"20-day vol > {THRESHOLDS['vol_amber']:.3f}")
        else:                                add("volatility", "green", vol, "Low realized volatility")

    return outcomes


def _aggregate(outcomes: list[dict]) -> tuple[str, float]:
    """Combine rule outcomes into one flag + a 0-100 score.

    Flag = worst status across all rules (RED if any, else AMBER if any, else GREEN).
    Score = mean of {green=100, amber=60, red=20} over evaluated rules."""
    if not outcomes:
        return "unknown", 0.0
    statuses = [o["status"] for o in outcomes]
    if "red" in statuses:
        flag = "red"
    elif "amber" in statuses:
        flag = "amber"
    else:
        flag = "green"
    score_map = {"green": 100.0, "amber": 60.0, "red": 20.0}
    score = sum(score_map[s] for s in statuses) / len(statuses)
    return flag, round(score, 1)


def _format_headline(outcomes: list[dict]) -> str:
    """Compact one-liner showing the 2-3 most impactful rules."""
    if not outcomes:
        return "No data available"

    def order(o: dict) -> int:
        return {"red": 0, "amber": 1, "green": 2}.get(o["status"], 3)

    sorted_ = sorted(outcomes, key=order)
    bits: list[str] = []
    for o in sorted_[:3]:
        v = o["value"]
        if o["rule"] in ("asset_quality",):
            label = f"NPL {v:.1f}%"
        elif o["rule"] == "npl_trend":
            label = f"NPL YoY {v:+.2f}pp"
        elif o["rule"] == "capital":
            label = f"CAR {v:.1f}%"
        elif o["rule"] == "piotroski":
            label = f"F-score {v:.0f}"
        elif o["rule"] == "momentum":
            label = f"6m {v:+.1f}%"
        elif o["rule"] == "quality_composite":
            label = f"Quality {v:.0f}"
        elif o["rule"] == "drawdown":
            label = f"Drawdown {v:.1f}%"
        elif o["rule"] == "valuation_self":
            label = f"P/E pctile {v:.0f}"
        elif o["rule"] == "volatility":
            label = f"Vol {v:.3f}"
        else:
            label = f"{o['rule']} {v}"
        bits.append(f"{label} ({o['status'].upper()})")
    return " · ".join(bits)


def analyze_tickers(tickers: list[str], pg: PostgresClient) -> list[dict]:
    """Evaluate flags for every ticker. Returns one dict per input ticker
    (even if it has no data — those come back with flag='unknown')."""
    if not tickers:
        return []

    rows = pg.fetch_all(_BATCH_SQL, {"tickers": list(tickers)})
    by_scrip = {r["scrip"]: r for r in rows}

    results: list[dict] = []
    for ticker in tickers:
        row = by_scrip.get(ticker)
        if row is None or row.get("company_name") is None:
            results.append({
                "scrip":         ticker,
                "company_name":  None,
                "sector":        None,
                "flag":          "unknown",
                "flag_score":    None,
                "cohort":        "unknown",
                "cohort_reason": "Ticker not in active universe.",
                "rule_outcomes": [],
                "snapshot":      {},
                "headline":      "Ticker not found in active universe",
                "error":         "ticker_not_found",
            })
            continue

        # Decorate row with derived fields used by rules and snapshot
        row["quadrant"] = _derive_quadrant(row)
        # Prefer scorecard's pe_self_pct_5y if non-null; else latest from history
        if row.get("pe_self_pct_5y") is None:
            row["pe_self_pct_5y"] = row.get("pe_self_pct_5y_latest")

        outcomes = _evaluate_rules(row)
        flag, score = _aggregate(outcomes)
        headline = _format_headline(outcomes)
        cohort, cohort_reason = _classify_cohort(row)

        # Build snapshot — strip None values, JSON-friendly
        snapshot = {k: v for k, v in row.items() if v is not None}
        # Cast Decimals/datetimes if any sneak in (defensive)
        for k, v in list(snapshot.items()):
            if hasattr(v, "isoformat"):
                snapshot[k] = v.isoformat()

        results.append({
            "scrip":         ticker,
            "company_name":  row.get("company_name"),
            "sector":        row.get("sector"),
            "flag":          flag,
            "flag_score":    score,
            "cohort":        cohort,
            "cohort_reason": cohort_reason,
            "rule_outcomes": outcomes,
            "snapshot":      snapshot,
            "headline":      headline,
            "error":         None,
        })
    return results


# ─── LLM narrative ──────────────────────────────────────────────────
_NARRATIVE_SYSTEM = """You are an internal investment-research assistant writing a speculative-analysis brief for the CEO of NIMB Ace Capital.

Anchor every claim in the numbers provided. Never invent metrics. Never use the words "buy" or "sell" — frame everything as risk and signal observation.
Output: clean Markdown. Tight, executive tone. No emojis. No filler."""


def _build_narrative_prompt(
    title: str,
    n_tickers: int,
    results: list[dict],
    created_at: datetime,
) -> str:
    by_flag   = {"green": [], "amber": [], "red": [], "unknown": []}
    by_cohort = {"value_universe": [], "fundamental_universe": [], "out_of_universe": [], "unknown": []}
    for r in results:
        by_flag[r["flag"]].append(r["scrip"])
        by_cohort[r.get("cohort", "unknown")].append(r["scrip"])

    # Per-ticker rich snapshot table — the LLM uses this to compose remarks.
    table_lines = [
        "| Ticker | Cohort | Flag | EPS | PE | CAR | NPL | Yield | Profit YoY | Notes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        s = r.get("snapshot", {}) or {}
        eps  = f"{s['eps']:.2f}" if s.get("eps") is not None else "—"
        pe   = f"{s['pe_ratio']:.2f}" if s.get("pe_ratio") is not None else "—"
        car  = f"{s['car']*100:.1f}%" if s.get("car") is not None else "—"
        npl  = f"{s['npl_ratio']*100:.1f}%" if s.get("npl_ratio") is not None else "—"
        dy   = f"{s['total_dividend_yield']:.1f}%" if s.get("total_dividend_yield") is not None else "—"
        gpy  = f"{s['net_profit_yoy_pct']:+.1f}%" if s.get("net_profit_yoy_pct") is not None else "—"
        notes = r.get("headline") or ""
        table_lines.append(
            f"| {r['scrip']} | {r.get('cohort','unknown').replace('_',' ').title()} | "
            f"{r['flag'].upper()} | {eps} | {pe} | {car} | {npl} | {dy} | {gpy} | {notes[:60]} |"
        )
    table = "\n".join(table_lines)

    return f"""# Context

Date: {created_at.strftime("%Y-%m-%d")}
Analysis title: "{title}"
Shortlist: {n_tickers} ticker(s) submitted by the research team.

# Flag summary

- GREEN ({len(by_flag['green'])}): {", ".join(by_flag['green']) or "—"}
- AMBER ({len(by_flag['amber'])}): {", ".join(by_flag['amber']) or "—"}
- RED ({len(by_flag['red'])}): {", ".join(by_flag['red']) or "—"}
{f"- UNKNOWN ({len(by_flag['unknown'])}): {', '.join(by_flag['unknown'])}" if by_flag['unknown'] else ""}

# Cohort summary

- VALUE UNIVERSE       ({len(by_cohort['value_universe'])}): {", ".join(by_cohort['value_universe']) or "—"}
- FUNDAMENTAL UNIVERSE ({len(by_cohort['fundamental_universe'])}): {", ".join(by_cohort['fundamental_universe']) or "—"}
- OUT OF UNIVERSE      ({len(by_cohort['out_of_universe'])}): {", ".join(by_cohort['out_of_universe']) or "—"}

# Per-ticker numbers

{table}

# Write the brief now

Produce exactly the following Markdown sections, followed by a final REMARKS block.

## Executive summary
One paragraph, ≤80 words. State the cohort's overall risk posture in plain English.

## Red flag concentration
For each RED ticker, one bullet (≤25 words) naming the specific rule(s) that triggered, with numbers. Skip this section if no RED names.

## Cohort observations
2–3 bullets on patterns visible across the list (e.g. "X of Y banks have NPL above 5%"). Use specific numeric counts.

## Outliers to watch
1–2 names worth a closer look (preferably Value Universe), each with one reason citing a specific metric. Skip if no clear standouts.

---

REMARKS_START
For EVERY ticker above, emit one short analyst-style sentence (≤25 words) commenting on its standout characteristic, in the style of NIMB Research's "Remarks" column ("PE Below 25 with good fundamentals, good dividend capacity", "Alarming NPL, Increasing non-banking assets and degrading asset quality"). One line per ticker in this EXACT format, nothing else inside this block:

TICKER: remark here

Use the actual ticker symbols. Do NOT use the words "buy" or "sell". Cite specific numbers where helpful.
REMARKS_END

DETAILS_START
For EVERY ticker above, emit a 3-5 sentence detailed verdict explaining (a) why the cohort placement (Value / Fundamental / Out of Universe) is appropriate, citing the specific criteria that passed or failed; (b) what is driving the risk-signal flag (Green / Amber / Red), citing the specific rules that triggered with numbers; (c) any notable positives or concerns. Use plain analyst language — the CEO is the reader.

Format: each ticker as a markdown block in this EXACT shape, nothing else inside this block:

TICKER:
<paragraph of 3-5 sentences>

Separate tickers with a blank line. Do NOT use the words "buy" or "sell". Cite specific numbers.
DETAILS_END

Markdown headings exactly as specified above. Do not add any prose outside these sections."""


def _parse_remarks_block(text: str) -> dict[str, str]:
    """Parse the REMARKS_START..REMARKS_END section into {TICKER: remark}.

    Tolerant to LLM variability: accepts optional bullets, spacing, etc.
    Returns {} if the block is absent or malformed (caller falls back to
    template headline)."""
    import re
    m = re.search(r"REMARKS_START\s*(.*?)\s*REMARKS_END", text, re.DOTALL | re.IGNORECASE)
    if not m:
        return {}
    block = m.group(1)
    remarks: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip().lstrip("-*•").strip()
        if not line:
            continue
        # Match "TICKER: remark text" or "TICKER - remark text"
        mm = re.match(r"^([A-Z][A-Z0-9_]{1,15})\s*[:\-–—]\s*(.+)$", line)
        if mm:
            remarks[mm.group(1)] = mm.group(2).strip().strip("\"'")
    return remarks


def _parse_details_block(text: str) -> dict[str, str]:
    """Parse the DETAILS_START..DETAILS_END section into {TICKER: paragraph}.

    Per ticker the LLM emits:
        TICKER:
        <3-5 sentence paragraph>
        <blank line>
        NEXT_TICKER:
        ...

    Returns {} if the block is absent or malformed."""
    import re
    m = re.search(r"DETAILS_START\s*(.*?)\s*DETAILS_END", text, re.DOTALL | re.IGNORECASE)
    if not m:
        return {}
    block = m.group(1).strip()
    details: dict[str, str] = {}
    # Split on lines that look like "TICKER:" at the start of a line.
    pattern = re.compile(r"^([A-Z][A-Z0-9_]{1,15})\s*:\s*$", re.MULTILINE)
    matches = list(pattern.finditer(block))
    for i, mm in enumerate(matches):
        ticker = mm.group(1)
        start = mm.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        body = block[start:end].strip()
        if body:
            details[ticker] = body
    # Also handle the alternative "TICKER: paragraph on same line" style.
    if not details:
        for line in block.splitlines():
            line = line.strip().lstrip("-*•").strip()
            mm2 = re.match(r"^([A-Z][A-Z0-9_]{1,15})\s*[:\-–—]\s*(.+)$", line)
            if mm2:
                details[mm2.group(1)] = mm2.group(2).strip()
    return details


def _strip_remarks_block(text: str) -> str:
    """Remove the REMARKS_START..REMARKS_END and DETAILS_START..DETAILS_END
    blocks (and any trailing rule line) from the markdown so they don't get
    rendered in the narrative report."""
    import re
    cleaned = re.sub(r"\n?-{3,}\s*\n?REMARKS_START.*?REMARKS_END\s*", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"\n?-{3,}\s*\n?DETAILS_START.*?DETAILS_END\s*",  "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.rstrip()


# ─── Templated fallback when the LLM detail block is missing ───────
def _build_detail_fallback(result: dict) -> str:
    """Compose a 2-4 sentence rationale from cohort_reason + rule outcomes.

    Used when generate_narrative() fails or its DETAILS block can't be
    parsed for this ticker — so the modal always has substantial content."""
    cohort = result.get("cohort", "unknown")
    cohort_reason = result.get("cohort_reason") or ""
    flag = result.get("flag", "unknown")
    outcomes = result.get("rule_outcomes", []) or []
    reds   = [o for o in outcomes if o.get("status") == "red"]
    ambers = [o for o in outcomes if o.get("status") == "amber"]
    greens = [o for o in outcomes if o.get("status") == "green"]

    cohort_label = {
        "value_universe":       "Value Universe",
        "fundamental_universe": "Fundamental Universe",
        "out_of_universe":      "Out of Universe",
        "unknown":              "Unknown",
    }.get(cohort, "Unknown")

    sentences: list[str] = []

    # Sentence 1 — cohort placement
    sentences.append(f"Classified as **{cohort_label}**. {cohort_reason}")

    # Sentence 2 — flag drivers
    if flag == "red" and reds:
        bits = "; ".join(o["threshold"] for o in reds[:3])
        sentences.append(f"The RED risk-signal flag is driven by {len(reds)} hard signal(s): {bits}.")
    elif flag == "amber" and (ambers or reds):
        bits = "; ".join(o["threshold"] for o in (ambers + reds)[:3])
        sentences.append(f"The AMBER risk-signal flag reflects {len(ambers)} soft signal(s): {bits}.")
    elif flag == "green" and greens:
        sentences.append(f"All {len(greens)} evaluated risk signals are within healthy bands.")

    # Sentence 3 — counterweight (positives if amber/red, concerns if green)
    if flag in ("red", "amber") and greens:
        bits = "; ".join(o["threshold"] for o in greens[:2])
        sentences.append(f"Offsetting positives: {bits}.")
    elif flag == "green" and ambers:
        bits = "; ".join(o["threshold"] for o in ambers[:2])
        sentences.append(f"Watch items: {bits}.")

    return " ".join(sentences)


def generate_narrative(
    title: str,
    n_tickers: int,
    results: list[dict],
    created_at: datetime | None = None,
) -> tuple[str | None, str | None, dict[str, str], dict[str, str]]:
    """Returns (markdown, model_name, per_ticker_remarks, per_ticker_details).

    `remarks` are the one-line headlines shown on the collapsed card.
    `details` are the 3-5 sentence rationales shown in the detail modal.

    On failure: returns (None, None, {}, {}) — the caller should set
    session.status='partial' and keep the existing template headlines.
    For tickers missing from the details dict the caller should compose a
    templated fallback via `_build_detail_fallback(result)`."""
    if not results:
        return None, None, {}, {}
    created_at = created_at or datetime.now(timezone.utc)

    try:
        router = get_router()
        client = router.synthesizer()
        prompt = _build_narrative_prompt(title, n_tickers, results, created_at)
        result = client.complete(
            messages=[Message(role=Role.USER, content=prompt)],
            system=_NARRATIVE_SYSTEM,
            temperature=0.3,
            max_output_tokens=4500,
        )
        raw_text = (result.content or "").strip()
        remarks = _parse_remarks_block(raw_text)
        details = _parse_details_block(raw_text)
        cleaned = _strip_remarks_block(raw_text)
        return cleaned, client.model, remarks, details
    except Exception as e:
        _log.exception("LLM narrative generation failed: %s", e)
        return None, None, {}, {}
