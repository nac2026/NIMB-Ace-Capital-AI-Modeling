"""get_internal_surveillance(scrip?/client?, min_score=45) → suspicious internal trades.

From postgres.internal_trade_surveillance — the firm's OWN executed fills, scored
0-100 for how suspicious they look. Each fill is joined to the public floor sheet
(to recover the counterparty broker) and cross-referenced against the market
manipulation signals. Surfaces fills that were bad vs the day's VWAP / traded
range, or that landed in scrips already flagged speculative / concentrated /
wash-trading / pumped. A flag for review, not a verdict. Answers the CEO's
question: 'which of our own trades look fishy?'"""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_internal_surveillance"


class GetInternalSurveillanceInput(BaseModel):
    scrip: str | None = Field(None, description="Filter to one NEPSE scrip (optional).")
    client_code: str | None = Field(None, description="Filter to one fund/portfolio account code (optional).")
    min_score: float = Field(45, ge=0, le=100, description="Only fills with surveillance_score ≥ this (default 45 = ELEVATED+).")
    limit: int = Field(50, ge=1, le=500, description="Max fills to return (default 50).")


class SurveillanceRow(BaseModel):
    contract_number: int
    trade_date: str
    scrip: str
    client_code: str
    client_name: str | None = None
    side: str
    our_qty: float | None = None
    our_value: float | None = None
    our_price: float | None = None
    day_vwap: float | None = None
    our_broker: int | None = None
    our_broker_name: str | None = None
    counterparty_broker: int | None = None
    counterparty_broker_name: str | None = None
    slippage_vs_vwap_pct: float | None = None
    slippage_npr: float | None = None
    worse_than_range_flag: bool | None = None
    markout_5d_pct: float | None = None
    cp_surprise_z: float | None = None
    exit_liquidity_flag: bool | None = None
    cross_flag: bool | None = None
    churn_flag: bool | None = None
    bought_near_peak_flag: bool | None = None
    scrip_speculation_tier: str | None = None
    scrip_concentration_flag: bool | None = None
    scrip_pump_flag: bool | None = None
    surveillance_score: float | None = None
    surveillance_tier: str | None = None
    flag_reasons: list[str] | None = None


def get_internal_surveillance(
    scrip: str | None = None,
    *,
    client_code: str | None = None,
    min_score: float = 45,
    limit: int = 50,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[SurveillanceRow]]:
    pg = pg or PostgresClient()

    where = ["surveillance_score >= %s"]
    params: list = [min_score]
    if scrip:
        where.append("scrip = %s")
        params.append(scrip.strip().upper())
    if client_code:
        where.append("client_code = %s")
        params.append(client_code.strip())
    params.append(limit)

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT s.contract_number, s.trade_date, s.scrip, s.client_code, s.client_name, s.side,
                   s.our_qty, s.our_value, s.our_price, s.day_vwap, s.our_broker, s.counterparty_broker,
                   ob.name AS our_broker_name, cb.name AS counterparty_broker_name,
                   s.slippage_vs_vwap_pct, s.slippage_npr, s.worse_than_range_flag,
                   s.markout_5d_pct, s.cp_surprise_z, s.exit_liquidity_flag,
                   s.cross_flag, s.churn_flag, s.bought_near_peak_flag,
                   s.scrip_speculation_tier, s.scrip_concentration_flag, s.scrip_pump_flag,
                   s.surveillance_score, s.surveillance_tier, s.flag_reasons, s.computed_at
            FROM internal_trade_surveillance s
            LEFT JOIN brokers ob ON ob.broker = s.our_broker
            LEFT JOIN brokers cb ON cb.broker = s.counterparty_broker
            WHERE {' AND '.join(where)}
            ORDER BY s.surveillance_score DESC, s.trade_date DESC
            LIMIT %s
            """,
            tuple(params),
        )
    if not rows:
        raise ToolError(
            "No internal trades match that surveillance filter.",
            tool=TOOL_NAME, reason="not_found",
        )

    data_as_of = max(r["computed_at"] for r in rows)
    results = [
        SurveillanceRow.model_validate(
            {**{k: v for k, v in r.items() if k != "computed_at"},
             "trade_date": str(r["trade_date"])}
        )
        for r in rows
    ]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.internal_trade_surveillance"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Suspicious INTERNAL trades — the firm's own fills scored 0-100 for how "
        "fishy they look, from internal_trade_surveillance. Each fill carries its "
        "slippage vs the day's VWAP, whether it filled outside the traded range, "
        "the recovered counterparty broker, whether the scrip is flagged "
        "speculative/concentrated/pumped, plus a surveillance tier (HIGH/ELEVATED/"
        "MODERATE/LOW) and human-readable flag_reasons. Filter by scrip and/or "
        "client_code (the fund). Use to answer 'which of our own trades look "
        "suspicious?' or 'did fund X get bad fills / trade into manipulated names?'."
    ),
    "input_schema": GetInternalSurveillanceInput.model_json_schema(),
}
