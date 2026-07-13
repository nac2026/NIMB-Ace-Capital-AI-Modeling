"""get_scorecard(scrip) → composite 0-100 score + 5 component percentiles.

Pulls from gold.investment_scorecard. The `recommendation` column (STRONG_BUY,
BUY, HOLD, REDUCE, SELL) IS returned in the payload — the agent system prompt
enforces "show data, not verdicts", so the LLM should summarize the components
numerically and not surface a BUY/SELL call unless the user explicitly asks
what the composite model's label is."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_scorecard"


class GetScorecardInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description="NEPSE scrip symbol or list (e.g. 'NABIL' or ['NABIL','NICA']). "
                    "Pass a list to compare scorecards across banks.",
    )


class ScorecardResult(BaseModel):
    scrip: str
    sector: str | None = None
    # 5 component percentiles (0-100)
    quality_pct: float | None = None
    valuation_pct: float | None = None
    momentum_pct: float | None = None
    risk_pct: float | None = None
    income_pct: float | None = None
    # Composite + underlying raw values
    quality_score_0_100: float | None = None
    pe_self_pct_5y: float | None = None
    return_6m: float | None = None
    sharpe_ratio_2y: float | None = None
    total_dividend_yield: float | None = None
    scorecard_0_100: float | None = None
    recommendation: str | None = None


def get_scorecard(
    scrip: str | list[str],
    *,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[ScorecardResult]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT scrip, sector,
                   quality_pct, valuation_pct, momentum_pct, risk_pct, income_pct,
                   quality_score_0_100, pe_self_pct_5y, return_6m,
                   sharpe_ratio_2y, total_dividend_yield,
                   scorecard_0_100, recommendation, computed_at
            FROM investment_scorecard
            WHERE scrip IN ({ph})
            """,
            tuple(scrips),
        )
    if not rows:
        raise ToolError(f"No scorecard for scrip(s)={scrips}", tool=TOOL_NAME, reason="not_found")

    data_as_of = max(r["computed_at"] for r in rows)
    results = [ScorecardResult.model_validate({k: v for k, v in r.items() if k != "computed_at"}) for r in rows]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.investment_scorecard"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return the composite analytics scorecard for one or more scrips. "
        "Returns 0-100 composite plus 5 component percentiles (quality, valuation, "
        "momentum, risk, income). Includes the underlying metrics (6m return, "
        "Sharpe, dividend yield, valuation self-percentile). Use for "
        "'how does NABIL score?' or comparative screening questions. Summarize "
        "as data — do NOT surface the recommendation label as a BUY/SELL call."
    ),
    "input_schema": GetScorecardInput.model_json_schema(),
}
