-- Runs once on first Postgres container start (docker-entrypoint-initdb.d).
-- Re-running is prevented by Postgres; drop ./data/postgres to re-init.

-- pgvector: required for query_embedding / news_articles.embedding columns.
CREATE EXTENSION IF NOT EXISTS vector;

-- pg_trgm: useful for fuzzy text search on company names, news titles.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Generic audit helper function — used by migration-managed tables later.
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON EXTENSION vector IS 'pgvector — HNSW vector similarity for embeddings';
