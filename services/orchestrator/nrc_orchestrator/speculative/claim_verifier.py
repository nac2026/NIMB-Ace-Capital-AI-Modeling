"""Verify each extracted report claim against ground-truth data.

Builds a compact ground-truth context (per-scrip metric snapshots from
speculative_pipeline.analyze_tickers + broker/sentiment, plus per-sector
aggregates), then has Gemini judge each claim: supported | contradicted |
unverifiable, with the actual figure and a one-line evidence note.

Honest by design: when we lack the data to check a claim (e.g. a sector we
don't cover fundamentally), the verdict is 'unverifiable' — never a guess."""
from __future__ import annotations

import json
import logging

from nrc_llm import LLMClient, Message, Role, get_router
from nrc_storage import PostgresClient

from ..speculative_pipeline import analyze_tickers
from .report_parser import ParsedClaim, ParsedReport

_log = logging.getLogger("nrc_orchestrator.speculative.claim_verifier")

# Metric fields worth surfacing to the verifier from each scrip snapshot.
_SNAP_KEYS = [
    "pe_ratio", "pb_ratio", "roe", "roa", "npl_ratio", "car", "cd_ratio",
    "eps", "bvps", "net_profit", "net_profit_yoy_pct", "return_6m",
    "total_deposits", "total_loans", "quality_score_0_100",
]


def _sector_aggregates(pg: PostgresClient, sectors: list[str]) -> list[dict]:
    """Latest-quarter per-sector medians (PE, NPL, ROE) for referenced sectors."""
    if not sectors:
        return []
    return pg.fetch_all(
        """
        WITH latest AS (
            SELECT DISTINCT ON (fs.scrip) fs.scrip, fs.pe_ratio, fs.npl_ratio, fs.roe
            FROM fundamental_snapshots fs
            ORDER BY fs.scrip, fs.fiscal_year_bs DESC, fs.quarter DESC
        )
        SELECT s.sector,
               count(*) AS n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY l.pe_ratio)  AS median_pe,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY l.npl_ratio) AS median_npl,
               avg(l.roe) AS avg_roe
        FROM latest l JOIN scrips s USING (scrip)
        WHERE s.sector = ANY(%s)
        GROUP BY s.sector
        """,
        (sectors,),
    )


def build_ground_truth(report: ParsedReport, pg: PostgresClient) -> dict:
    """Assemble the ground-truth context the verifier reasons against."""
    scrips = sorted({*report.scrips, *(c.scrip for c in report.claims if c.scrip)})
    snaps = analyze_tickers(scrips, pg) if scrips else []
    per_scrip = {}
    for r in snaps:
        snap = r.get("snapshot", {})
        per_scrip[r["scrip"]] = {
            "sector": r.get("sector"),
            "flag": r.get("flag"),
            **{k: snap[k] for k in _SNAP_KEYS if k in snap},
        }
    # broker + sentiment overlays (best-effort)
    if scrips:
        for row in pg.fetch_all(
            "SELECT scrip, speculation_score, speculation_tier FROM speculation_score WHERE scrip = ANY(%s)",
            (scrips,),
        ):
            per_scrip.setdefault(row["scrip"], {}).update(
                speculation_score=row["speculation_score"], speculation_tier=row["speculation_tier"])
        for row in pg.fetch_all(
            "SELECT scrip, sentiment_label, sentiment_score FROM scrip_sentiment WHERE scrip = ANY(%s)",
            (scrips,),
        ):
            per_scrip.setdefault(row["scrip"], {}).update(
                news_sentiment=row["sentiment_label"], sentiment_score=row["sentiment_score"])

    return {
        "per_scrip": per_scrip,
        "sector_aggregates": _sector_aggregates(pg, report.sectors),
    }


_SYSTEM = """You are a fact-checking analyst. You are given GROUND-TRUTH data from our NEPSE \
database and a list of CLAIMS from a research report. For each claim, judge it against the data \
and return STRICT JSON — an array, one object per claim, in order:

[{"i": <index>, "verdict": "supported"|"contradicted"|"unverifiable", \
"actual_value": "<the real figure/finding from the data, or null>", \
"evidence": "<one concise sentence citing the data>"}]

Rules: 'supported' only if the data clearly agrees (allow small rounding). 'contradicted' if the \
data clearly disagrees — state the real number. 'unverifiable' if the data doesn't cover it (do NOT \
guess). Compare like-for-like (sector medians for sector claims, the scrip's snapshot for company \
claims). Be strict and literal."""


def _parse_array(text: str) -> list[dict]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text
        text = text.lstrip("json").strip().strip("`").strip()
    s, e = text.find("["), text.rfind("]")
    if s == -1 or e == -1:
        return []
    try:
        return json.loads(text[s:e + 1])
    except json.JSONDecodeError:
        return []


def verify_claims(
    report: ParsedReport,
    pg: PostgresClient,
    *,
    llm: LLMClient | None = None,
) -> list[dict]:
    """Return [{claim_text, scrip, claim_type, verdict, actual_value, evidence}]."""
    if not report.claims:
        return []
    llm = llm or get_router().synthesizer()
    gt = build_ground_truth(report, pg)

    claim_lines = [
        f'{i}. ' + (f"[{c.scrip}] " if c.scrip else "") + c.claim_text
        for i, c in enumerate(report.claims)
    ]
    prompt = (
        "GROUND-TRUTH DATA (JSON):\n" + json.dumps(gt, default=str)[:12000]
        + "\n\nCLAIMS:\n" + "\n".join(claim_lines)
    )
    try:
        resp = llm.complete([Message(role=Role.USER, content=prompt)],
                            system=_SYSTEM, tools=None, max_output_tokens=8192, temperature=0.1)
        verdicts = {int(o["i"]): o for o in _parse_array(resp.content) if isinstance(o, dict) and "i" in o}
    except Exception:  # noqa: BLE001
        _log.exception("claim verification failed")
        verdicts = {}

    out = []
    for i, c in enumerate(report.claims):
        v = verdicts.get(i, {})
        verdict = str(v.get("verdict", "unverifiable")).lower()
        if verdict not in {"supported", "contradicted", "unverifiable"}:
            verdict = "unverifiable"
        out.append({
            "claim_text": c.claim_text,
            "scrip": c.scrip,
            "claim_type": c.claim_type,
            "verdict": verdict,
            "actual_value": v.get("actual_value"),
            "evidence": {"note": v.get("evidence")},
        })
    return out
