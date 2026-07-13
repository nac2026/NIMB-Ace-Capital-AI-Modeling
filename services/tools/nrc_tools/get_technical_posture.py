"""get_technical_posture(scrip) → the 5 technical-signal rule votes.

From gold.technical_signal_summary. Returns r1..r5 + the composite
signal_sum. The `technical_signal` label (STRONG_BUY/BUY/HOLD/SELL/
STRONG_SELL) is in the payload but the agent system prompt enforces
neutral framing — cite the vote breakdown, not the label as advice."""
from __future__ import annotations
from datetime import date

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_technical_posture"


class GetTechnicalPostureInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description="NEPSE scrip or list. Returns the 5-rule technical vote breakdown per scrip.",
    )


class TechnicalPostureResult(BaseModel):
    scrip: str
    latest_indicator_date: date | None = None
    close: float | None = None
    # Individual rule votes (-1 / 0 / +1 each)
    r1_trend: int | None = None
    r2_ma_align: int | None = None
    r3_rsi: int | None = None
    r4_macd: int | None = None
    r5_bollinger: int | None = None
    # Composite
    signal_sum: int | None = None
    technical_signal: str | None = None   # STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL


def get_technical_posture(
    scrip: str | list[str],
    *,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[TechnicalPostureResult]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT scrip, latest_indicator_date, close,
                   r1_trend, r2_ma_align, r3_rsi, r4_macd, r5_bollinger,
                   signal_sum, technical_signal, computed_at
            FROM technical_signal_summary
            WHERE scrip IN ({ph})
            """,
            tuple(scrips),
        )
    if not rows:
        raise ToolError(f"No technical posture for scrip(s)={scrips}", tool=TOOL_NAME, reason="not_found")

    data_as_of = max(r["computed_at"] for r in rows)
    results = [TechnicalPostureResult.model_validate({k: v for k, v in r.items() if k != "computed_at"}) for r in rows]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.technical_signal_summary"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return the 5-rule technical-posture breakdown per scrip — r1_trend "
        "(close vs 200-day MA), r2_ma_align (20/50/200 alignment), r3_rsi "
        "(overbought/oversold), r4_macd (direction), r5_bollinger (envelope). "
        "Each is -1/0/+1; signal_sum is [-5,+5]. Cite the individual votes "
        "when explaining — e.g. 'r1_trend=-1 (below 200-day MA), r3_rsi=0 "
        "(neutral)'. Don't render technical_signal as a BUY/SELL call."
    ),
    "input_schema": GetTechnicalPostureInput.model_json_schema(),
}
