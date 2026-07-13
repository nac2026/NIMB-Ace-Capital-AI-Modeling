"""Newsfeed pipeline: fetch → dedup → tag → enrich → store → rollup.

Each cycle pulls Sharesansar RSS + broad Google News queries (+ a rotating
per-scrip Google News sweep), tags to scrips, Gemini-enriches only the
articles not already enriched, UPSERTs, and rebuilds the scrip_sentiment
rollup. Designed to run on a schedule (every ~30 min) or once (--once)."""
from __future__ import annotations

import logging
import time

from nrc_storage import PostgresClient

from .config import DEFAULT_BROAD_QUERIES, NewsfeedSettings, get_newsfeed_settings
from .enrich import enrich_articles
from .sources import (
    RawArticle,
    fetch_body,
    fetch_google_news,
    fetch_merolagani,
    fetch_sharesansar,
    fetch_sharesansar_category,
)
from .store import rebuild_scrip_sentiment, upsert_articles
from .tagging import ScripTagger

_log = logging.getLogger("nrc_newsfeed.pipeline")


def _scrip_sweep(pg: PostgresClient, limit: int) -> list[tuple[str, str]]:
    """Rotate through the universe: the scrips whose news is most stale first."""
    if limit <= 0:
        return []
    rows = pg.fetch_all(
        """
        SELECT s.scrip, s.company_name
        FROM scrips s
        LEFT JOIN scrip_sentiment ss USING (scrip)
        WHERE s.is_active
        ORDER BY ss.computed_at ASC NULLS FIRST
        LIMIT %s
        """,
        (limit,),
    )
    return [(r["scrip"], r["company_name"] or r["scrip"]) for r in rows]


def run_once(settings: NewsfeedSettings | None = None, *, pg: PostgresClient | None = None) -> dict:
    settings = settings or get_newsfeed_settings()
    pg = pg or PostgresClient()
    pg.open()
    try:
        tagger = ScripTagger(pg)

        # 1. Fetch
        collected: list[RawArticle] = []
        collected += fetch_sharesansar(settings.newsfeed_sharesansar_rss)
        if settings.newsfeed_sharesansar_categories_enabled:
            for cat in settings.newsfeed_sharesansar_categories:
                collected += fetch_sharesansar_category(cat, cap=settings.newsfeed_category_cap_per_page)
        if settings.newsfeed_merolagani_enabled:
            collected += fetch_merolagani(
                pages=settings.newsfeed_merolagani_pages,
                page_size=settings.newsfeed_merolagani_page_size,
            )
            # Per-symbol sweep: the symbol= filter pre-associates news to a company
            # (catches matcher misses); query_scrip seeds an LLM candidate the LLM
            # still confirms — not a blind tag.
            for scrip, _name in _scrip_sweep(pg, settings.newsfeed_merolagani_symbol_sweep_per_cycle):
                collected += fetch_merolagani(
                    symbol=scrip,
                    pages=settings.newsfeed_merolagani_symbol_pages,
                    page_size=settings.newsfeed_merolagani_page_size,
                )
        if settings.newsfeed_google_news_enabled:
            for q in DEFAULT_BROAD_QUERIES:
                collected += fetch_google_news(q, cap=settings.newsfeed_max_per_query)
            for scrip, name in _scrip_sweep(pg, settings.newsfeed_scrip_sweep_per_cycle):
                q = f"{name} {scrip} NEPSE"
                collected += fetch_google_news(q, query_scrip=scrip, cap=10)

        # 2. Dedup by article_id (url hash). Bodies are fetched later (step 3a), so at
        # this point variants differ only by their query_scrip hint.
        by_id: dict[str, RawArticle] = {}
        for a in collected:
            cur = by_id.get(a.article_id)
            if cur is None:
                by_id[a.article_id] = a
            elif a.query_scrip:        # keep the scrip-tagged variant's hint
                cur.query_scrip = cur.query_scrip or a.query_scrip
        articles = list(by_id.values())

        # 3. Incremental: only process articles not already fully handled (enriched)
        # in the DB. On the hourly schedule this keeps each cycle to the genuinely
        # new articles — no re-fetching bodies or re-running the LLM on old news.
        done = {
            r["article_id"] for r in pg.fetch_all(
                "SELECT article_id FROM news_articles WHERE article_id = ANY(%s) AND enriched_at IS NOT NULL",
                ([a.article_id for a in articles],),
            )
        } if articles else set()
        todo = [a for a in articles if a.article_id not in done]

        # 3a. Fetch full article bodies for the new ones only (bounds HTTP load).
        # fetch_body dispatches by source (Sharesansar / Merolagani); returns None
        # for sources without a body fetcher (e.g. Google News external links).
        for a in todo:
            if a.body:
                continue
            full = fetch_body(a)
            if full:
                # The list/stub fields win when present (authoritative for Merolagani);
                # the detail fetch only fills gaps — plus the full body.
                a.title = a.title or full.title
                a.body = full.body
                a.snippet = a.snippet or full.snippet
                a.image_url = a.image_url or full.image_url
                a.published_at = a.published_at or full.published_at

        # 4. Classify to company via the LLM: token-matcher proposes high-recall
        # candidates, the LLM picks the subset the article is actually about.
        cand_map = {
            a.article_id: [(s, tagger.scrip_name.get(s, s)) for s in tagger.candidates(a)]
            for a in todo
        }
        enrichment = (
            enrich_articles(todo, candidates=cand_map, batch_size=settings.newsfeed_enrich_batch)
            if todo else {}
        )
        for a in todo:
            e = enrichment.get(a.article_id)
            # Trust the LLM's selection when it actually ran (even if it chose none);
            # fall back to the conservative token tag only if the LLM didn't respond.
            a.scrip_tags = e["scrips"] if e and e.get("classified") else tagger.tag(a)

        # 5. Store only the new/updated articles (old ones keep their enrichment).
        written = upsert_articles(pg, todo, enrichment)

        # 6. Rebuild rollup
        scrips_rolled = rebuild_scrip_sentiment(pg, window_days=settings.newsfeed_lookback_days)

        result = {
            "fetched": len(collected),
            "unique": len(articles),
            "new": len(todo),
            "skipped": len(articles) - len(todo),
            "enriched": len(enrichment),
            "written": written,
            "scrips_rolled": scrips_rolled,
        }
        _log.info("newsfeed cycle: %s", result)
        return result
    finally:
        pg.close()


def run_newsfeed(*, once: bool = False, settings: NewsfeedSettings | None = None) -> None:
    settings = settings or get_newsfeed_settings()
    _log.info("newsfeed started (interval=%.0fs)", settings.newsfeed_interval_s)
    while True:
        t0 = time.time()
        try:
            run_once(settings)
        except Exception:  # noqa: BLE001
            _log.exception("newsfeed cycle failed; will retry")
        if once:
            return
        elapsed = time.time() - t0
        if elapsed < settings.newsfeed_interval_s:
            time.sleep(settings.newsfeed_interval_s - elapsed)
