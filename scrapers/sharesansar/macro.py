"""Macro indicators. Each page is an AJAX-driven form: GET /<page>?year=<fy_id> with
X-Requested-With: XMLHttpRequest returns an HTML fragment containing the table."""
from __future__ import annotations
import csv, re
from pathlib import Path
from selectolax.parser import HTMLParser
from .client import SharesansarClient

OUT = Path(__file__).resolve().parent.parent / "output" / "macro"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = {
    "inflation":          "/inflation",
    "remittance":         "/remittance",
    "short_term_rates":   "/short-term-interest-rates",
    "bfi_deposits":       "/bfis-deposit-lending",
}

YEAR_OPTION_RE = re.compile(
    r'<select[^>]+name="year"[^>]*>(.*?)</select>', re.S)
OPTION_RE = re.compile(r'<option value="(\d+)"[^>]*>([^<]+)</option>')


def _get_year_options(client: SharesansarClient, path: str) -> list[tuple[str, str]]:
    html = client.get_page(path)
    m = YEAR_OPTION_RE.search(html)
    if not m:
        return []
    return OPTION_RE.findall(m.group(1))  # [(id, label)]


def _fetch_year(client: SharesansarClient, path: str, year_id: str) -> str:
    client._wait()
    r = client.c.get(path, params={"year": year_id},
                     headers={"X-Requested-With": "XMLHttpRequest",
                              "Referer": f"https://www.sharesansar.com{path}"})
    r.raise_for_status()
    return r.text


def _parse_rows(fragment_html: str) -> tuple[list[str], list[list[str]]]:
    tree = HTMLParser(fragment_html)
    tb = tree.css_first("table")
    if not tb:
        return [], []
    header = [_.text(strip=True) for _ in tb.css("thead th, thead td")]
    rows = []
    for tr in tb.css("tbody tr"):
        rows.append([td.text(strip=True) for td in tr.css("td, th")])
    return header, rows


def scrape_all(client: SharesansarClient, max_years: int | None = 5) -> dict:
    """Pull each macro page across the most recent `max_years` fiscal years (default 5)."""
    out = {}
    for name, path in PAGES.items():
        years = _get_year_options(client, path)[: max_years or 0]
        if not years:
            out[name] = 0
            continue
        all_rows = []
        header: list[str] = []
        for fy_id, fy_label in years:
            fragment = _fetch_year(client, path, fy_id)
            h, rows = _parse_rows(fragment)
            if h and not header:
                header = h
            for row in rows:
                all_rows.append([fy_label] + row)
        csv_path = OUT / f"{name}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["fiscal_year_bs"] + header)
            for r in all_rows:
                w.writerow(r)
        out[name] = len(all_rows)
    return out
