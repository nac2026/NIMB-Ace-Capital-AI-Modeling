"""get_dividend_history(scrip) → annual dividend yield + cash/bonus events.

Stitches gold.dividend_yield (annual aggregate per fiscal year) with
silver.corporate_actions (raw event log). Useful for 'has NABIL paid
consistent dividends?' or 'what's NABIL's yield vs FD?' questions."""
from __future__ import annotations
from datetime import date

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_dividend_history"


class GetDividendHistoryInput(BaseModel):
    scrip: str = Field(..., description="NEPSE scrip symbol.")
    years: int = Field(10, ge=1, le=20, description="Fiscal years of annual history.")


class AnnualYieldRow(BaseModel):
    fiscal_year_bs: int
    annual_cash_div_pct: float | None = None
    annual_bonus_pct: float | None = None
    market_value_per_share: float | None = None
    cash_dividend_yield: float | None = None
    total_dividend_yield: float | None = None
    yield_tier: str | None = None


class ActionEvent(BaseModel):
    action_type: str
    ratio: float | None = None
    amount: float | None = None
    announcement_date: date | None = None
    fiscal_year_bs: int | None = None


class DividendHistoryPayload(BaseModel):
    scrip: str
    annual: list[AnnualYieldRow]
    actions: list[ActionEvent]


def get_dividend_history(
    scrip: str,
    *,
    years: int = 10,
    pg: PostgresClient | None = None,
) -> ToolResponse[DividendHistoryPayload]:
    pg = pg or PostgresClient()
    scrip = scrip.strip().upper()

    with _timed() as t:
        annual_rows = pg.fetch_all(
            """
            SELECT fiscal_year_bs,
                   annual_cash_div_pct, annual_bonus_pct,
                   market_value_per_share,
                   cash_dividend_yield, total_dividend_yield, yield_tier,
                   computed_at
            FROM dividend_yield
            WHERE scrip = %s
            ORDER BY fiscal_year_bs DESC
            LIMIT %s
            """,
            (scrip, years),
        )
        actions = pg.fetch_all(
            """
            SELECT action_type, ratio, amount, announcement_date, fiscal_year_bs
            FROM corporate_actions
            WHERE scrip = %s
            ORDER BY announcement_date DESC NULLS LAST
            LIMIT 40
            """,
            (scrip,),
        )
    if not annual_rows and not actions:
        raise ToolError(f"No dividend history for {scrip}", tool=TOOL_NAME, reason="not_found")

    data_as_of = max((r["computed_at"] for r in annual_rows), default=None)
    payload = DividendHistoryPayload(
        scrip=scrip,
        annual=[AnnualYieldRow.model_validate({k: v for k, v in r.items() if k != "computed_at"}) for r in annual_rows],
        actions=[ActionEvent.model_validate(r) for r in actions],
    )
    return build_response(
        tool=TOOL_NAME, data=payload,
        sources=["postgres.dividend_yield", "postgres.corporate_actions"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return annual dividend yield history (cash + bonus) plus the raw "
        "cash-dividend / bonus / rights event log. yield_tier buckets as "
        "ABOVE_FD_RATE / MODERATE / LOW (FD benchmark ≈ 8%). Use for "
        "dividend-consistency, yield-vs-FD, and upcoming/historical corporate "
        "action questions."
    ),
    "input_schema": GetDividendHistoryInput.model_json_schema(),
}
