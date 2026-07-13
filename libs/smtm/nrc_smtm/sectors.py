"""Normalize SMTM's free-form sector labels onto the canonical `SECTORS` set.

SMTM `company_list` returns ~19 inconsistent sector strings — "HydroPower" vs
"Hydro Power", "Banking" (the 19 commercial banks) vs "Commercial Banks",
"Manu.& Pro." vs "Manufacturing And Processing", etc. Everything downstream
(metric packs, peer groups, dbt sector partitions) keys off the canonical
labels declared in `nrc_contracts.common.SECTORS`, so we map once here at the
ingestion edge."""
from __future__ import annotations

from nrc_contracts import SECTORS

# Raw SMTM label (lowercased, stripped) → canonical SECTORS member.
_SECTOR_MAP: dict[str, str] = {
    "banking": "Commercial Bank",
    "commercial banks": "Commercial Bank",
    "commercial bank": "Commercial Bank",
    "development banks": "Development Bank",
    "development bank": "Development Bank",
    "finance": "Finance",
    "microfinance": "Microfinance",
    "micro finance": "Microfinance",
    "life insurance": "Life Insurance",
    "non life insurance": "Non Life Insurance",
    "non-life insurance": "Non Life Insurance",
    "hydropower": "Hydro Power",
    "hydro power": "Hydro Power",
    "manufacturing and processing": "Manufacturing and Processing",
    "manu.& pro.": "Manufacturing and Processing",
    "manu. & pro.": "Manufacturing and Processing",
    "hotels and tourism": "Hotels",
    "hotels": "Hotels",
    "tourism": "Hotels",
    "trading": "Trading",
    "tradings": "Trading",
    "investment": "Investment",
    "mutual fund": "Mutual Fund",
    "bond": "Corporate Debenture",
    "corporate debenture": "Corporate Debenture",
    "debenture": "Corporate Debenture",
    "preferred stock": "Preferred Stock",
    "promoter share": "Preferred Stock",
    # Reinsurers (HRL, NRIC) are regulated alongside non-life insurers; NEPSE/SMTM
    # group them under non-life. Map any reinsurance label onto Non Life Insurance.
    "reinsurance": "Non Life Insurance",
    "re insurance": "Non Life Insurance",
    "re-insurance": "Non Life Insurance",
    "others": "Others",
}

# Canonical sectors that are NOT common equities — ingested for completeness but
# excluded from the equity research/screening universe.
NON_EQUITY_SECTORS: frozenset[str] = frozenset(
    {"Mutual Fund", "Corporate Debenture", "Preferred Stock"}
)


def normalize_sector(raw: str | None) -> str:
    """Map an SMTM sector label to a canonical `SECTORS` member ("Others" fallback)."""
    if not raw:
        return "Others"
    key = " ".join(raw.strip().lower().split())
    canon = _SECTOR_MAP.get(key)
    if canon:
        return canon
    # Last resort: accept it verbatim if it already matches a canonical label.
    for s in SECTORS:
        if s.lower() == key:
            return s
    return "Others"


def is_equity_sector(canonical_sector: str) -> bool:
    """True for common-equity sectors (excludes bonds, mutual funds, preferred)."""
    return canonical_sector not in NON_EQUITY_SECTORS
