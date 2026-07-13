"""Gemini enrichment — batch-classify headlines into sentiment + summary + event.

Uses the cheap intent-tier model (flash-lite); headlines are processed in
batches (one LLM call per batch) returning a strict JSON array. Robust to
partial/garbled output — unparseable items fall back to NEUTRAL so a bad batch
never blocks ingestion. Nepali headlines are summarized in English."""
from __future__ import annotations

import json
import logging

from nrc_llm import LLMClient, Message, Role, get_router

from .sources import RawArticle

_log = logging.getLogger("nrc_newsfeed.enrich")

_VALID_EVENTS = {"earnings", "dividend", "management", "regulatory", "merger", "other"}

_SYSTEM = """You are a NEPSE (Nepal Stock Exchange) market-news analyst. For each numbered \
headline, judge its likely impact on the mentioned Nepali listed company/sector and return STRICT JSON.

Each item may list candidate company symbols (with names). In "scrips", return ONLY the symbols \
of the listed company/companies the news is genuinely ABOUT — its primary subject(s). EXCLUDE \
companies merely mentioned in passing (issue managers, underwriters, rating agencies, peers/\
comparisons). Pick only from the provided candidates; if none of them is the actual subject, \
return []. If no candidates are given, return [].

Return ONLY a JSON array, one object per input item, no prose, no markdown fences:
[{"i": <index>, "sentiment": "BULLISH"|"NEUTRAL"|"BEARISH", "score": <float -1.0..1.0>, \
"event_type": "earnings"|"dividend"|"management"|"regulatory"|"merger"|"other", \
"summary": "<one concise English sentence>", "scrips": ["<SYMBOL>", ...]}]

Guidance: dividend hikes/profit growth/expansion = BULLISH; NPL rise/losses/regulatory penalties/\
promoter selling = BEARISH; routine notices = NEUTRAL. score sign matches sentiment, magnitude = \
conviction. Translate Nepali headlines to English in the summary."""


def _parse_json_array(text: str) -> list[dict]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text
        text = text.lstrip("json").strip().strip("`").strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(text[start:end + 1])
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def enrich_articles(
    articles: list[RawArticle],
    *,
    candidates: dict[str, list[tuple[str, str]]] | None = None,
    llm: LLMClient | None = None,
    batch_size: int = 20,
) -> dict[str, dict]:
    """Return {article_id: {sentiment, sentiment_score, event_type, summary, scrips}}.

    candidates maps article_id → [(scrip, company_name), ...]; the LLM returns the
    subset (in 'scrips') that each article is genuinely about. scrips is [] when no
    candidates are supplied or none is the true subject."""
    candidates = candidates or {}
    llm = llm or get_router().intent()
    results: dict[str, dict] = {}

    for start in range(0, len(articles), batch_size):
        batch = articles[start:start + batch_size]
        lines = []
        for i, a in enumerate(batch):
            snip = (a.snippet[:160] + "…") if len(a.snippet) > 160 else a.snippet
            line = f"{i}. {a.title}" + (f" — {snip}" if snip else "")
            cands = candidates.get(a.article_id) or []
            if cands:
                line += "  [candidates: " + ", ".join(f"{s}={n}" for s, n in cands) + "]"
            lines.append(line)
        prompt = "Headlines:\n" + "\n".join(lines)
        try:
            resp = llm.complete(
                [Message(role=Role.USER, content=prompt)],
                system=_SYSTEM, tools=None, max_output_tokens=2048, temperature=0.1,
            )
            parsed = _parse_json_array(resp.content)
        except Exception:  # noqa: BLE001 — never let a bad batch block ingestion
            _log.exception("enrichment batch failed; defaulting to NEUTRAL")
            parsed = []

        by_index = {int(o["i"]): o for o in parsed if isinstance(o, dict) and "i" in o}
        for i, a in enumerate(batch):
            o = by_index.get(i, {})
            classified = i in by_index   # did the LLM actually return an object for this item?
            sentiment = str(o.get("sentiment", "NEUTRAL")).upper()
            if sentiment not in {"BULLISH", "NEUTRAL", "BEARISH"}:
                sentiment = "NEUTRAL"
            event = str(o.get("event_type", "other")).lower()
            if event not in _VALID_EVENTS:
                event = "other"
            try:
                score = max(-1.0, min(1.0, float(o.get("score", 0.0))))
            except (TypeError, ValueError):
                score = 0.0
            # Keep only returned symbols that were in this article's candidate set
            # (guards against hallucinated symbols).
            allowed = {s for s, _ in (candidates.get(a.article_id) or [])}
            raw_scrips = o.get("scrips") if isinstance(o.get("scrips"), list) else []
            scrips = sorted({str(s).upper() for s in raw_scrips if str(s).upper() in allowed})
            results[a.article_id] = {
                "sentiment": sentiment,
                "sentiment_score": score,
                "event_type": event,
                "summary": (o.get("summary") or a.title)[:500],
                "scrips": scrips,
                "classified": classified,
            }
    return results
