"""get_broker_accumulation(scrip, top_n=5) → which brokers are building/exiting.

From postgres.broker_accumulation. Returns the top net accumulators and top net
distributors of a scrip over the loaded floor-sheet window, with each broker's
cumulative net quantity, share of the scrip's traded volume, and persistence
(days net-buying / days active). accumulation_flag marks a persistent, material
net buyer — the 'an operator is quietly building a position' signal."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_broker_accumulation"


class GetBrokerAccumulationInput(BaseModel):
    scrip: str = Field(..., description="NEPSE scrip symbol.")
    top_n: int = Field(5, ge=1, le=20, description="How many brokers per side (default 5).")


class BrokerPosition(BaseModel):
    broker: int
    cum_net_qty: float | None = None
    cum_net_amount: float | None = None
    volume_share: float | None = None
    days_active: int | None = None
    days_net_buy: int | None = None
    days_net_sell: int | None = None
    accumulation_flag: bool | None = None
    distribution_flag: bool | None = None


class BrokerAccumulation(BaseModel):
    scrip: str
    window_first_day: str | None = None
    window_last_day: str | None = None
    top_accumulators: list[BrokerPosition]
    top_distributors: list[BrokerPosition]


def get_broker_accumulation(
    scrip: str,
    *,
    top_n: int = 5,
    pg: PostgresClient | None = None,
) -> ToolResponse[BrokerAccumulation]:
    pg = pg or PostgresClient()
    scrip = scrip.strip().upper()

    cols = (
        "broker, cum_net_qty, cum_net_amount, volume_share, "
        "days_active, days_net_buy, days_net_sell, "
        "accumulation_flag, distribution_flag, first_day, last_day, computed_at"
    )
    with _timed() as t:
        acc = pg.fetch_all(
            f"SELECT {cols} FROM broker_accumulation WHERE scrip = %s "
            "ORDER BY cum_net_qty DESC LIMIT %s",
            (scrip, top_n),
        )
        dist = pg.fetch_all(
            f"SELECT {cols} FROM broker_accumulation WHERE scrip = %s "
            "ORDER BY cum_net_qty ASC LIMIT %s",
            (scrip, top_n),
        )
    if not acc:
        raise ToolError(f"No broker-flow data for {scrip}", tool=TOOL_NAME, reason="not_found")

    def _pos(r: dict) -> BrokerPosition:
        return BrokerPosition.model_validate({k: v for k, v in r.items()
                                              if k in BrokerPosition.model_fields})

    data = BrokerAccumulation(
        scrip=scrip,
        window_first_day=str(acc[0]["first_day"]) if acc[0].get("first_day") else None,
        window_last_day=str(acc[0]["last_day"]) if acc[0].get("last_day") else None,
        top_accumulators=[_pos(r) for r in acc],
        top_distributors=[_pos(r) for r in dist],
    )
    data_as_of = max(r["computed_at"] for r in acc)
    return build_response(
        tool=TOOL_NAME, data=data,
        sources=["postgres.broker_accumulation"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Top net accumulating and net distributing brokers for a scrip from the "
        "floor-sheet, with each broker's cumulative net quantity, share of the "
        "scrip's traded volume, and persistence (days net-buying). "
        "accumulation_flag marks a persistent, material net buyer. Use for 'is "
        "any broker accumulating/controlling this stock?' or 'who is buying X?'."
    ),
    "input_schema": GetBrokerAccumulationInput.model_json_schema(),
}
