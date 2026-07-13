"""get_asset_quality(scrip, quarters=8) → NPL trajectory + LLP coverage.

From gold.asset_quality_trends. Asset quality DIRECTION matters more than
level — a scrip at 4% NPL rising is worse than one at 5% falling. This
tool surfaces the trajectory (QoQ + YoY) plus the LLP coverage trend."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_asset_quality"


class GetAssetQualityInput(BaseModel):
    scrip: str = Field(..., description="NEPSE scrip symbol.")
    quarters: int = Field(8, ge=1, le=40, description="Lookback in quarters (default 8 ≈ 2y).")


class AssetQualityRow(BaseModel):
    fiscal_year_bs: int
    quarter: int
    npl_ratio: float | None = None
    llp_to_npl_ratio: float | None = None
    npl_qoq_change_abs: float | None = None
    npl_yoy_change_abs: float | None = None
    llp_coverage_yoy_change: float | None = None
    credit_loss_rate_ttm: float | None = None
    asset_quality_tier: str | None = None


def get_asset_quality(
    scrip: str,
    *,
    quarters: int = 8,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[AssetQualityRow]]:
    pg = pg or PostgresClient()
    scrip = scrip.strip().upper()

    with _timed() as t:
        rows = pg.fetch_all(
            """
            SELECT fiscal_year_bs, quarter,
                   npl_ratio, llp_to_npl_ratio,
                   npl_qoq_change_abs, npl_yoy_change_abs, llp_coverage_yoy_change,
                   credit_loss_rate_ttm, asset_quality_tier, computed_at
            FROM asset_quality_trends
            WHERE scrip = %s
            ORDER BY fiscal_year_bs DESC, quarter DESC
            LIMIT %s
            """,
            (scrip, quarters),
        )
    if not rows:
        raise ToolError(f"No asset-quality data for {scrip}", tool=TOOL_NAME, reason="not_found")
    rows.reverse()

    data_as_of = max(r["computed_at"] for r in rows)
    results = [AssetQualityRow.model_validate({k: v for k, v in r.items() if k != "computed_at"}) for r in rows]
    return build_response(
        tool=TOOL_NAME, data=results,
        sources=["postgres.asset_quality_trends"],
        data_as_of=data_as_of, latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return NPL ratio trajectory + LLP coverage + TTM credit-loss rate "
        "over last N quarters. Includes YoY/QoQ absolute deltas so the LLM "
        "can distinguish direction from level. asset_quality_tier buckets "
        "as STRONG/MODERATE/WEAK. Use for 'is NABIL's NPL improving?' or "
        "credit-risk questions."
    ),
    "input_schema": GetAssetQualityInput.model_json_schema(),
}
