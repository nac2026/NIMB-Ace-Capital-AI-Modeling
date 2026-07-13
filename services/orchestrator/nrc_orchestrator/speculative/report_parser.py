"""Parse an uploaded research report → structured thesis + claims.

Step 1 of the review pipeline. Extracts text from PDF (PyMuPDF) / DOCX
(python-docx) / plain text, then uses Gemini to pull out the investment
thesis, the recommendation + target price, the scrips/sectors discussed, and
every checkable factual claim (so claim_verifier can test each against our
data). Robust to messy reports — returns whatever it can, never raises on a
malformed LLM response."""
from __future__ import annotations

import io
import json
import logging

from nrc_llm import LLMClient, Message, Role, get_router
from pydantic import BaseModel, Field

_log = logging.getLogger("nrc_orchestrator.speculative.report_parser")


class ParsedClaim(BaseModel):
    scrip: str | None = None                 # resolved if the claim is company-specific
    claim_text: str
    claim_type: str = "other"                # metric | thesis | recommendation | sector | other


class ParsedReport(BaseModel):
    thesis: str = ""
    recommendation: str | None = None        # BUY | ACCUMULATE | HOLD | SELL | AVOID | (free text)
    target_price: float | None = None
    scrips: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    claims: list[ParsedClaim] = Field(default_factory=list)
    raw_text_chars: int = 0


def extract_text(content: bytes, filename: str) -> str:
    """Extract plain text from PDF / DOCX / TXT bytes."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        import pymupdf  # type: ignore
        doc = pymupdf.open(stream=content, filetype="pdf")
        try:
            return "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()
    if name.endswith(".docx"):
        import docx  # python-docx
        d = docx.Document(io.BytesIO(content))
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    # txt / fallback
    try:
        return content.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""


_SYSTEM = """You are an investment-committee analyst at a Nepali capital fund. You are given the \
text of an internal research report. Extract its structure as STRICT JSON (no prose, no markdown fences):

{"thesis": "<2-4 sentence summary of the core investment argument>",
 "recommendation": "BUY|ACCUMULATE|HOLD|SELL|AVOID or null",
 "target_price": <number or null>,
 "scrips": ["<NEPSE ticker symbols explicitly recommended/analyzed>"],
 "sectors": ["<sectors discussed>"],
 "claims": [{"scrip": "<ticker or null>", "claim_type": "metric|thesis|recommendation|sector",
             "claim_text": "<one specific, checkable assertion>"}]}

Rules: claims must be SPECIFIC and CHECKABLE against market/financial data (e.g. "NABIL's NPL is 2.1%", \
"commercial bank sector PE is 36", "profitability grew 15.99%") — not vague opinions. Use NEPSE ticker \
symbols (NABIL, NICASIA, etc.) where a company is named. Limit `claims` to the 25 MOST MATERIAL, \
decision-relevant assertions (keep each concise). Return [] / null for anything absent."""


def _parse_json_object(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text
        text = text.lstrip("json").strip().strip("`").strip()
    start = text.find("{")
    if start == -1:
        return {}
    body = text[start:]
    # Fast path: well-formed JSON.
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    # Salvage truncated output: keep complete top-level claim objects, then
    # close the array + object. Handles responses cut off at max_tokens.
    last = body.rfind("}")
    while last > 0:
        candidate = body[: last + 1]
        for suffix in ("", "]}", "}"):
            try:
                return json.loads(candidate + suffix)
            except json.JSONDecodeError:
                continue
        last = body.rfind("}", 0, last)
    return {}


def parse_report(text: str, *, llm: LLMClient | None = None, max_chars: int = 24000) -> ParsedReport:
    """LLM-extract the report structure. `text` is truncated to max_chars."""
    llm = llm or get_router().synthesizer()
    body = (text or "")[:max_chars]
    if not body.strip():
        return ParsedReport(raw_text_chars=0)

    try:
        resp = llm.complete(
            [Message(role=Role.USER, content=f"REPORT TEXT:\n{body}")],
            system=_SYSTEM, tools=None, max_output_tokens=8192, temperature=0.1,
        )
        obj = _parse_json_object(resp.content)
    except Exception:  # noqa: BLE001
        _log.exception("report parse failed")
        obj = {}

    claims = []
    for c in obj.get("claims", []) or []:
        if isinstance(c, dict) and c.get("claim_text"):
            scrip = c.get("scrip")
            claims.append(ParsedClaim(
                scrip=(scrip.strip().upper() if isinstance(scrip, str) and scrip.strip() else None),
                claim_text=str(c["claim_text"])[:600],
                claim_type=str(c.get("claim_type", "other")),
            ))

    tp = obj.get("target_price")
    try:
        tp = float(tp) if tp is not None else None
    except (TypeError, ValueError):
        tp = None

    return ParsedReport(
        thesis=str(obj.get("thesis", ""))[:2000],
        recommendation=(obj.get("recommendation") or None),
        target_price=tp,
        scrips=[str(s).strip().upper() for s in (obj.get("scrips") or []) if str(s).strip()],
        sectors=[str(s).strip() for s in (obj.get("sectors") or []) if str(s).strip()],
        claims=claims,
        raw_text_chars=len(body),
    )
