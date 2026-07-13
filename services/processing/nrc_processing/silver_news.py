"""Silver transform: bronze.news_raw → silver.news_articles.

Conforms to nrc_contracts.NewsArticle. Two things happen here:
  1. Pivot from (scrip, url) long form to one-row-per-url with
     scrip_tags=[...] list. A sector-wide headline tagged to all 19 banks
     collapses from 19 bronze rows into 1 silver row.
  2. Stable article_id derived as SHA1(url)[:16] — matches the contract's
     'article_id = stable hash of url' convention.

body is left NULL at Silver; a separate news_embedder service fetches article
bodies lazily on demand."""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone

import pyarrow as pa
from pydantic import ValidationError

from nrc_compute import DuckDBEngine
from nrc_contracts import EventType, Language, NewsArticle
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import ProcessingReport

_SRC = "bronze.news_raw"
_MASTER = "silver.scrip_master"
_DST = "silver.news_articles"


def _article_id(url: str) -> str:
    """SHA1 hash truncated to 16 hex chars — stable per-URL identifier."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def transform_news(
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
    active_only: bool = True,
) -> ProcessingReport:
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    with DuckDBEngine(settings) as engine:
        engine.register_table("bn", _SRC)
        engine.register_table("sm", _MASTER)
        rows_read = engine.sql("SELECT COUNT(*) AS n FROM bn").to_pylist()[0]["n"]

        active_filter = "JOIN sm ON sm.scrip = bn.scrip AND sm.is_active" if active_only else "LEFT JOIN sm ON sm.scrip = bn.scrip"

        # Pivot to one row per URL with list of scrip_tags. Pick any title/date
        # for the row (they're identical across bronze rows for the same URL).
        pivoted = engine.sql(f"""
            SELECT
                bn.url,
                ARRAY_AGG(DISTINCT bn.scrip ORDER BY bn.scrip)  AS scrip_tags,
                ANY_VALUE(bn.title)                             AS title,
                ANY_VALUE(bn.published_date)                    AS published_date,
                ANY_VALUE(bn.slug)                              AS slug,
                ANY_VALUE(bn.source)                            AS source,
                ANY_VALUE(bn.ingested_at)                       AS ingested_at
            FROM bn
            {active_filter}
            GROUP BY bn.url
        """)

    # Conform to NewsArticle one row at a time.
    warnings: list[str] = []
    valid_rows = []
    for r in pivoted.to_pylist():
        # published_date is a date; contract needs a datetime. Treat as 00:00 UTC.
        pub_dt = datetime.combine(r["published_date"], datetime.min.time(), tzinfo=timezone.utc) if r["published_date"] else None
        row = {
            "article_id": _article_id(r["url"]),
            "url": r["url"],
            "source": r["source"],
            "published_at": pub_dt,
            "title": r["title"],
            "body": None,
            "language": Language.EN,
            "scrip_tags": list(r["scrip_tags"]),
            "sector_tags": [],
            "event_type": EventType.OTHER,
            "ingested_at": r["ingested_at"],
        }
        try:
            NewsArticle.model_validate(row)
            # Coerce enums back to string values for pyarrow serialization.
            row["language"] = row["language"].value
            row["event_type"] = row["event_type"].value
            valid_rows.append(row)
        except ValidationError as e:
            if len(warnings) < 20:
                warnings.append(f"{r['url']}: {e.errors()[0]['msg']}")

    schema = pa.schema([
        ("article_id", pa.string()),
        ("url", pa.string()),
        ("source", pa.string()),
        ("published_at", pa.timestamp("us", tz="UTC")),
        ("title", pa.string()),
        ("body", pa.string()),
        ("language", pa.string()),
        ("scrip_tags", pa.list_(pa.string())),
        ("sector_tags", pa.list_(pa.string())),
        ("event_type", pa.string()),
        ("ingested_at", pa.timestamp("us", tz="UTC")),
    ])
    valid = pa.Table.from_pylist(valid_rows, schema=schema)
    io = DeltaIO(settings)
    io.write(_DST, valid, mode=mode)

    return ProcessingReport(
        table=_DST,
        rows_read=rows_read,
        rows_written=valid.num_rows,
        delta_version=io.version(_DST),
        started_at=started_at,
        warnings=warnings,
    )
