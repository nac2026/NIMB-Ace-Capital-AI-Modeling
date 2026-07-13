"""Persist enriched articles + rebuild the per-scrip sentiment rollup."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from nrc_storage import PostgresClient

from .sources import RawArticle


def upsert_articles(
    pg: PostgresClient,
    articles: list[RawArticle],
    enrichment: dict[str, dict],
) -> int:
    """UPSERT articles into news_articles (ON CONFLICT article_id). Returns count."""
    now = datetime.now(timezone.utc)
    n = 0
    with pg.transaction() as conn, conn.cursor() as cur:
        for a in articles:
            e = enrichment.get(a.article_id, {})
            cur.execute(
                """
                INSERT INTO news_articles
                    (article_id, url, source, published_at, title, body, language,
                     scrip_tags, sector_tags, event_type, ingested_at,
                     summary, sentiment, sentiment_score, enriched_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (article_id) DO UPDATE SET
                    scrip_tags      = EXCLUDED.scrip_tags,
                    event_type      = EXCLUDED.event_type,
                    summary         = EXCLUDED.summary,
                    sentiment       = EXCLUDED.sentiment,
                    sentiment_score = EXCLUDED.sentiment_score,
                    enriched_at     = EXCLUDED.enriched_at,
                    body            = COALESCE(EXCLUDED.body, news_articles.body)
                """,
                (
                    a.article_id, a.url, a.source,
                    a.published_at or now, a.title, (a.body or None), "en",
                    a.scrip_tags, [], e.get("event_type", "other"), now,
                    e.get("summary"), e.get("sentiment"), e.get("sentiment_score"),
                    now if e else None,
                ),
            )
            n += 1
    return n


def rebuild_scrip_sentiment(pg: PostgresClient, *, window_days: int = 30, top_n: int = 5) -> int:
    """Rebuild scrip_sentiment from the trailing window. Returns scrips updated.

    Recency-weighted mean of article sentiment scores per scrip (more recent =
    higher weight), plus bullish/neutral/bearish counts and the most-recent
    headlines for display."""
    rows = pg.fetch_all(
        """
        WITH recent AS (
            SELECT unnest(scrip_tags) AS scrip, sentiment, sentiment_score,
                   published_at, title, url,
                   -- linear recency weight: 1.0 today → ~0.1 at window edge
                   greatest(0.1, 1.0 - extract(epoch FROM (now() - published_at))
                                       / (%s * 86400.0)) AS w
            FROM news_articles
            WHERE enriched_at IS NOT NULL
              AND published_at >= now() - make_interval(days => %s)
              AND array_length(scrip_tags, 1) > 0
        )
        SELECT
            scrip,
            sum(coalesce(sentiment_score,0) * w) / nullif(sum(w),0) AS score,
            count(*)                                               AS n,
            count(*) FILTER (WHERE sentiment='BULLISH')            AS bull,
            count(*) FILTER (WHERE sentiment='NEUTRAL')            AS neu,
            count(*) FILTER (WHERE sentiment='BEARISH')            AS bear,
            max(published_at)                                      AS latest
        FROM recent GROUP BY scrip
        """,
        (window_days, window_days),
    )

    now = datetime.now(timezone.utc)
    updated = 0
    with pg.transaction() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE scrip_sentiment")
        for r in rows:
            score = r["score"] or 0.0
            label = "BULLISH" if score > 0.15 else "BEARISH" if score < -0.15 else "NEUTRAL"
            heads = pg.fetch_all(
                """
                SELECT title, url, sentiment, published_at
                FROM news_articles
                WHERE %s = ANY(scrip_tags) AND enriched_at IS NOT NULL
                ORDER BY published_at DESC LIMIT %s
                """,
                (r["scrip"], top_n),
            )
            top = [{"title": h["title"], "url": h["url"], "sentiment": h["sentiment"],
                    "published_at": h["published_at"].isoformat() if h["published_at"] else None}
                   for h in heads]
            cur.execute(
                """
                INSERT INTO scrip_sentiment
                    (scrip, sentiment_score, sentiment_label, n_articles,
                     bullish_count, neutral_count, bearish_count, window_days,
                     latest_published_at, top_headlines, computed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (r["scrip"], score, label, r["n"], r["bull"], r["neu"], r["bear"],
                 window_days, r["latest"], json.dumps(top), now),
            )
            updated += 1
    return updated
