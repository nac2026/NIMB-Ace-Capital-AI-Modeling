"""get_peer_rankings(scrip, metric?) → sector rank + percentile + median for metric(s)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import PeerRanking, Quarter, ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_peer_rankings"

_VALID_METRICS = (
    "roe", "roa", "npl_ratio", "car", "cd_ratio", "eps", "bvps",
    "pe_ratio", "pb_ratio", "net_profit", "operating_profit",
    "net_interest_income", "total_deposits", "total_loans", "paid_up_capital",
)


class GetPeerRankingsInput(BaseModel):
    scrip: str = Field(..., description="NEPSE scrip symbol")
    metric: str | None = Field(
        default=None,
        description=(
            "Which metric to rank. One of: roe, roa, npl_ratio, car, cd_ratio, "
            "eps, bvps, pe_ratio, pb_ratio, net_profit, operating_profit, "
            "net_interest_income, total_deposits, total_loans, paid_up_capital. "
            "Omit for all metrics."
        ),
    )


def get_peer_rankings(
    scrip: str,
    *,
    metric: str | None = None,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[PeerRanking]]:
    pg = pg or PostgresClient()
    scrip = scrip.strip().upper()
    if metric is not None and metric not in _VALID_METRICS:
        raise ToolError(
            f"Unknown metric {metric!r}. Valid: {_VALID_METRICS}",
            tool=TOOL_NAME,
            reason="bad_input",
        )

    with _timed() as t:
        if metric is not None:
            rows = pg.fetch_all(
                """
                SELECT * FROM peer_rankings_quarterly
                WHERE scrip=%s AND metric_name=%s
                ORDER BY fiscal_year_bs DESC, quarter DESC
                """,
                (scrip, metric),
            )
        else:
            rows = pg.fetch_all(
                """
                SELECT * FROM peer_rankings_quarterly
                WHERE scrip = %s
                ORDER BY fiscal_year_bs DESC, quarter DESC, metric_name ASC
                """,
                (scrip,),
            )

    if not rows:
        raise ToolError(
            f"No peer rankings for {scrip!r} metric={metric!r}",
            tool=TOOL_NAME,
            reason="not_found",
        )

    rankings = []
    for r in rows:
        r["quarter"] = Quarter(r["quarter"])
        rankings.append(PeerRanking.model_validate(r))

    return build_response(
        tool=TOOL_NAME,
        data=rankings,
        sources=["postgres.peer_rankings_quarterly"],
        data_as_of=rows[0]["computed_at"],
        latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Get a scrip's rank + percentile + sector median/mean for one or all metrics.\n\n"
        "IMPORTANT: percentile_in_sector is ALWAYS normalized so 1.0 = best-in-sector, "
        "regardless of metric direction. For 'higher is better' metrics (ROE, ROA, EPS, "
        "CAR, net_profit, etc.) rank 1 = highest value. For 'lower is better' metrics "
        "(npl_ratio only, currently) rank 1 = lowest value. sector_median and sector_mean "
        "are always in the metric's native units.\n\n"
        "Use for 'where does X rank in ROE?', 'is X's NPL worse than peers?', "
        "or 'show me X's complete peer comparison'."
    ),
    "input_schema": GetPeerRankingsInput.model_json_schema(),
}
