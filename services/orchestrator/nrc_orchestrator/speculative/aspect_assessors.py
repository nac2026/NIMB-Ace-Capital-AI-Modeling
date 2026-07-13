"""Independent multi-aspect assessment per scrip.

For each recommended scrip, give Gemini that scrip's full ground-truth bundle
(fundamentals snapshot + flag, broker concentration/accumulation, speculation
score, news sentiment) and have it rate each aspect positive/neutral/negative
with a one-line assessment + score. This is the unbiased "what does the data
actually say about this stock, independent of the report" layer."""
from __future__ import annotations

import json
import logging

from nrc_llm import LLMClient, Message, Role, get_router
from nrc_storage import PostgresClient

from ..speculative_pipeline import analyze_tickers
from .report_parser import ParsedReport

_log = logging.getLogger("nrc_orchestrator.speculative.aspect_assessors")

ASPECTS = [
    "fundamentals", "valuation", "technicals", "floorsheet_manipulation",
    "liquidity", "governance", "regulatory", "macro_sector", "news_sentiment",
]

_SYSTEM = f"""You are an independent NEPSE equity analyst. Given GROUND-TRUTH data for one stock, \
assess each of these aspects: {", ".join(ASPECTS)}. Return STRICT JSON — an array, one object per \
aspect:

[{{"aspect": "<name>", "rating": "positive"|"neutral"|"negative", "score": <float -1..1>, \
"assessment": "<one concise sentence grounded in the data>"}}]

Rules: base ratings ONLY on the provided data. For aspects with no data (e.g. governance if absent), \
rate "neutral" and say data is unavailable. floorsheet_manipulation = negative when speculation score \
is high / one broker dominates / circular trading; positive when clean. Be objective and literal — \
this is a check on a research report, so do not be swayed by optimism."""


def _bundle(scrip: str, pg: PostgresClient) -> dict:
    snaps = analyze_tickers([scrip], pg)
    snap = snaps[0] if snaps else {}
    b = {"scrip": scrip, "sector": snap.get("sector"), "flag": snap.get("flag"),
         "metrics": snap.get("snapshot", {})}
    spec = pg.fetch_one(
        """SELECT speculation_score, speculation_tier, c_concentration, c_circular,
                  c_accumulation, has_self_trade FROM speculation_score WHERE scrip=%s""", (scrip,))
    if spec:
        b["floorsheet"] = spec
    conc = pg.fetch_one(
        """SELECT top1_buy_share, top3_buy_share, concentration_flag
           FROM broker_concentration_daily WHERE scrip=%s ORDER BY trade_date DESC LIMIT 1""", (scrip,))
    if conc:
        b["broker_concentration"] = conc
    sent = pg.fetch_one(
        "SELECT sentiment_label, sentiment_score, n_articles FROM scrip_sentiment WHERE scrip=%s", (scrip,))
    if sent:
        b["news"] = sent
    return b


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


def assess_report(report: ParsedReport, pg: PostgresClient, *, llm: LLMClient | None = None,
                  max_scrips: int = 10) -> dict[str, list[dict]]:
    """Return {scrip: [aspect assessments]} for the report's recommended scrips."""
    llm = llm or get_router().synthesizer()
    scrips = report.scrips[:max_scrips]
    out: dict[str, list[dict]] = {}
    for scrip in scrips:
        bundle = _bundle(scrip, pg)
        try:
            resp = llm.complete(
                [Message(role=Role.USER, content="GROUND-TRUTH:\n" + json.dumps(bundle, default=str)[:8000])],
                system=_SYSTEM, tools=None, max_output_tokens=2048, temperature=0.1)
            items = _parse_array(resp.content)
        except Exception:  # noqa: BLE001
            _log.exception("aspect assessment failed for %s", scrip)
            items = []
        rated = []
        for o in items:
            if not isinstance(o, dict) or not o.get("aspect"):
                continue
            rating = str(o.get("rating", "neutral")).lower()
            if rating not in {"positive", "neutral", "negative"}:
                rating = "neutral"
            try:
                score = max(-1.0, min(1.0, float(o.get("score", 0.0))))
            except (TypeError, ValueError):
                score = 0.0
            rated.append({"aspect": str(o["aspect"]), "rating": rating, "score": score,
                          "assessment": str(o.get("assessment", ""))[:400]})
        out[scrip] = rated
    return out
