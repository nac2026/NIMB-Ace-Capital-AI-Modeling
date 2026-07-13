"""Scrape full EOD OHLCV history per scrip from /company-price-history."""
from __future__ import annotations
import csv
from pathlib import Path
from .client import SharesansarClient

OUT = Path(__file__).resolve().parent.parent / "output" / "prices"
OUT.mkdir(parents=True, exist_ok=True)

FIELDS = ["scrip", "date", "open", "high", "low", "close", "per_change",
          "traded_quantity", "traded_amount", "status"]


def scrape_scrip(client: SharesansarClient, symbol: str) -> int:
    cid = client.company_id(symbol)
    rows = client.post_datatable("/company-price-history", cid,
                                  referer=f"/company/{symbol}")
    out_rows = [{
        "scrip": symbol,
        "date": r.get("published_date"),
        "open": r.get("open"),
        "high": r.get("high"),
        "low": r.get("low"),
        "close": r.get("close"),
        "per_change": r.get("per_change"),
        "traded_quantity": r.get("traded_quantity"),
        "traded_amount": r.get("traded_amount"),
        "status": r.get("status"),
    } for r in rows]
    path = OUT / f"{symbol}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out_rows)
    return len(out_rows)
