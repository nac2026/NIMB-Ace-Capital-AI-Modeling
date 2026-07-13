"""SMTM live-API Bronze adapters — the live NEPSE feed (tier=LIVE_API).

Unlike the file-based client_csv adapters, these fetch from the SMTM Data API
(libs/smtm) and write canonical Bronze tables. Floor-sheet is the crown jewel:
every trade with buyer/seller broker IDs, the basis for broker-flow and
speculation/manipulation detection."""
from __future__ import annotations

from .company_list import ingest_smtm_company_list
from .eod_prices import ingest_smtm_eod_prices
from .floorsheet import ingest_smtm_floorsheet, write_floorsheet_trades

__all__ = [
    "ingest_smtm_floorsheet", "ingest_smtm_company_list",
    "write_floorsheet_trades", "ingest_smtm_eod_prices",
]
