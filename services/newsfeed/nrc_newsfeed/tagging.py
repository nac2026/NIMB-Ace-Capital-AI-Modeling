"""Tag articles to scrips by symbol + distinctive company-name tokens.

Loads the active universe from the Postgres `scrips` table once. Matching is
conservative (word-boundary symbol match + multi-char distinctive name tokens)
to limit false positives. Articles fetched via a per-scrip Google News query
are always tagged to that scrip."""
from __future__ import annotations

import re

from nrc_storage import PostgresClient

from .sources import RawArticle

# Generic words stripped from company names so only distinctive tokens remain.
_STOP = {
    "bank", "limited", "ltd", "company", "co", "nepal", "the", "and",
    "hydropower", "hydro", "power", "energy", "insurance", "life", "non",
    "development", "finance", "microfinance", "laghubitta", "bittiya", "sanstha",
    "investment", "mutual", "fund", "commercial", "manufacturing", "national",
    "general", "industries", "industry", "limited.", "pvt", "private", "public",
    "corporation", "holdings", "international", "nepalese", "first", "everest",
}


class ScripTagger:
    def __init__(self, pg: PostgresClient | None = None):
        pg = pg or PostgresClient()
        rows = pg.fetch_all(
            "SELECT scrip, company_name FROM scrips WHERE is_active"
        )
        self._symbols: set[str] = set()
        self._name_tokens: dict[str, str] = {}   # token → scrip
        self.scrip_name: dict[str, str] = {}     # scrip → company name (for LLM prompts)
        for r in rows:
            scrip = r["scrip"].upper()
            self._symbols.add(scrip)
            name = (r["company_name"] or "")
            self.scrip_name[scrip] = name or scrip
            for tok in re.findall(r"[A-Za-z]+", name.lower()):
                if len(tok) >= 4 and tok not in _STOP:
                    # First scrip to claim a token wins; ambiguous tokens are rare.
                    self._name_tokens.setdefault(tok, scrip)

    def _match(self, text: str) -> set[str]:
        tags: set[str] = set()
        words = set(re.findall(r"[A-Za-z]+", text))
        upper_words = {w for w in words if w.isupper()}
        # Symbol match — only as a standalone all-caps token.
        for sym in self._symbols & upper_words:
            tags.add(sym)
        # Distinctive company-name token match (case-insensitive).
        lower_words = {w.lower() for w in words}
        for tok, scrip in self._name_tokens.items():
            if tok in lower_words:
                tags.add(scrip)
        return tags

    def tag(self, art: RawArticle) -> list[str]:
        """Conservative tags from title + snippet only — the no-LLM fallback.

        The body names every firm mentioned (issue managers, rating agencies, peers)
        and over-tags, so it is excluded here. For high recall (later filtered by the
        LLM), use candidates()."""
        tags: set[str] = set()
        if art.query_scrip:
            tags.add(art.query_scrip.upper())
        tags |= self._match(f"{art.title} {art.snippet}")
        return sorted(tags)

    def candidates(self, art: RawArticle) -> list[str]:
        """Scrip candidates for LLM filtering, from title + snippet (the lead/overview,
        which reliably names the article's SUBJECT company). The full body is excluded
        on purpose: it adds non-subject mentions (issue managers, peers) and, for long
        general-news articles, coincidental token matches that bloat the candidate set
        and confuse the LLM. The LLM (enrich.py) then picks the true subject(s)."""
        tags: set[str] = set()
        if art.query_scrip:
            tags.add(art.query_scrip.upper())
        tags |= self._match(f"{art.title} {art.snippet}")
        return sorted(tags)
