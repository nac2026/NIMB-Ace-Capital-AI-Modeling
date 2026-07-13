"""Unit tests for nrc_nepal.fiscal_year parsers."""
from __future__ import annotations
import pytest

from nrc_nepal import (
    parse_ad_fiscal_year_short,
    parse_fiscal_year,
    parse_quarter_period,
)


def test_parse_fy_slash_form():
    assert parse_fiscal_year("2081/2082") == 2081
    assert parse_fiscal_year("  2081 / 2082 ") == 2081
    assert parse_fiscal_year("2077/2078") == 2077


def test_parse_fy_bare_form():
    assert parse_fiscal_year("2081") == 2081


@pytest.mark.parametrize("bad", ["", "   ", "abcd", "2081/2083", "2081/2081", "20812082", "2081-2082"])
def test_parse_fy_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_fiscal_year(bad)


@pytest.mark.parametrize("label,expected", [
    ("1st Quarter 2082/2083", (2082, 1)),
    ("2nd Quarter 2082/2083", (2082, 2)),
    ("3rd Quarter 2081/2082", (2081, 3)),
    ("4th Quarter 2079/2080", (2079, 4)),
    ("  2nd Quarter  2082 / 2083  ", (2082, 2)),
])
def test_parse_quarter_period(label, expected):
    assert parse_quarter_period(label) == expected


@pytest.mark.parametrize("bad", ["", "Q2 2082/2083", "5th Quarter 2082/2083", "2nd Q 2082/2083", "2nd Quarter 2082/2084"])
def test_parse_quarter_period_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_quarter_period(bad)


@pytest.mark.parametrize("raw,expected_bs", [
    ("2020/21", 2077),      # NABIL Q1 reference period
    ("2023/24", 2080),      # Q4 2023-24 — unit-verified via published filing
    ("2025/26", 2082),      # most recent quarters in client dump
    ("2019/20", 2076),      # one year back
    ("  2020 / 21  ", 2077),
    ("2099/00", 2156),      # century rollover, end=(start+1)%100
])
def test_parse_ad_fiscal_year_short(raw, expected_bs):
    assert parse_ad_fiscal_year_short(raw) == expected_bs


@pytest.mark.parametrize("bad", [
    "", "   ",
    "2020/2021",   # long form, not short
    "2020/23",     # end not start+1
    "2020/20",     # end == start
    "20/21",       # start not 4 digits
    "2020-21",     # wrong separator
    "abcd/ef",
])
def test_parse_ad_fiscal_year_short_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_ad_fiscal_year_short(bad)
