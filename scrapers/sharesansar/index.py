"""NEPSE + sub-indices. The /index-history-data endpoint is a DataTables GET that
accepts index_id + from/to (YYYY-MM-DD) and returns OHLC+turnover per trading day."""
from __future__ import annotations
import csv
from datetime import date, timedelta
from pathlib import Path
from .client import SharesansarClient

OUT = Path(__file__).resolve().parent.parent / "output" / "index"
OUT.mkdir(parents=True, exist_ok=True)

# Known Sharesansar index IDs — discovered via recon/DevTools.
# 12 is the main NEPSE Index; sub-indices have other ids. We include the main one
# plus banking; if IDs are wrong the server simply returns empty rows.
INDICES = {
    "NEPSE":        12,
    "BANKING":       1,  # Commercial-bank sub-index (discovered via page inspection)
}


def _full_dt_params(index_id: int, date_from: str, date_to: str, start: int, length: int, draw: int) -> dict:
    """Replicate the exact DataTables POST body the browser uses for /index-history-data."""
    cols = ["DT_Row_Index", "current", "change_", "per_change", "per_change",
            "turnover", "published_date"]
    p = {"draw": str(draw)}
    for i, name in enumerate(cols):
        p[f"columns[{i}][data]"] = name
        p[f"columns[{i}][name]"] = ""
        p[f"columns[{i}][searchable]"] = "true" if i > 0 else "false"
        p[f"columns[{i}][orderable]"] = "true" if i > 0 else "false"
        p[f"columns[{i}][search][value]"] = ""
        p[f"columns[{i}][search][regex]"] = "false"
    p["order[0][column]"] = "6"
    p["order[0][dir]"] = "desc"
    p["start"] = str(start)
    p["length"] = str(length)
    p["search[value]"] = ""
    p["search[regex]"] = "false"
    p["index_id"] = str(index_id)
    p["from"] = date_from
    p["to"] = date_to
    return p


def _fetch_history(client: SharesansarClient, index_id: int, date_from: str, date_to: str) -> list[dict]:
    # Seed session (index page sets cookies + CSRF)
    client.get_page("/index-history-data")
    all_rows: list[dict] = []
    start, draw = 0, 0
    length = 50
    while True:
        draw += 1
        params = _full_dt_params(index_id, date_from, date_to, start, length, draw)
        client._wait()
        r = client.c.get("/index-history-data", params=params,
                         headers={"X-Requested-With": "XMLHttpRequest",
                                  "Accept": "application/json",
                                  "Referer": "https://www.sharesansar.com/index-history-data"})
        r.raise_for_status()
        j = r.json()
        rows = j.get("data", []) or []
        all_rows.extend(rows)
        total = j.get("recordsTotal", 0)
        if start + len(rows) >= total or not rows:
            break
        start += len(rows)
    return all_rows


def scrape_history(client: SharesansarClient, lookback_days: int = 730) -> int:
    to_d = date.today()
    from_d = to_d - timedelta(days=lookback_days)
    total = 0
    for name, index_id in INDICES.items():
        rows = _fetch_history(client, index_id, from_d.isoformat(), to_d.isoformat())
        path = OUT / f"{name}_history.csv"
        if rows:
            keys = list(rows[0].keys())
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["index_name"] + keys)
                w.writeheader()
                for r in rows:
                    w.writerow({"index_name": name, **r})
            total += len(rows)
        print(f"  {name} (id={index_id}): {len(rows)} rows")
    return total


# Keep old function names for compatibility
def scrape_current(client: SharesansarClient) -> int:
    return scrape_history(client, lookback_days=7)
