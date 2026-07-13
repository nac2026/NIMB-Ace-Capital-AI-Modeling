-- News intelligence: sentiment enrichment on news_articles + per-scrip rollup.
--
-- The live newsfeed pipeline (services/newsfeed) OWNS news_articles going
-- forward — it UPSERTs articles (ON CONFLICT article_id) from RSS sources and
-- enriches them with Gemini (summary + sentiment + event). So news_articles is
-- REMOVED from the sync_postgres truncate-reload list; the stale 8,895 scraped
-- headlines remain only as historical backfill.

ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS summary          TEXT;
ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS sentiment        VARCHAR(12);   -- BULLISH | NEUTRAL | BEARISH
ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS sentiment_score  DOUBLE PRECISION; -- -1.0 .. +1.0
ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS enriched_at      TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_news_sentiment ON news_articles (sentiment);
CREATE INDEX IF NOT EXISTS ix_news_enriched  ON news_articles (enriched_at);

-- ---------------------------------------------------------- scrip_sentiment
-- Recent-weighted sentiment rollup per scrip — read by the dashboard, the
-- company-360 News panel, and injected into chat context. Rebuilt each
-- newsfeed cycle over a trailing window.
CREATE TABLE IF NOT EXISTS scrip_sentiment (
    scrip               VARCHAR(20) PRIMARY KEY,
    sentiment_score     DOUBLE PRECISION,          -- weighted mean of article scores
    sentiment_label     VARCHAR(12),               -- BULLISH | NEUTRAL | BEARISH
    n_articles          INTEGER NOT NULL DEFAULT 0,
    bullish_count       INTEGER NOT NULL DEFAULT 0,
    neutral_count       INTEGER NOT NULL DEFAULT 0,
    bearish_count       INTEGER NOT NULL DEFAULT 0,
    window_days         INTEGER,
    latest_published_at TIMESTAMPTZ,
    top_headlines       JSONB,                      -- [{title,url,sentiment,published_at}] most recent
    computed_at         TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_scrip_sentiment_label ON scrip_sentiment (sentiment_label);
