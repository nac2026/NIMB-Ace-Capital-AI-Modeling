"""get_returns(scrip) → 1m/3m/6m/1y/3y/5y price returns + TSR + market risk.

Stitches price_returns + total_shareholder_return + beta_and_volatility
into one snapshot so the LLM answers "how has NABIL done?" with the full
picture — price appreciation, total return including dividends, drawdown,
volatility, Sharpe, and NEPSE beta."""
from __future__ import annotations
from datetime import date

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_returns"


class GetReturnsInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description="NEPSE scrip or list. Returns price returns + total return + market risk per scrip.",
    )


class ReturnsResult(BaseModel):
    scrip: str
    as_of: date | None = None
    close: float | None = None
    # Price-only returns
    return_1m: float | None = None
    return_3m: float | None = None
    return_6m: float | None = None
    return_1y: float | None = None
    return_3y: float | None = None
    return_5y: float | None = None
    drawdown_from_peak: float | None = None
    realized_vol_20d: float | None = None
    # Total shareholder return (incl. dividends)
    tsr_1y: float | None = None
    tsr_3y: float | None = None
    tsr_5y: float | None = None
    # Market risk
    beta: float | None = None
    alpha_annual: float | None = None
    r_squared: float | None = None
    annualized_vol: float | None = None
    sharpe_ratio_2y: float | None = None


def get_returns(
    scrip: str | list[str],
    *,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[ReturnsResult]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT s.scrip,
                   pr.as_of, pr.close,
                   pr.return_1m, pr.return_3m, pr.return_6m,
                   pr.return_1y, pr.return_3y, pr.return_5y,
                   pr.drawdown_from_peak, pr.realized_vol_20d,
                   tsr.tsr_1y, tsr.tsr_3y, tsr.tsr_5y,
                   bv.beta, bv.alpha_annual, bv.r_squared,
                   bv.annualized_vol, bv.sharpe_ratio_2y,
                   GREATEST(
                       COALESCE(pr.computed_at, TIMESTAMP 'epoch'),
                       COALESCE(tsr.computed_at, TIMESTAMP 'epoch'),
                       COALESCE(bv.computed_at, TIMESTAMP 'epoch')
                   ) AS computed_at
            FROM scrips s
            LEFT JOIN price_returns pr            ON pr.scrip  = s.scrip
            LEFT JOIN total_shareholder_return tsr ON tsr.scrip = s.scrip
            LEFT JOIN beta_and_volatility bv       ON bv.scrip  = s.scrip
            WHERE s.scrip IN ({ph})
            """,
            tuple(scrips),
        )
    if not rows:
        raise ToolError(f"No return data for scrip(s)={scrips}", tool=TOOL_NAME, reason="not_found")

    data_as_of = max(r["computed_at"] for r in rows if r["computed_at"] is not None)
    results = [ReturnsResult.model_validate({k: v for k, v in r.items() if k != "computed_at"}) for r in rows]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.price_returns", "postgres.total_shareholder_return", "postgres.beta_and_volatility"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return multi-horizon price returns (1m/3m/6m/1y/3y/5y) + total "
        "shareholder return (incl. dividends) + market-risk metrics (NEPSE "
        "beta, Sharpe, realized vol) for one or more scrips. Use for 'how "
        "has NABIL done?' or multi-horizon return questions."
    ),
    "input_schema": GetReturnsInput.model_json_schema(),
}
