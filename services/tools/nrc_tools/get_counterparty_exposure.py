"""get_counterparty_exposure(scrip?/client?, min_trades=2) → who keeps facing the fund?

From postgres.internal_counterparty_exposure — the collusion-proxy pattern table.
For each (fund, counterparty broker, scrip): how often the fund traded against
that broker, the broker's actual market share in the scrip, and a one-sample
proportion z-score for how improbable the pairing is under random routing.
surprise_z ≥ ~3 with several fills = "this routing is very unlikely to be
chance"; worse when the broker is independently market-flagged (accumulating /
distributing / wash pair) in that scrip. A flag for review, not a verdict."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_counterparty_exposure"


class GetCounterpartyExposureInput(BaseModel):
    scrip: str | None = Field(None, description="Filter to one NEPSE scrip (optional).")
    client_code: str | None = Field(None, description="Filter to one fund/portfolio account code (optional).")
    min_trades: int = Field(2, ge=1, le=100, description="Only pairings with at least this many fills (default 2).")
    limit: int = Field(30, ge=1, le=200, description="Max pairings to return (default 30).")


class ExposureRow(BaseModel):
    client_code: str
    client_name: str | None = None
    counterparty_broker: int
    counterparty_broker_name: str | None = None
    scrip: str
    n_trades: int
    total_qty: float | None = None
    total_amount: float | None = None
    n_days: int | None = None
    first_date: str | None = None
    last_date: str | None = None
    share_of_fund_qty: float | None = None
    cp_market_share: float | None = None
    surprise_z: float | None = None
    cp_is_accumulator: bool | None = None
    cp_is_distributor: bool | None = None
    cp_in_wash_pair: bool | None = None
    cp_flagged: bool | None = None


def get_counterparty_exposure(
    scrip: str | None = None,
    *,
    client_code: str | None = None,
    min_trades: int = 2,
    limit: int = 30,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[ExposureRow]]:
    pg = pg or PostgresClient()

    where = ["e.n_trades >= %s"]
    params: list = [min_trades]
    if scrip:
        where.append("e.scrip = %s")
        params.append(scrip.strip().upper())
    if client_code:
        where.append("e.client_code = %s")
        params.append(client_code.strip())
    params.append(limit)

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT e.client_code, e.client_name, e.counterparty_broker,
                   b.name AS counterparty_broker_name, e.scrip,
                   e.n_trades, e.total_qty, e.total_amount, e.n_days,
                   e.first_date, e.last_date,
                   e.share_of_fund_qty, e.cp_market_share, e.surprise_z,
                   e.cp_is_accumulator, e.cp_is_distributor, e.cp_in_wash_pair,
                   e.cp_flagged, e.computed_at
            FROM internal_counterparty_exposure e
            LEFT JOIN brokers b ON b.broker = e.counterparty_broker
            WHERE {' AND '.join(where)}
            ORDER BY e.surprise_z DESC NULLS LAST
            LIMIT %s
            """,
            tuple(params),
        )
    if not rows:
        raise ToolError(
            "No counterparty exposure patterns match that filter.",
            tool=TOOL_NAME, reason="not_found",
        )

    data_as_of = max(r["computed_at"] for r in rows)
    results = [
        ExposureRow.model_validate(
            {**{k: v for k, v in r.items() if k != "computed_at"},
             "first_date": str(r["first_date"]) if r["first_date"] else None,
             "last_date": str(r["last_date"]) if r["last_date"] else None}
        )
        for r in rows
    ]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.internal_counterparty_exposure"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Counterparty repeat-trading patterns for the firm's OWN trades — which "
        "brokers keep ending up on the other side of a fund's flow, far beyond "
        "their market share in that scrip. Returns, per (fund, broker, scrip): "
        "number of fills, the fund's share of flow against that broker, the "
        "broker's actual market share, a surprise z-score (≥3 = statistically "
        "improbable routing), and whether the broker is market-flagged "
        "(accumulating/distributing/wash) in the scrip. The collusion-proxy "
        "signal. Use for 'which broker patterns look suspicious in our own trading?'."
    ),
    "input_schema": GetCounterpartyExposureInput.model_json_schema(),
}
