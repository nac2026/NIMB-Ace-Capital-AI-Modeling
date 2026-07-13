"""get_broker_concentration(scrip, days=10) → is one broker controlling a side?

From postgres.broker_concentration_daily. HHI (0..1, 1 = monopoly) plus the
single biggest broker's share (top1) and the top-3 share, per trading day, for
buy and sell sides. dominance_flag = top1 > 30%; control_flag = top3 > 60%.
High, persistent values mean a few brokers are steering the stock — the desk's
'operator behaviour' signal."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_broker_concentration"


class GetBrokerConcentrationInput(BaseModel):
    scrip: str = Field(..., description="NEPSE scrip symbol.")
    days: int = Field(10, ge=1, le=120, description="Most recent N trading days (default 10).")


class ConcentrationRow(BaseModel):
    trade_date: str
    n_brokers: int | None = None
    hhi_buy: float | None = None
    hhi_sell: float | None = None
    top1_buy_share: float | None = None
    top1_sell_share: float | None = None
    top3_buy_share: float | None = None
    top3_sell_share: float | None = None
    buy_dominance_flag: bool | None = None
    sell_dominance_flag: bool | None = None
    buy_control_flag: bool | None = None
    sell_control_flag: bool | None = None
    concentration_flag: bool | None = None


def get_broker_concentration(
    scrip: str,
    *,
    days: int = 10,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[ConcentrationRow]]:
    pg = pg or PostgresClient()
    scrip = scrip.strip().upper()

    with _timed() as t:
        rows = pg.fetch_all(
            """
            SELECT trade_date, n_brokers, hhi_buy, hhi_sell,
                   top1_buy_share, top1_sell_share, top3_buy_share, top3_sell_share,
                   buy_dominance_flag, sell_dominance_flag,
                   buy_control_flag, sell_control_flag, concentration_flag, computed_at
            FROM broker_concentration_daily
            WHERE scrip = %s
            ORDER BY trade_date DESC
            LIMIT %s
            """,
            (scrip, days),
        )
    if not rows:
        raise ToolError(f"No floor-sheet concentration data for {scrip}", tool=TOOL_NAME, reason="not_found")

    data_as_of = max(r["computed_at"] for r in rows)
    results = [
        ConcentrationRow.model_validate(
            {**{k: v for k, v in r.items() if k != "computed_at"}, "trade_date": str(r["trade_date"])}
        )
        for r in rows
    ]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.broker_concentration_daily"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Per-day broker concentration for a scrip from the floor-sheet: HHI "
        "(0-1), the single biggest broker's share (top1) and top-3 share on buy "
        "and sell sides, with dominance (top1>30%) and control (top3>60%) flags. "
        "Use to answer 'is one broker controlling this stock?' or 'is trading "
        "concentrated in a few hands?'."
    ),
    "input_schema": GetBrokerConcentrationInput.model_json_schema(),
}
