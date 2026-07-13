"""Ticker canonicalization — aliases, whitespace/case normalization.

The client dumps, scrapers, and published filings use slightly different
tickers for the same scrip:

  * NICA / NICASIA   — NIC Asia Bank
  * NEPAL SBI / SBI  — Nepal SBI Bank
  * SBI / NEPALSBI   — same, punctuation/space variations

We pick a single canonical form per scrip and resolve every incoming alias
to it at the Bronze-ingest boundary so downstream Silver/Gold never see
duplicates. Canonical is always trimmed + upper-cased.

Keep this alias map small and audited. Adding a new alias means "these two
labels definitely refer to the same listed entity" — do NOT use it to force
different entities together (e.g. two banks that merged but whose separate
historical records you want to preserve)."""
from __future__ import annotations


# Map of alias → canonical. Canonical form should be the NEPSE listing symbol.
# Both sides must be upper-case, whitespace-collapsed.
TICKER_ALIASES: dict[str, str] = {
    "NICA": "NICASIA",
    "NEPAL SBI": "SBI",
    "NEPALSBI": "SBI",
}


def canonical_ticker(raw: str) -> str:
    """Normalize a raw scrip label to its canonical form.

    Steps: strip, upper, collapse internal whitespace, then look up in the
    alias map. If no alias matches, return the normalized input as-is.
    Raises ValueError on empty/whitespace-only input."""
    if not isinstance(raw, str):
        raise ValueError(f"ticker must be a string, got {type(raw).__name__}")
    s = " ".join(raw.strip().upper().split())
    if not s:
        raise ValueError("ticker must not be blank")
    return TICKER_ALIASES.get(s, s)
