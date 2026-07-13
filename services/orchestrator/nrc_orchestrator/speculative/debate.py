"""Bull vs bear vs judge → an unbiased RED/AMBER/GREEN verdict on the report.

Three LLM passes over the evidence bundle (thesis + recommendation + claim
verdicts + aspect ratings): a Bull argues the thesis is sound, a Bear argues
against, and a Judge weighs both and renders the verdict + confidence +
reasoning. The adversarial structure is what keeps the verdict unbiased rather
than echoing the report's optimism."""
from __future__ import annotations

import json
import logging

from nrc_llm import LLMClient, Message, Role, get_router

_log = logging.getLogger("nrc_orchestrator.speculative.debate")


def _evidence_summary(report, claims: list[dict], aspects: dict[str, list[dict]]) -> str:
    supported = sum(1 for c in claims if c["verdict"] == "supported")
    contradicted = [c for c in claims if c["verdict"] == "contradicted"]
    unverifiable = sum(1 for c in claims if c["verdict"] == "unverifiable")
    neg_aspects = [(s, a["aspect"], a["assessment"]) for s, lst in aspects.items()
                   for a in lst if a["rating"] == "negative"]
    return json.dumps({
        "thesis": report.thesis,
        "recommendation": report.recommendation,
        "scrips": report.scrips,
        "claims_supported": supported,
        "claims_contradicted": [{"claim": c["claim_text"], "actual": c["actual_value"]} for c in contradicted],
        "claims_unverifiable": unverifiable,
        "negative_aspects": [{"scrip": s, "aspect": a, "note": n} for s, a, n in neg_aspects][:25],
    }, default=str)[:9000]


def _ask(llm: LLMClient, system: str, user: str, max_tokens: int = 1024) -> str:
    try:
        return llm.complete([Message(role=Role.USER, content=user)], system=system,
                            tools=None, max_output_tokens=max_tokens, temperature=0.2).content.strip()
    except Exception:  # noqa: BLE001
        _log.exception("debate turn failed")
        return ""


_BULL = "You are the BULL. Argue, in 4-6 sentences, why this research report's thesis IS defensible — cite the supported claims and positive signals. Be persuasive but honest."
_BEAR = "You are the BEAR. Argue, in 4-6 sentences, why this report's thesis is RISKY or WRONG — cite contradicted claims, negative aspects, manipulation/speculation flags, and unverifiable key assertions. Be persuasive but honest."
_JUDGE = """You are the JUDGE — an unbiased investment-committee chair. Given the evidence, the bull case, \
and the bear case, render a verdict on whether the report's recommendation is well-supported. Return STRICT JSON:
{"verdict": "GREEN"|"AMBER"|"RED", "confidence": <float 0..1>, "reasoning": "<3-5 sentence justification>"}
GREEN = thesis well-supported by data, risks minor. AMBER = mixed/material unverified or moderate risks. \
RED = thesis contradicted by data or serious risk/manipulation signals. Weigh evidence, not rhetoric."""


def run_debate(report, claims: list[dict], aspects: dict[str, list[dict]], *,
               llm: LLMClient | None = None) -> dict:
    """Return {bull, bear, judge:{verdict,confidence,reasoning}}."""
    llm = llm or get_router().synthesizer()
    ev = _evidence_summary(report, claims, aspects)
    bull = _ask(llm, _BULL, f"EVIDENCE:\n{ev}")
    bear = _ask(llm, _BEAR, f"EVIDENCE:\n{ev}")
    judge_raw = _ask(llm, _JUDGE, f"EVIDENCE:\n{ev}\n\nBULL CASE:\n{bull}\n\nBEAR CASE:\n{bear}", max_tokens=800)

    verdict, confidence, reasoning = "AMBER", 0.5, judge_raw
    s, e = judge_raw.find("{"), judge_raw.rfind("}")
    if s != -1 and e != -1:
        try:
            j = json.loads(judge_raw[s:e + 1])
            v = str(j.get("verdict", "AMBER")).upper()
            verdict = v if v in {"GREEN", "AMBER", "RED"} else "AMBER"
            confidence = max(0.0, min(1.0, float(j.get("confidence", 0.5))))
            reasoning = str(j.get("reasoning", "")) or judge_raw
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return {"bull": bull, "bear": bear,
            "judge": {"verdict": verdict, "confidence": confidence, "reasoning": reasoning}}
