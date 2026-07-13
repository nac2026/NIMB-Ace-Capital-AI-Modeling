"""Parse /company-quarterly-report HTML into structured fundamentals rows.

The response is a fragment with 3 tabs: #balance (BALANCE SHEET), #profitloss (P&L),
#keymetrics (KEY METRICS). Each tab contains tables comparing multiple quarters."""
from __future__ import annotations
import csv, json, re
from pathlib import Path
from .client import SharesansarClient
from selectolax.parser import HTMLParser

OUT = Path(__file__).resolve().parent.parent / "output" / "fundamentals"
OUT.mkdir(parents=True, exist_ok=True)


def _clean(s: str | None) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def _to_number(s: str) -> float | str:
    """Try to parse a Nepali-formatted number; return string if not numeric."""
    s = _clean(s).replace(",", "")
    if not s or s in ("-", "N/A", "NA"):
        return ""
    try:
        return float(s.rstrip("%"))
    except ValueError:
        return s


def parse_quarterly_html(html: str, symbol: str) -> dict:
    """Returns {'tabs': {tab_id: {'columns': [...], 'rows': [{label, values}]}}}
    Keeps it general — we preserve structure rather than hardcoding metric lookups."""
    tree = HTMLParser(html)
    tabs: dict = {}
    for div in tree.css("div.tab-pane"):
        tab_id = div.attributes.get("id") or "unknown"
        tab = {"columns": [], "rows": []}
        # Each tab has at least one table
        tables = div.css("table")
        if not tables:
            continue
        for tb in tables:
            # Detect headers
            head_cells = tb.css("thead th, thead td")
            if head_cells:
                cols = [_clean(c.text()) for c in head_cells]
                tab["columns"] = cols
            # Rows
            for tr in tb.css("tbody tr"):
                cells = [_clean(c.text()) for c in tr.css("th, td")]
                if not cells:
                    continue
                tab["rows"].append({
                    "metric": cells[0],
                    "values": cells[1:],
                })
        tabs[tab_id] = tab
    return {"scrip": symbol, "tabs": tabs}


def scrape_fundamentals(client: SharesansarClient, symbol: str, sector: str = "Commercial Bank") -> int:
    cid = client.company_id(symbol)
    html = client.post_quarterly_report(symbol, cid, sector)
    parsed = parse_quarterly_html(html, symbol)

    # Write 1: raw structured JSON (preserves exactly what was parsed)
    (OUT / f"{symbol}_fundamentals.json").write_text(
        json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write 2: long-format CSV — one row per (tab, metric, period)
    long_rows = []
    for tab_id, tab in parsed["tabs"].items():
        cols = tab.get("columns", [])
        periods = cols[1:] if cols else []  # first col is the metric label
        for row in tab["rows"]:
            for i, v in enumerate(row["values"]):
                if i >= len(periods):
                    break
                long_rows.append({
                    "scrip": symbol,
                    "section": tab_id,           # balance / profitloss / keymetrics
                    "metric": row["metric"],
                    "period": periods[i],
                    "value_raw": v,
                    "value_num": _to_number(v) if isinstance(v, str) else "",
                })
    path = OUT / f"{symbol}_fundamentals_long.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["scrip", "section", "metric",
                                           "period", "value_raw", "value_num"])
        w.writeheader()
        w.writerows(long_rows)
    return len(long_rows)
