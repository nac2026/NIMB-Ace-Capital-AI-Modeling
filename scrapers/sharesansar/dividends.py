"""Corporate actions: bonus + cash dividend per scrip (rights handled separately)."""
from __future__ import annotations
import csv, re
from pathlib import Path
from .client import SharesansarClient

OUT = Path(__file__).resolve().parent.parent / "output" / "dividends"
OUT.mkdir(parents=True, exist_ok=True)

DIV_FIELDS = ["scrip", "fiscal_year_bs", "announcement_date", "bookclose_date",
              "distribution_date", "bonus_share_pct", "cash_dividend_pct",
              "total_dividend_pct", "status"]
RIGHT_FIELDS = ["scrip", "fiscal_year_bs", "announcement_date", "opening_date",
                "closing_date", "ratio", "issue_price", "total_units"]


def _clean_bookclose(s: str | None) -> str | None:
    if not s:
        return None
    return re.sub(r"\s*\[.*\]\s*$", "", s).strip() or None


def scrape_dividend(client: SharesansarClient, symbol: str) -> int:
    cid = client.company_id(symbol)
    rows = client.post_datatable("/company-dividend", cid, referer=f"/company/{symbol}")
    out = [{
        "scrip": symbol,
        "fiscal_year_bs": r.get("year"),
        "announcement_date": r.get("announcement_date"),
        "bookclose_date": _clean_bookclose(r.get("bookclose_date")),
        "distribution_date": r.get("distribution_date") or None,
        "bonus_share_pct": r.get("bonus_share") or None,
        "cash_dividend_pct": r.get("cash_dividend") or None,
        "total_dividend_pct": r.get("total_dividend") or None,
        "status": r.get("status"),
    } for r in rows]
    path = OUT / f"{symbol}_dividends.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DIV_FIELDS)
        w.writeheader()
        w.writerows(out)
    return len(out)


def scrape_rights(client: SharesansarClient, symbol: str) -> int:
    cid = client.company_id(symbol)
    rows = client.post_datatable("/company-rightshare", cid, referer=f"/company/{symbol}")
    out = [{
        "scrip": symbol,
        "fiscal_year_bs": r.get("year") or r.get("fiscal_year"),
        "announcement_date": r.get("announcement_date") or r.get("proposed_date"),
        "opening_date": r.get("opening_date"),
        "closing_date": r.get("closing_date"),
        "ratio": r.get("ratio_value") or r.get("ratio"),
        "issue_price": r.get("issue_price"),
        "total_units": r.get("total_units"),
    } for r in rows]
    path = OUT / f"{symbol}_rights.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RIGHT_FIELDS)
        w.writeheader()
        w.writerows(out)
    return len(out)
