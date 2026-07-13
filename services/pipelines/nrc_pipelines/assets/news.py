"""News-intelligence asset — one newsfeed cycle (fetch → enrich → rollup).

Wraps nrc_newsfeed.run_once so the live news pipeline runs on a Dagster
schedule (every ~30 min) instead of only via the standalone `nrc-newsfeed`
poller. Hits the live RSS sources + Gemini, so it needs network + SMTM/LLM
config. Owns news_articles + scrip_sentiment (not synced from the lakehouse)."""
from dagster import AssetExecutionContext, MetadataValue, Output, asset

from nrc_newsfeed import run_once
from nrc_newsfeed.config import get_newsfeed_settings

_GROUP = "news"


@asset(
    group_name=_GROUP,
    key_prefix=["news"],
    description=(
        "One live news cycle: fetch (Sharesansar + Google News RSS) → tag to "
        "scrips → Gemini sentiment/summary → upsert news_articles → rebuild "
        "scrip_sentiment rollup."
    ),
    metadata={"target": "postgres (news_articles, scrip_sentiment)"},
    compute_kind="python",
)
def news_sentiment(context: AssetExecutionContext) -> Output[int]:
    res = run_once(get_newsfeed_settings())
    context.log.info("newsfeed cycle: %s", res)
    return Output(
        value=res.get("written", 0),
        metadata={
            "fetched": MetadataValue.int(res.get("fetched", 0)),
            "unique": MetadataValue.int(res.get("unique", 0)),
            "enriched": MetadataValue.int(res.get("enriched", 0)),
            "written": MetadataValue.int(res.get("written", 0)),
            "scrips_rolled": MetadataValue.int(res.get("scrips_rolled", 0)),
        },
    )
