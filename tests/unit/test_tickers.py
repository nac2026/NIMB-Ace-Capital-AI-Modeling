"""Unit tests for nrc_nepal.tickers — alias resolution and normalization."""
from __future__ import annotations
import pytest

from nrc_nepal import TICKER_ALIASES, canonical_ticker


class TestCanonicalTicker:
    @pytest.mark.parametrize("raw,expected", [
        # No alias — pass-through
        ("NABIL", "NABIL"),
        ("CZBIL", "CZBIL"),
        ("HBL", "HBL"),
        # Case
        ("nabil", "NABIL"),
        ("Nabil", "NABIL"),
        # Trimming
        ("  NABIL  ", "NABIL"),
        ("\tNABIL\n", "NABIL"),
        # Alias resolution — these are the pairs the client dumps use
        # inconsistently
        ("NICA", "NICASIA"),
        ("nica", "NICASIA"),
        ("NEPAL SBI", "SBI"),
        ("nepal sbi", "SBI"),
        ("NEPALSBI", "SBI"),
        # Internal whitespace collapse
        ("NEPAL  SBI", "SBI"),
        ("  nepal   sbi  ", "SBI"),
    ])
    def test_resolves(self, raw, expected):
        assert canonical_ticker(raw) == expected

    @pytest.mark.parametrize("bad", ["", "   ", "\t\n"])
    def test_rejects_blank(self, bad):
        with pytest.raises(ValueError):
            canonical_ticker(bad)

    def test_rejects_non_string(self):
        with pytest.raises(ValueError):
            canonical_ticker(None)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            canonical_ticker(123)  # type: ignore[arg-type]


class TestAliasMapInvariants:
    def test_all_aliases_upper_case(self):
        """Lookups are keyed on upper-case inputs — all keys must already
        be upper-case or the lookup silently misses."""
        for alias in TICKER_ALIASES:
            assert alias == alias.upper(), f"alias {alias!r} is not uppercase"

    def test_all_targets_upper_case(self):
        for target in TICKER_ALIASES.values():
            assert target == target.upper(), f"target {target!r} is not uppercase"

    def test_no_chained_aliases(self):
        """An alias target must not itself be an alias — otherwise lookups
        need to iterate, which they don't."""
        for alias, target in TICKER_ALIASES.items():
            assert target not in TICKER_ALIASES, (
                f"chained alias: {alias}->{target}->{TICKER_ALIASES[target]}"
            )
