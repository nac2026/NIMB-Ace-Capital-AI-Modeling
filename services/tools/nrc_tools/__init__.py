"""Deterministic research tools — the functions the LLM calls.

Each tool is a plain Python function with a typed Pydantic input schema and
a `ToolResponse[T]` return. The REGISTRY below is what the orchestrator
introspects to build the tool-use payload for the LLM."""
from __future__ import annotations
from typing import Callable

from ._base import ToolError
from ._version import TOOL_VERSION
from .get_corporate_actions import TOOL_SPEC as SPEC_CORP_ACTIONS
from .get_corporate_actions import get_corporate_actions
from .get_live_quote import TOOL_SPEC as SPEC_LIVE_QUOTE
from .get_live_quote import get_live_quote
from .get_fundamentals import TOOL_SPEC as SPEC_FUNDAMENTALS
from .get_fundamentals import get_fundamentals
from .get_fundamentals_history import TOOL_SPEC as SPEC_FUNDAMENTALS_HISTORY
from .get_fundamentals_history import get_fundamentals_history
from .get_news import TOOL_SPEC as SPEC_NEWS
from .get_news import get_news
from .get_peer_rankings import TOOL_SPEC as SPEC_PEER_RANKINGS
from .get_peer_rankings import get_peer_rankings
from .get_price_history import TOOL_SPEC as SPEC_PRICE_HISTORY
from .get_price_history import get_price_history
from .get_quote import TOOL_SPEC as SPEC_QUOTE
from .get_quote import get_quote
from .get_technicals import TOOL_SPEC as SPEC_TECHNICALS
from .get_technicals import get_technicals
from .get_valuation import TOOL_SPEC as SPEC_VALUATION
from .get_valuation import get_valuation
from .list_scrips import TOOL_SPEC as SPEC_LIST_SCRIPS
from .list_scrips import list_scrips
from .stage1_screen import TOOL_SPEC as SPEC_STAGE1
from .stage1_screen import stage1_screen
from .stage2_bank_screen import TOOL_SPEC as SPEC_STAGE2
from .stage2_bank_screen import stage2_bank_screen

# --- Phase I + J tools (Gold-layer analytics access) -------------------
from .get_asset_quality import TOOL_SPEC as SPEC_ASSET_QUALITY
from .get_asset_quality import get_asset_quality
from .get_capital import TOOL_SPEC as SPEC_CAPITAL
from .get_capital import get_capital
from .get_dividend_history import TOOL_SPEC as SPEC_DIVIDEND_HISTORY
from .get_dividend_history import get_dividend_history
from .get_dupont import TOOL_SPEC as SPEC_DUPONT
from .get_dupont import get_dupont
from .get_piotroski import TOOL_SPEC as SPEC_PIOTROSKI
from .get_piotroski import get_piotroski
from .get_quadrant import TOOL_SPEC as SPEC_QUADRANT
from .get_quadrant import get_quadrant
from .get_returns import TOOL_SPEC as SPEC_RETURNS
from .get_returns import get_returns
from .get_scorecard import TOOL_SPEC as SPEC_SCORECARD
from .get_scorecard import get_scorecard
from .get_technical_posture import TOOL_SPEC as SPEC_TECH_POSTURE
from .get_technical_posture import get_technical_posture
from .get_valuation_history import TOOL_SPEC as SPEC_VALUATION_HISTORY
from .get_valuation_history import get_valuation_history

# --- Floor-sheet broker-flow tools (microstructure) --------------------
from .get_broker_concentration import TOOL_SPEC as SPEC_BROKER_CONCENTRATION
from .get_broker_concentration import get_broker_concentration
from .get_broker_accumulation import TOOL_SPEC as SPEC_BROKER_ACCUMULATION
from .get_broker_accumulation import get_broker_accumulation
from .get_speculation_score import TOOL_SPEC as SPEC_SPECULATION_SCORE
from .get_speculation_score import get_speculation_score
from .get_scrip_sentiment import TOOL_SPEC as SPEC_SCRIP_SENTIMENT
from .get_scrip_sentiment import get_scrip_sentiment

# --- Internal-trade surveillance (the firm's own fills) ----------------
from .get_internal_surveillance import TOOL_SPEC as SPEC_INTERNAL_SURVEILLANCE
from .get_internal_surveillance import get_internal_surveillance
from .get_counterparty_exposure import TOOL_SPEC as SPEC_COUNTERPARTY_EXPOSURE
from .get_counterparty_exposure import get_counterparty_exposure

# --- Governed query layer (non-restrictive: ask anything over the schema) ---
from .describe_schema import TOOL_SPEC as SPEC_DESCRIBE_SCHEMA
from .describe_schema import describe_schema
from .query_database import TOOL_SPEC as SPEC_QUERY_DATABASE
from .query_database import query_database

__version__ = TOOL_VERSION


# Registry: tool_name → (callable, json-schema spec)
REGISTRY: dict[str, tuple[Callable, dict]] = {
    # --- Original tools ---
    SPEC_LIVE_QUOTE["name"]:             (get_live_quote,               SPEC_LIVE_QUOTE),
    SPEC_PRICE_HISTORY["name"]:          (get_price_history,            SPEC_PRICE_HISTORY),
    SPEC_QUOTE["name"]:                  (get_quote,                    SPEC_QUOTE),
    SPEC_FUNDAMENTALS["name"]:           (get_fundamentals,             SPEC_FUNDAMENTALS),
    SPEC_FUNDAMENTALS_HISTORY["name"]:   (get_fundamentals_history,     SPEC_FUNDAMENTALS_HISTORY),
    SPEC_TECHNICALS["name"]:             (get_technicals,               SPEC_TECHNICALS),
    SPEC_CORP_ACTIONS["name"]:           (get_corporate_actions,        SPEC_CORP_ACTIONS),
    SPEC_VALUATION["name"]:              (get_valuation,                SPEC_VALUATION),
    SPEC_STAGE1["name"]:                 (stage1_screen,                SPEC_STAGE1),
    SPEC_STAGE2["name"]:                 (stage2_bank_screen,           SPEC_STAGE2),
    SPEC_PEER_RANKINGS["name"]:          (get_peer_rankings,            SPEC_PEER_RANKINGS),
    SPEC_NEWS["name"]:                   (get_news,                     SPEC_NEWS),
    SPEC_LIST_SCRIPS["name"]:            (list_scrips,                  SPEC_LIST_SCRIPS),
    # --- Phase I + J (Gold analytics) ---
    SPEC_SCORECARD["name"]:              (get_scorecard,                SPEC_SCORECARD),
    SPEC_QUADRANT["name"]:               (get_quadrant,                 SPEC_QUADRANT),
    SPEC_DUPONT["name"]:                 (get_dupont,                   SPEC_DUPONT),
    SPEC_PIOTROSKI["name"]:              (get_piotroski,                SPEC_PIOTROSKI),
    SPEC_VALUATION_HISTORY["name"]:      (get_valuation_history,        SPEC_VALUATION_HISTORY),
    SPEC_RETURNS["name"]:                (get_returns,                  SPEC_RETURNS),
    SPEC_ASSET_QUALITY["name"]:          (get_asset_quality,            SPEC_ASSET_QUALITY),
    SPEC_CAPITAL["name"]:                (get_capital,                  SPEC_CAPITAL),
    SPEC_DIVIDEND_HISTORY["name"]:       (get_dividend_history,         SPEC_DIVIDEND_HISTORY),
    SPEC_TECH_POSTURE["name"]:           (get_technical_posture,        SPEC_TECH_POSTURE),
    # --- Floor-sheet broker-flow (microstructure) ---
    SPEC_BROKER_CONCENTRATION["name"]:   (get_broker_concentration,     SPEC_BROKER_CONCENTRATION),
    SPEC_BROKER_ACCUMULATION["name"]:    (get_broker_accumulation,      SPEC_BROKER_ACCUMULATION),
    SPEC_SPECULATION_SCORE["name"]:      (get_speculation_score,        SPEC_SPECULATION_SCORE),
    SPEC_SCRIP_SENTIMENT["name"]:        (get_scrip_sentiment,          SPEC_SCRIP_SENTIMENT),
    # --- Internal-trade surveillance ---
    SPEC_INTERNAL_SURVEILLANCE["name"]:  (get_internal_surveillance,    SPEC_INTERNAL_SURVEILLANCE),
    SPEC_COUNTERPARTY_EXPOSURE["name"]:  (get_counterparty_exposure,    SPEC_COUNTERPARTY_EXPOSURE),
    # --- Governed query layer ---
    SPEC_DESCRIBE_SCHEMA["name"]:        (describe_schema,              SPEC_DESCRIBE_SCHEMA),
    SPEC_QUERY_DATABASE["name"]:         (query_database,               SPEC_QUERY_DATABASE),
}


def tool_specs() -> list[dict]:
    """Return all tool JSON schemas — ready for LLM function-calling payload."""
    return [spec for _, spec in REGISTRY.values()]


__all__ = [
    "ToolError",
    "REGISTRY",
    "tool_specs",
    # Original
    "get_quote",
    "get_live_quote",
    "get_fundamentals",
    "get_fundamentals_history",
    "get_technicals",
    "get_corporate_actions",
    "get_valuation",
    "stage1_screen",
    "stage2_bank_screen",
    "get_peer_rankings",
    "get_news",
    "list_scrips",
    "get_price_history",
    # Phase I + J
    "get_scorecard",
    "get_quadrant",
    "get_dupont",
    "get_piotroski",
    "get_valuation_history",
    "get_returns",
    "get_asset_quality",
    "get_capital",
    "get_dividend_history",
    "get_technical_posture",
    # Floor-sheet broker-flow
    "get_broker_concentration",
    "get_broker_accumulation",
    "get_speculation_score",
    "get_scrip_sentiment",
    # Internal-trade surveillance
    "get_internal_surveillance",
    "get_counterparty_exposure",
    # Governed query layer
    "describe_schema",
    "query_database",
]
