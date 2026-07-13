"""Per-scrip news (tagged by Sharesansar), plus full article body fetch."""
from __future__ import annotations
import csv, re, time
from pathlib import Path
from .client import SharesansarClient

OUT = Path(__file__).resolve().parent.parent / "output" / "news"
OUT.mkdir(parents=True, exist_ok=True)

INDEX_FIELDS = ["scrip", "published_date", "title", "slug", "url"]
ARTICLE_FIELDS = ["scrip", "published_date", "title", "slug", "url", "body"]

A_TAG = re.compile(r"<a href='([^']+)'>([^<]+)</a>")


def _parse_title(raw: str) -> tuple[str, str]:
    m = A_TAG.search(raw or "")
    if m:
        return m.group(2), m.group(1)
    return (raw or "").strip(), ""


def scrape_news_index(client: SharesansarClient, symbol: str, limit: int | None = None) -> int:
    """Write the index (title/date/slug/url) — cheap, no article body fetch."""
    cid = client.company_id(symbol)
    rows = client.post_datatable("/company-news", cid, referer=f"/company/{symbol}")
    out = []
    for r in rows[: limit or len(rows)]:
        title, url = _parse_title(r.get("title", ""))
        out.append({
            "scrip": symbol,
            "published_date": r.get("published_date"),
            "title": title,
            "slug": r.get("slug"),
            "url": url,
        })
    path = OUT / f"{symbol}_news_index.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        w.writeheader()
        w.writerows(out)
    return len(out)
