"""Scrip master: parse Company Info tab from /company/<symbol>.

The company page has a static table with id="myTableCInfo" that holds:
Symbol, Name, Sector, Listed Shares, Paid Up Value, Market Capitalization,
Registered Date, Phone Number, Email, Address, Website — plus latest dividend,
right share, auction, pivot-analysis, and moving-average snapshots."""
from __future__ import annotations
import csv, re
from pathlib import Path
from selectolax.parser import HTMLParser
from .client import SharesansarClient

OUT = Path(__file__).resolve().parent.parent / "output" / "company_info"
OUT.mkdir(parents=True, exist_ok=True)

MASTER_FIELDS = [
    "scrip", "company_name", "sector", "sub_sector",
    "listed_shares", "paid_up_value", "paid_up_capital", "market_cap",
    "registered_date", "phone", "email", "address", "website",
    "latest_close", "last_close_date",
    "latest_bonus_pct", "latest_cash_div_pct", "latest_bookclose_date",
    "company_id",
]


def _clean(s: str | None) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def _parse_company_info_table(tree) -> dict:
    """Parse the 2-column Symbol/Value table with id=myTableCInfo."""
    tbl = tree.css_first("table#myTableCInfo")
    if not tbl:
        return {}
    kv = {}
    for tr in tbl.css("tr"):
        cells = tr.css("th, td")
        if len(cells) >= 2:
            key = _clean(cells[0].text())
            val = _clean(cells[1].text())
            kv[key] = val
    return kv


def _parse_latest_dividend(tree) -> tuple[str, str, str]:
    """Top-of-page 'Latest Dividend' box: Bonus Share / Cash Dividend / Book Close Date."""
    bonus = cash = book = ""
    for tbl in tree.css("table.company-table"):
        txt = tbl.text()
        if "Cash Dividend" in txt or "Bonus Share" in txt:
            for tr in tbl.css("tr"):
                cells = [_clean(c.text()) for c in tr.css("th, td")]
                if len(cells) >= 2:
                    k, v = cells[0], cells[1]
                    if "Bonus" in k:
                        bonus = v.rstrip("%").strip()
                    elif "Cash" in k:
                        cash = v.rstrip("%").strip()
                    elif "Book" in k:
                        book = v
            break
    return bonus, cash, book


def _parse_latest_price(tree) -> tuple[str, str]:
    """Top bar shows current close + date. Robust fallback: first price-ish number."""
    # The price banner is in a div with large font — use a regex over cleaned page text
    text = tree.body.text() if tree.body else ""
    m = re.search(r"([\d,]+\.\d{2})\s*%?\s*([+-]?[\d.]+)?\s*%?", text)
    close = m.group(1).replace(",", "") if m else ""
    return close, ""  # date not reliably extractable without ambiguity


def scrape_scrip(client: SharesansarClient, symbol: str) -> dict:
    html = client.get_page(f"/company/{symbol}")
    tree = HTMLParser(html)
    kv = _parse_company_info_table(tree)
    bonus, cash, book = _parse_latest_dividend(tree)
    close, last_date = _parse_latest_price(tree)

    def _strip_num(s: str) -> str:
        """Remove trailing words like 'units', 'Rs.' prefix, and collapse whitespace."""
        if not s: return ""
        s = s.replace("Rs.", "").replace("units", "").strip()
        return _clean(s)

    listed = _strip_num(kv.get("Listed Shares", ""))
    paid_val = _strip_num(kv.get("Paid Up", ""))                  # face value per share
    paid_up_capital = _strip_num(kv.get("Total Paid Up Value", ""))  # total paid-up
    registered = kv.get("Operation Date") or kv.get("Registered Date", "")
    website = kv.get("Website Link") or kv.get("Website", "")

    return {
        "scrip": symbol,
        "company_name": kv.get("Name", ""),
        "sector": kv.get("Sector", ""),
        "sub_sector": kv.get("Sub Sector", ""),
        "listed_shares": listed,
        "paid_up_value": paid_val,
        "paid_up_capital": paid_up_capital,
        "market_cap": "",
        "registered_date": registered,
        "phone": kv.get("Phone Number", ""),
        "email": kv.get("Email", ""),
        "address": kv.get("Address", ""),
        "website": website,
        "latest_close": close,
        "last_close_date": last_date,
        "latest_bonus_pct": bonus,
        "latest_cash_div_pct": cash,
        "latest_bookclose_date": book,
        "company_id": client.symbol_to_id.get(symbol, ""),
    }


def scrape_all(client: SharesansarClient, symbols: list[str]) -> int:
    rows = []
    for s in symbols:
        try:
            rows.append(scrape_scrip(client, s))
            print(f"  info {s}: ok")
        except Exception as e:
            print(f"  info {s}: ERROR {e}")
    path = OUT / "scrip_master.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MASTER_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)
