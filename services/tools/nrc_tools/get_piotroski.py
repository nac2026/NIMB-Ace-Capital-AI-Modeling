"""get_piotroski(scrip, quarters=8) → bank-adapted F-Score + 9 signal values.

From gold.piotroski_f_score. The LLM should cite individual signals
("the F-Score dropped because p5_npl_not_worse = 0 — NPL worsened YoY")
rather than just the composite number."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_piotroski"


class GetPiotroskiInput(BaseModel):
    scrip: str = Field(..., description="NEPSE scrip symbol.")
    quarters: int = Field(8, ge=1, le=40, description="Lookback in quarters (default 8).")


class PiotroskiRow(BaseModel):
    fiscal_year_bs: int
    quarter: int
    p1_positive_profit: int | None = None
    p2_positive_roa: int | None = None
    p3_profit_grew: int | None = None
    p4_roa_improved: int | None = None
    p5_npl_not_worse: int | None = None
    p6_car_not_worse: int | None = None
    p7_no_large_issuance: int | None = None
    p8_nim_improved: int | None = None
    p9_cti_improved: int | None = None
    f_score: int | None = None
    n_signals_available: int | None = None


def get_piotroski(
    scrip: str,
    *,
    quarters: int = 8,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[PiotroskiRow]]:
    pg = pg or PostgresClient()
    scrip = scrip.strip().upper()

    with _timed() as t:
        rows = pg.fetch_all(
            """
            SELECT fiscal_year_bs, quarter,
                   p1_positive_profit, p2_positive_roa, p3_profit_grew,
                   p4_roa_improved,    p5_npl_not_worse, p6_car_not_worse,
                   p7_no_large_issuance, p8_nim_improved, p9_cti_improved,
                   f_score, n_signals_available, computed_at
            FROM piotroski_f_score
            WHERE scrip = %s
            ORDER BY fiscal_year_bs DESC, quarter DESC
            LIMIT %s
            """,
            (scrip, quarters),
        )
    if not rows:
        raise ToolError(f"No Piotroski data for {scrip}", tool=TOOL_NAME, reason="not_found")
    rows.reverse()

    data_as_of = max(r["computed_at"] for r in rows)
    results = [PiotroskiRow.model_validate({k: v for k, v in r.items() if k != "computed_at"}) for r in rows]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.piotroski_f_score"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return bank-adapted Piotroski F-Score over N quarters with the 9 "
        "individual signal values. Signals: positive profit, positive ROA, "
        "profit grew YoY, ROA improved YoY, NPL not worse YoY, CAR not worse, "
        "no large share issuance, NIM improved, cost-to-income improved. "
        "Score 0-9 (7+ strong, 0-3 weak). Always cite specific failed "
        "signals when explaining the score."
    ),
    "input_schema": GetPiotroskiInput.model_json_schema(),
}
