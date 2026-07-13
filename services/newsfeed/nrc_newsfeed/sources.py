"""RSS news sources — Sharesansar (primary, English) + Google News (breadth).

Also two HTML/JSON crawlers: a Sharesansar *category-page* crawler (`/category/<slug>`)
+ full body fetcher (`/newsdetail/...`), and a Merolagani JSON news-list API crawler
(`webrequesthandler.ashx?type=get_news`) + body fetcher (`NewsDetail.aspx`). All
sources normalize to RawArticle. article_id = sha1(url)[:16] so re-fetches dedup
cleanly. Verified live 2026-05-29 (see memory: nepse-news-sources)."""
from __future__ import annotations

import hashlib
import html
import json
import random
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"}
_TAG_RE = re.compile(r"<[^>]+>")

_SS_BASE = "https://www.sharesansar.com"


@dataclass
class RawArticle:
    title: str
    url: str
    source: str
    published_at: datetime | None
    snippet: str = ""
    body: str = ""                          # full article text (category crawler only)
    image_url: str = ""
    query_scrip: str | None = None          # set when fetched via a per-scrip query
    scrip_tags: list[str] = field(default_factory=list)

    @property
    def article_id(self) -> str:
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:16]


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _TAG_RE.sub("", text).replace("&nbsp;", " ").strip()


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    # RFC-822 (RSS pubDate) e.g. "Fri, 29 May 2026 12:08:24 +0000"
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        pass
    # ISO-ish e.g. "2026-05-29T17:53:00+05:45"
    try:
        return datetime.fromisoformat(raw).astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_rss(xml_text: str, source: str, query_scrip: str | None = None) -> list[RawArticle]:
    out: list[RawArticle] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for it in root.findall(".//item"):
        url = (it.findtext("link") or "").strip()
        title = _clean(it.findtext("title"))
        if not url or not title:
            continue
        out.append(RawArticle(
            title=title,
            url=url,
            source=source,
            published_at=_parse_date(it.findtext("pubDate")),
            snippet=_clean(it.findtext("description"))[:500],
            query_scrip=query_scrip,
        ))
    return out


def _get(url: str, timeout: float = 20.0) -> str | None:
    try:
        r = httpx.get(url, headers=_UA, timeout=timeout, follow_redirects=True)
        if r.status_code == 200:
            return r.text
    except httpx.HTTPError:
        return None
    return None


def fetch_sharesansar(rss_url: str = "https://www.sharesansar.com/rss") -> list[RawArticle]:
    """Sharesansar latest news RSS — English, NEPSE-focused, minute-fresh."""
    body = _get(rss_url)
    return _parse_rss(body, "sharesansar") if body else []


def _google_news_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-NP&gl=NP&ceid=NP:en"


def fetch_google_news(query: str, *, query_scrip: str | None = None, cap: int = 25) -> list[RawArticle]:
    """Google News RSS for a query — aggregates all outlets, no API key."""
    body = _get(_google_news_url(query))
    if not body:
        return []
    items = _parse_rss(body, "google_news", query_scrip=query_scrip)
    return items[:cap]


# --------------------------------------------------------------------------- #
# Sharesansar category-page crawler + article-body fetcher
# --------------------------------------------------------------------------- #
# Detail URLs end in a `-YYYY-MM-DD` slug tail (used as a fallback publish date).
_DETAIL_RE = re.compile(r"https://www\.sharesansar\.com/newsdetail/[^\"'\s<>]+")
_SLUG_DATE_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})$")
# Body lives in a stable `#newsdetail-content` div. The real publish timestamp is in
# the header line above the body (e.g. "Thu, Jun 11, 2026 10:17 AM on …") — the
# article:published_time meta is unreliable (observed a 2016 date), so we don't use it.
_BODY_RE = re.compile(r'<div[^>]*id=["\']newsdetail-content["\'][^>]*>(.*?)</div>', re.S | re.I)
_HEADER_DATE_RE = re.compile(
    r"([A-Z][a-z]{2},\s*[A-Z][a-z]{2}\s+\d{1,2},\s*\d{4}\s+\d{1,2}:\d{2}\s*[AP]M)"
)

# Polite throttle shared across Sharesansar detail/category GETs (we do many).
_last_ss_req_t = 0.0


def _ss_throttle(rate: float = 1.5, jitter: float = 1.0) -> None:
    global _last_ss_req_t
    elapsed = time.time() - _last_ss_req_t
    target = rate + random.uniform(0, jitter)
    if elapsed < target:
        time.sleep(target - elapsed)
    _last_ss_req_t = time.time()


def _meta(src: str, prop: str) -> str:
    """Extract an Open Graph / meta tag content value (content can precede or follow the
    key). The capture is bounded to a single tag ([^"'] / [^>], no DOTALL) so an empty
    meta like `<meta property="og:title">` returns '' instead of spilling into later tags."""
    p = re.escape(prop)
    m = re.search(
        r'<meta\b[^>]*?(?:property|name)=["\']' + p + r'["\'][^>]*?\bcontent=["\']([^"\']*)["\']',
        src, re.I,
    ) or re.search(
        r'<meta\b[^>]*?\bcontent=["\']([^"\']*)["\'][^>]*?(?:property|name)=["\']' + p + r'["\']',
        src, re.I,
    )
    return html.unescape(m.group(1).strip()) if m else ""


def _clean_html(text: str) -> str:
    """Strip script/style + tags, unescape entities, collapse whitespace."""
    if not text:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    return html.unescape(re.sub(r"\s+", " ", _TAG_RE.sub(" ", text))).strip()


def _slug_date(url: str) -> datetime | None:
    m = _SLUG_DATE_RE.search(url)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fetch_sharesansar_category(category: str, *, cap: int = 25) -> list[RawArticle]:
    """List a Sharesansar category page → lightweight RawArticles (url + slug-date).

    Bodies are NOT fetched here (cheap listing pass); call fetch_article() per URL for
    the new ones. `category` is the slug, e.g. 'ipo-fpo-news' or 'dividend-right-bonus'."""
    _ss_throttle()
    src = _get(f"{_SS_BASE}/category/{category}")
    if not src:
        return []
    seen: set[str] = set()
    out: list[RawArticle] = []
    for url in _DETAIL_RE.findall(src):
        if url in seen:
            continue
        seen.add(url)
        # Real category articles end in a `-YYYY-MM-DD` slug; this excludes sidebar /
        # related-widget promo links (e.g. an old "watch-live-video…2019-2nd-day").
        slug_dt = _slug_date(url)
        if slug_dt is None:
            continue
        out.append(RawArticle(
            title="", url=url, source="sharesansar", published_at=slug_dt,
        ))
        if len(out) >= cap:
            break
    return out


def fetch_article(url: str) -> RawArticle | None:
    """Fetch a Sharesansar /newsdetail page → RawArticle with title, body, date, image."""
    _ss_throttle()
    src = _get(url)
    if not src:
        return None
    title = _meta(src, "og:title")
    if not title:
        return None
    bm = _BODY_RE.search(src)
    body = _clean_html(bm.group(1)) if bm else ""
    summary = _meta(src, "og:description").lstrip("| ").removeprefix("ShareSansar").lstrip("| ").strip()
    dm = _HEADER_DATE_RE.search(_clean_html(src))
    published_at = None
    if dm:
        try:
            published_at = datetime.strptime(dm.group(1).strip(), "%a, %b %d, %Y %I:%M %p").replace(tzinfo=timezone.utc)
        except ValueError:
            published_at = None
    return RawArticle(
        title=title,
        url=url,
        source="sharesansar",
        published_at=published_at or _slug_date(url),
        snippet=(summary or body)[:500],
        body=body,
        image_url=_meta(src, "og:image"),
    )


# --------------------------------------------------------------------------- #
# Merolagani — JSON news-list API + NewsDetail.aspx body fetcher
# --------------------------------------------------------------------------- #
# The list handler returns a JSON array of {newsID, newsTitle, newsOverview (HTML
# excerpt), newsDateAD, imagePath}. No cookies/CSRF needed. The full body lives on
# the server-rendered NewsDetail.aspx page (concatenated <p> blocks). newsID is a
# monotonic int, so dedup/incremental works the same as everywhere via article_id.
_MERO_BASE = "https://eng.merolagani.com"
_MERO_NEWS_API = f"{_MERO_BASE}/handlers/webrequesthandler.ashx"
_last_mero_req_t = 0.0


def _mero_throttle(rate: float = 1.0, jitter: float = 0.8) -> None:
    global _last_mero_req_t
    elapsed = time.time() - _last_mero_req_t
    target = rate + random.uniform(0, jitter)
    if elapsed < target:
        time.sleep(target - elapsed)
    _last_mero_req_t = time.time()


def _parse_mero_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    # Displayed times are Nepal-local but carry no tz; treat as UTC to match the
    # Sharesansar fetcher's convention (consistent, not astronomically exact).
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _mero_news_url(news_id: int) -> str:
    return f"{_MERO_BASE}/NewsDetail.aspx?newsID={news_id}"


def _extract_element(src: str, el_id: str) -> str:
    """Return the inner HTML of the element with the given id (depth-matched), or ''."""
    m = re.search(r'<(\w+)[^>]*id=["\']' + re.escape(el_id) + r'["\'][^>]*>', src)
    if not m:
        return ""
    tag, start, depth = m.group(1), m.end(), 1
    for mm in re.finditer(r"<(/?)" + tag + r"[^>]*>", src[start:]):
        depth += -1 if mm.group(1) else 1
        if depth == 0:
            return src[start:start + mm.start()]
    return src[start:start + 8000]   # unbalanced markup fallback


def fetch_merolagani(*, symbol: str = "", pages: int = 3, page_size: int = 8) -> list[RawArticle]:
    """Crawl the Merolagani English news list (JSON API) → lightweight RawArticles.

    When `symbol` is given, the API returns only that company's news and each article's
    query_scrip is set to it — a high-confidence candidate the LLM still confirms (it is
    NOT a blind tag). Bodies are NOT fetched here; call fetch_merolagani_article() per URL."""
    symbol = symbol.upper()
    out: list[RawArticle] = []
    for page in range(1, pages + 1):
        _mero_throttle()
        params = {
            "type": "get_news", "newsID": "0", "newsCategoryID": "0", "symbol": symbol,
            "page": str(page), "pageSize": str(page_size), "popular": "false",
            "includeFeatured": "true", "languageType": "EN",
        }
        try:
            r = httpx.get(_MERO_NEWS_API, params=params,
                          headers={**_UA, "X-Requested-With": "XMLHttpRequest",
                                   "Referer": f"{_MERO_BASE}/NewsList.aspx"},
                          timeout=20.0, follow_redirects=True)
            if r.status_code != 200:
                break
            items = json.loads(r.text)
        except (httpx.HTTPError, json.JSONDecodeError):
            break
        if not items:
            break
        for it in items:
            nid = it.get("newsID")
            title = _clean_html(it.get("newsTitle") or "")
            if not nid or not title:
                continue
            img = (it.get("imagePath") or "").replace("\\", "/")
            out.append(RawArticle(
                title=title,
                url=_mero_news_url(nid),
                source="merolagani",
                published_at=_parse_mero_date(it.get("newsDateAD")),
                snippet=_clean_html(it.get("newsOverview") or "")[:500],
                image_url=f"{_MERO_BASE}/{img}" if img else "",
                query_scrip=symbol or None,
            ))
    return out


def fetch_merolagani_article(url: str) -> RawArticle | None:
    """Fetch a Merolagani NewsDetail.aspx page → RawArticle with title, body, image.

    The full body is server-rendered inside #ctl00_ContentPlaceHolder1_newsDetail. Some
    articles render an EMPTY body there (loaded another way) — for those, body falls back
    to og:description and the caller keeps the list API's newsOverview snippet."""
    _mero_throttle()
    src = _get(url)
    if not src:
        return None
    title = _meta(src, "og:title")
    if not title:
        # Shell/incomplete render — let the caller keep the list-API title + overview.
        return None
    summary = _meta(src, "og:description")
    body = _clean_html(_extract_element(src, "ctl00_ContentPlaceHolder1_newsDetail"))
    return RawArticle(
        title=title,
        url=url,
        source="merolagani",
        published_at=None,   # the list API supplies the date; the page has none reliable
        snippet=(summary or body)[:500],
        body=body or summary,
        image_url=_meta(src, "og:image"),
    )


# --------------------------------------------------------------------------- #
# Body-fetch dispatch — route an article to its source's full-body fetcher.
# --------------------------------------------------------------------------- #
def fetch_body(art: RawArticle) -> RawArticle | None:
    """Fetch the full article body for a stub, dispatching by source. Returns None
    for sources without a body fetcher (e.g. google_news external links)."""
    if art.source == "sharesansar":
        return fetch_article(art.url)
    if art.source == "merolagani":
        return fetch_merolagani_article(art.url)
    return None
