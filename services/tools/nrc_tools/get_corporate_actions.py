"""get_corporate_actions(scrip, limit?) → dividend/bonus/rights history.

Accepts a single scrip or a list — returns actions for all requested scrips."""
from __future__ import annotations

from pydantic import BaseModel, Field

from nrc_contracts import ActionType, CorporateAction, ToolResponse
from nrc_storage import PostgresClient

from ._base import ToolError, _timed, build_response

TOOL_NAME = "get_corporate_actions"


class GetCorporateActionsInput(BaseModel):
    scrip: str | list[str] = Field(
        ...,
        description="NEPSE scrip symbol or list of symbols, e.g. 'NABIL' or ['NABIL','EBL']. "
                    "Pass a list to compare dividend/bonus history across banks.",
    )
    limit: int = Field(
        default=20, ge=1, le=100,
        description="Max number of actions per scrip to return, newest first.",
    )


def get_corporate_actions(
    scrip: str | list[str],
    *,
    limit: int = 20,
    pg: PostgresClient | None = None,
) -> ToolResponse[list[CorporateAction]]:
    pg = pg or PostgresClient()
    scrips = [scrip] if isinstance(scrip, str) else list(scrip)
    scrips = [s.strip().upper() for s in scrips]
    ph = ", ".join(["%s"] * len(scrips))

    with _timed() as t:
        rows = pg.fetch_all(
            f"""
            SELECT * FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY scrip
                        ORDER BY COALESCE(announcement_date, ex_date, book_closure_date) DESC NULLS LAST
                    ) AS rn
                FROM corporate_actions
                WHERE scrip IN ({ph})
            ) t
            WHERE rn <= %s
            ORDER BY scrip, COALESCE(announcement_date, ex_date, book_closure_date) DESC NULLS LAST
            """,
            (*scrips, limit),
        )

    if not rows:
        raise ToolError(
            f"No corporate actions for scrip(s)={scrips}",
            tool=TOOL_NAME, reason="not_found",
        )

    actions = []
    for r in rows:
        r.pop("rn", None)
        r["action_type"] = ActionType(r["action_type"])
        actions.append(CorporateAction.model_validate(r))

    return build_response(
        tool=TOOL_NAME, data=actions,
        sources=["postgres.corporate_actions"], latency_ms=t["latency_ms"],
    )


TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Get dividend, bonus share, and rights issue history for one or more scrips, newest first. "
        "Pass a list for comparisons: e.g. scrip=['NABIL','EBL']. "
        "Use for dividend history, upcoming bonus, rights history, or dividend-yield calculations."
    ),
    "input_schema": GetCorporateActionsInput.model_json_schema(),
}
