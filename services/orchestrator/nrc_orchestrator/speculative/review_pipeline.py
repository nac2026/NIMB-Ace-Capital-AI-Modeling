"""Orchestrate the review-mode pipeline + persist results.

parse → verify claims → assess aspects → bull/bear/judge debate → counter-report,
then write everything to the analysis_* tables. Returns a summary dict. Sets the
session status so the UI can poll. Reuses the same analysis_sessions row the
upload created (mode='review')."""
from __future__ import annotations

import json
import logging

from nrc_storage import PostgresClient

from .aspect_assessors import assess_report
from .claim_verifier import verify_claims
from .counter_report import build_counter_report
from .debate import run_debate
from .report_parser import extract_text, parse_report

_log = logging.getLogger("nrc_orchestrator.speculative.review_pipeline")


def run_review(session_id, content: bytes, filename: str, pg: PostgresClient) -> dict:
    """Entry point from raw bytes (extracts text, then runs the LLM pipeline)."""
    return run_review_from_text(session_id, extract_text(content, filename), pg)


def run_review_from_text(session_id, text: str, pg: PostgresClient) -> dict:
    pg.execute(
        "UPDATE analysis_sessions SET status='running', started_at=now(), mode='review' WHERE session_id=%s",
        (session_id,),
    )
    try:
        report = parse_report(text)
        claims = verify_claims(report, pg)
        aspects = assess_report(report, pg)
        debate = run_debate(report, claims, aspects)
        narrative = build_counter_report(report, claims, aspects, debate)
        verdict = debate["judge"]["verdict"]
        confidence = debate["judge"]["confidence"]

        _persist(session_id, report, claims, aspects, debate, narrative, pg)

        pg.execute(
            """UPDATE analysis_sessions
               SET status='succeeded', completed_at=now(), narrative_md=%s, narrative_model='gemini',
                   parsed_report=%s, verdict=%s, verdict_confidence=%s, target_price=%s,
                   tickers=%s, n_tickers=%s
               WHERE session_id=%s""",
            (narrative, json.dumps(report.model_dump(), default=str), verdict, confidence,
             report.target_price, report.scrips, len(report.scrips), session_id),
        )
        return {"verdict": verdict, "confidence": confidence, "n_claims": len(claims),
                "n_scrips": len(report.scrips)}
    except Exception as e:  # noqa: BLE001
        _log.exception("review pipeline failed")
        pg.execute(
            "UPDATE analysis_sessions SET status='failed', completed_at=now(), error_message=%s WHERE session_id=%s",
            (str(e)[:500], session_id),
        )
        raise


def _persist(session_id, report, claims, aspects, debate, narrative, pg: PostgresClient) -> None:
    with pg.transaction() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM analysis_claims WHERE session_id=%s", (session_id,))
        cur.execute("DELETE FROM analysis_aspects WHERE session_id=%s", (session_id,))
        cur.execute("DELETE FROM analysis_debate WHERE session_id=%s", (session_id,))
        for c in claims:
            cur.execute(
                """INSERT INTO analysis_claims (session_id, scrip, claim_text, claim_type, verdict, actual_value, evidence)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (session_id, c.get("scrip"), c["claim_text"], c.get("claim_type"), c["verdict"],
                 (str(c["actual_value"]) if c.get("actual_value") is not None else None),
                 json.dumps(c.get("evidence") or {})),
            )
        for scrip, lst in aspects.items():
            for a in lst:
                cur.execute(
                    """INSERT INTO analysis_aspects (session_id, scrip, aspect, rating, score, assessment, evidence)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (session_id, scrip, a["aspect"], a["rating"], a["score"], a["assessment"], json.dumps({})),
                )
        for role in ("bull", "bear"):
            if debate.get(role):
                cur.execute(
                    "INSERT INTO analysis_debate (session_id, scrip, role, round, content) VALUES (%s,%s,%s,%s,%s)",
                    (session_id, None, role, 1, debate[role]),
                )
        j = debate.get("judge", {})
        cur.execute(
            "INSERT INTO analysis_debate (session_id, scrip, role, round, content) VALUES (%s,%s,%s,%s,%s)",
            (session_id, None, "judge", 1, j.get("reasoning", "")),
        )
