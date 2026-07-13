"""Bikram Sambat fiscal year + quarter parsing.

A BS fiscal year runs Shrawan → Ashad (≈ mid-July → mid-July). The year is
identified by its starting BS year:
  * 2081 → Shrawan 2081 to Ashad 2082 (≈ Jul 2024 – Jul 2025 AD)
  * 2082 → Shrawan 2082 to Ashad 2083 (≈ Jul 2025 – Jul 2026 AD)

Sharesansar labels fiscal years as '2081/2082' (the slash separates start and
end BS years of the fiscal year). Our canonical form stores just the start
year as `fiscal_year_bs: int`.

Quarters within a BS fiscal year:
  * Q1 = Shrawan + Bhadra + Ashwin (~mid-Jul to mid-Oct)
  * Q2 = Kartik + Marga + Poush   (~mid-Oct to mid-Jan)
  * Q3 = Magh + Falgun + Chaitra  (~mid-Jan to mid-Apr)
  * Q4 = Baisakh + Jestha + Ashad (~mid-Apr to mid-Jul)"""
from __future__ import annotations
import re

# Quarter is sourced from nrc_contracts but we avoid a cyclic import by
# referencing its string values directly. The two packages are independent.
# Callers map the returned int to Quarter(n) themselves.

_FY_SLASH_RE = re.compile(r"^\s*(\d{4})\s*/\s*(\d{4})\s*$")
_FY_AD_SHORT_RE = re.compile(r"^\s*(\d{4})\s*/\s*(\d{2})\s*$")
_QUARTER_LABEL_RE = re.compile(
    r"^\s*(1st|2nd|3rd|4th)\s+Quarter\s+(\d{4})\s*/\s*(\d{4})\s*$",
    re.IGNORECASE,
)
_QUARTER_MAP = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4}

# Offset from AD start year to BS start year for Nepal fiscal years (Shrawan
# starts mid-July). BS = AD + 57 for fiscal years starting in July.
#   AD 2020/21 (Jul 2020–Jul 2021) ↔ BS 2077/78
#   AD 2023/24 (Jul 2023–Jul 2024) ↔ BS 2080/81
_AD_TO_BS_OFFSET = 57


def parse_fiscal_year(raw: str) -> int:
    """Parse '2081/2082' → 2081. Accepts already-normalized '2081' too.

    Raises ValueError on malformed input. Sharesansar's convention is that the
    two years bracket the fiscal year (start/end), so we always return the
    start year."""
    if raw is None:
        raise ValueError("empty fiscal year")
    raw = raw.strip()
    if not raw:
        raise ValueError("empty fiscal year")
    m = _FY_SLASH_RE.match(raw)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        if end != start + 1:
            raise ValueError(f"fiscal year {raw!r}: end must be start+1")
        return start
    # Bare 4-digit fallback for already-canonical inputs.
    if raw.isdigit() and len(raw) == 4:
        return int(raw)
    raise ValueError(f"cannot parse fiscal year {raw!r}")


def parse_ad_fiscal_year_short(raw: str) -> int:
    """Parse AD short-form fiscal year → BS start year.

    Client CSV dumps use AD short form: '2020/21' means Jul 2020 – Jul 2021
    (Nepal fiscal year). We convert to the BS start year used as our
    canonical `fiscal_year_bs`:

      * '2020/21' → 2077 (BS 2077/78)
      * '2023/24' → 2080 (BS 2080/81)
      * '2025/26' → 2082 (BS 2082/83)

    Raises ValueError on malformed input or AD years that don't straddle a
    single fiscal year (e.g. '2020/22')."""
    if raw is None:
        raise ValueError("empty fiscal year")
    raw = raw.strip()
    if not raw:
        raise ValueError("empty fiscal year")
    m = _FY_AD_SHORT_RE.match(raw)
    if not m:
        raise ValueError(f"cannot parse AD-short fiscal year {raw!r}")
    ad_start = int(m.group(1))
    ad_end_short = int(m.group(2))
    if ad_end_short != (ad_start + 1) % 100:
        raise ValueError(
            f"AD-short fiscal year {raw!r}: end {ad_end_short:02d} must be (start+1) mod 100"
        )
    return ad_start + _AD_TO_BS_OFFSET


def parse_quarter_period(raw: str) -> tuple[int, int]:
    """Parse '2nd Quarter 2082/2083' → (fiscal_year_bs=2082, quarter=2).

    Returns (fiscal_year_bs, quarter_int). Caller maps quarter_int to a
    Quarter enum value. Raises ValueError on malformed input."""
    if not raw:
        raise ValueError("empty period")
    m = _QUARTER_LABEL_RE.match(raw)
    if not m:
        raise ValueError(f"cannot parse quarter period {raw!r}")
    q_label, start, end = m.group(1), int(m.group(2)), int(m.group(3))
    if end != start + 1:
        raise ValueError(f"period {raw!r}: end BS year must be start+1")
    return start, _QUARTER_MAP[q_label.lower()]
