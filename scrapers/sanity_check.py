"""Data sanity check: verify scraped data is sufficient for the three demo queries.

Demo queries and their data dependencies:
  (Q1) "Which banks pass our Stage 1 screen this quarter?"
        → needs quarterly: net_profit, net_interest_income, ROE per bank
  (Q2) "NABIL Stage 2 metrics + rank on ROE/NPL among banks"
        → needs quarterly: ROE, NPL, CAR, CD ratio per bank
  (Q3) "Is NABIL fairly valued + technicals"
        → needs price history (>= 200 trading days for SMA 200)
        + quarterly EPS and BVPS

Outputs: console report with BLOCKER / WARN / OK per check.
"""
from __future__ import annotations
import csv, json, re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "output"
BANKS = [
    "ADBL","BOKL","CCBL","CZBIL","CBL","EBL","GBIME","HBL","JBNL","KBL","LBL",
    "MBL","MEGA","NABIL","NBB","NBL","NCCB","NIB","SBI","NICA","NMB","PRVU",
    "PCBL","SANIMA","SBL","SCB","SRBL",
]

# Fundamentals metrics we must find (case-insensitive substring match against
# whatever the Key Metrics section labels them).
CRITICAL_METRICS = {
    # label patterns (lowercase substrings) — any one match is enough
    "eps":        ["earnings per share", "earning per share", "eps"],
    "bvps":       ["net worth per share", "book value per share", "bvps"],
    "roe":        ["return on equity", "return on shareholders"],
    "roa":        ["return on asset"],
    "npl":        ["non-performing loan", "non performing loan", "npl"],
    "car":        ["capital fund to rwa", "capital adequacy", "car ratio",
                   "capital adequecy"],   # Nepal banks report CAR as "Capital fund to RWA"
    "cd_ratio":   ["credit to deposit ratio", "credit-to-deposit", "c.d. ratio"],
    "net_profit": ["profit for the period", "net profit", "net income after tax"],
    "nii":        ["net interest income"],
    "op_profit":  ["operating profit"],
    "tot_dep":    ["total deposit", "deposits and borrowings", "deposits from customers"],
    "tot_loan":   ["loan and advances to customers", "loans and advances",
                   "total loans", "net loans"],
    "pe":         ["p/e ratio"],
    "pb":         ["p/b ratio", "price to book"],
}

# Terminal colors (only if attached to tty)
import sys
USE_COLOR = sys.stdout.isatty()
def _c(s, code): return f"\033[{code}m{s}\033[0m" if USE_COLOR else s
OK = lambda s: _c(s, "32")
WARN = lambda s: _c(s, "33")
BAD = lambda s: _c(s, "31")
BOLD = lambda s: _c(s, "1")


def safe_date(s: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try: return datetime.strptime(s.strip(), fmt).date()
        except Exception: pass
    return None


def check_scrip_master() -> dict:
    path = ROOT / "company_info" / "scrip_master.csv"
    if not path.exists():
        return {"status": "BLOCKER", "detail": "missing scrip_master.csv"}
    rows = list(csv.DictReader(open(path)))
    seen = {r["scrip"] for r in rows}
    missing = set(BANKS) - seen
    blanks = defaultdict(int)
    for r in rows:
        for k in ("company_name", "listed_shares", "paid_up_capital", "registered_date"):
            if not (r.get(k) or "").strip():
                blanks[k] += 1
    return {
        "status": "BLOCKER" if missing else ("WARN" if blanks else "OK"),
        "rows": len(rows),
        "missing_banks": sorted(missing),
        "blank_field_counts": dict(blanks),
    }


def check_prices() -> dict:
    summary = {}
    missing = []
    short = []  # banks with fewer than 200 trading days (can't compute SMA_200)
    date_spans = {}
    for sym in BANKS:
        p = ROOT / "prices" / f"{sym}.csv"
        if not p.exists():
            missing.append(sym)
            continue
        rows = list(csv.DictReader(open(p)))
        dates = [safe_date(r["date"]) for r in rows if r.get("date")]
        dates = [d for d in dates if d]
        if len(dates) < 200:
            short.append((sym, len(dates)))
        date_spans[sym] = (min(dates).isoformat() if dates else "-",
                            max(dates).isoformat() if dates else "-",
                            len(dates))
    summary["missing"] = missing
    summary["too_short_for_SMA200"] = short
    summary["date_spans"] = date_spans
    status = "BLOCKER" if missing else ("WARN" if short else "OK")
    summary["status"] = status
    return summary


def check_fundamentals() -> dict:
    """For each bank, check Key Metrics section contains the 6 critical ratios."""
    per_bank: dict[str, dict] = {}
    for sym in BANKS:
        p = ROOT / "fundamentals" / f"{sym}_fundamentals_long.csv"
        if not p.exists():
            per_bank[sym] = {"status": "MISSING"}
            continue
        rows = list(csv.DictReader(open(p)))
        # Look across ALL sections (balance / profitloss / keymetrics)
        metric_labels = {(r["metric"] or "").lower() for r in rows}
        periods = sorted({r["period"] for r in rows if r.get("period")})

        found = {}
        for key, patterns in CRITICAL_METRICS.items():
            match = next((m for m in metric_labels
                          if any(p in m for p in patterns)), None)
            found[key] = bool(match)
        per_bank[sym] = {
            "total_rows": len(rows),
            "periods": periods[-4:],     # last 4 periods we have
            "critical_found": found,
            "missing_critical": [k for k, v in found.items() if not v],
        }
    # Aggregate
    all_missing_critical = defaultdict(list)  # metric → banks missing it
    for sym, info in per_bank.items():
        for k in info.get("missing_critical", []):
            all_missing_critical[k].append(sym)
    status = "OK"
    if any(info.get("status") == "MISSING" for info in per_bank.values()):
        status = "BLOCKER"
    elif all_missing_critical:
        status = "WARN"
    return {"status": status, "per_bank": per_bank,
            "metric_to_missing_banks": dict(all_missing_critical)}


def check_dividends() -> dict:
    n_dividend = n_rights = 0
    missing = []
    for sym in BANKS:
        pd = ROOT / "dividends" / f"{sym}_dividends.csv"
        pr = ROOT / "dividends" / f"{sym}_rights.csv"
        if not pd.exists() or not pr.exists():
            missing.append(sym); continue
        n_dividend += sum(1 for _ in open(pd)) - 1
        n_rights += sum(1 for _ in open(pr)) - 1
    return {"status": "BLOCKER" if missing else "OK",
            "total_dividend_rows": n_dividend,
            "total_rights_rows": n_rights,
            "missing_banks": missing}


def check_news() -> dict:
    today = date.today()
    per_bank = {}
    missing = []
    for sym in BANKS:
        p = ROOT / "news" / f"{sym}_news_index.csv"
        if not p.exists():
            missing.append(sym); continue
        rows = list(csv.DictReader(open(p)))
        dates = [safe_date(r["published_date"]) for r in rows if r.get("published_date")]
        dates = [d for d in dates if d]
        recent_30 = sum(1 for d in dates if (today - d).days <= 30)
        recent_180 = sum(1 for d in dates if (today - d).days <= 180)
        per_bank[sym] = {
            "total": len(rows),
            "latest": max(dates).isoformat() if dates else "-",
            "last_30_days": recent_30,
            "last_180_days": recent_180,
        }
    return {"status": "BLOCKER" if missing else "OK",
            "per_bank": per_bank, "missing": missing}


def check_index() -> dict:
    out = {}
    for name in ("NEPSE", "BANKING"):
        p = ROOT / "index" / f"{name}_history.csv"
        if not p.exists():
            out[name] = {"status": "MISSING"}; continue
        rows = list(csv.DictReader(open(p)))
        dates = [safe_date(r["published_date"]) for r in rows if r.get("published_date")]
        dates = [d for d in dates if d]
        out[name] = {"rows": len(rows),
                     "from": min(dates).isoformat() if dates else "-",
                     "to": max(dates).isoformat() if dates else "-"}
    return {"status": "OK" if all("rows" in v for v in out.values()) else "BLOCKER",
            "indices": out}


def main():
    print(BOLD("\n=== NEPSE Research Copilot — Data Sanity Check ===\n"))

    # 1. Scrip master
    r = check_scrip_master()
    tag = OK("OK") if r["status"] == "OK" else (WARN("WARN") if r["status"] == "WARN" else BAD("BLOCKER"))
    print(f"[{tag}] Scrip master: {r['rows']} rows. "
          f"Missing banks: {r['missing_banks'] or 'none'}. "
          f"Blank fields: {r['blank_field_counts']}")

    # 2. Prices
    r = check_prices()
    tag = OK("OK") if r["status"] == "OK" else (WARN("WARN") if r["status"] == "WARN" else BAD("BLOCKER"))
    print(f"\n[{tag}] Prices:")
    print(f"   missing banks: {r['missing'] or 'none'}")
    if r["too_short_for_SMA200"]:
        print(f"   {WARN('banks with <200 days (cannot compute SMA_200):')} "
              f"{r['too_short_for_SMA200']}")
    # Min/max date across all banks
    all_spans = list(r["date_spans"].values())
    if all_spans:
        min_first = min(s[0] for s in all_spans)
        max_last = max(s[1] for s in all_spans)
        total = sum(s[2] for s in all_spans)
        print(f"   aggregate: {total:,} rows, earliest date {min_first}, latest date {max_last}")

    # 3. Fundamentals
    r = check_fundamentals()
    tag = OK("OK") if r["status"] == "OK" else (WARN("WARN") if r["status"] == "WARN" else BAD("BLOCKER"))
    print(f"\n[{tag}] Fundamentals (Key Metrics section):")
    per_bank = r["per_bank"]
    sample = per_bank.get("NABIL") or next(iter(per_bank.values()))
    print(f"   example (NABIL): total_rows={sample.get('total_rows')}, "
          f"periods={sample.get('periods')}")
    if r["metric_to_missing_banks"]:
        print(f"   {WARN('missing critical metrics per bank:')}")
        for metric, banks in r["metric_to_missing_banks"].items():
            print(f"     {metric}: {len(banks)} banks missing → {banks[:8]}"
                  + (f" ... (+{len(banks)-8} more)" if len(banks) > 8 else ""))
    else:
        print("   all 27 banks have all 9 critical metrics present")

    # 4. Dividends
    r = check_dividends()
    tag = OK("OK") if r["status"] == "OK" else BAD("BLOCKER")
    print(f"\n[{tag}] Dividends: {r['total_dividend_rows']} dividend rows, "
          f"{r['total_rights_rows']} rights rows. Missing banks: {r['missing_banks'] or 'none'}")

    # 5. News
    r = check_news()
    tag = OK("OK") if r["status"] == "OK" else BAD("BLOCKER")
    totals_30 = sum(v["last_30_days"] for v in r["per_bank"].values())
    totals_180 = sum(v["last_180_days"] for v in r["per_bank"].values())
    print(f"\n[{tag}] News: {totals_30} articles in last 30 days, "
          f"{totals_180} in last 180 days, across 27 banks. Missing: {r['missing'] or 'none'}")

    # 6. Index
    r = check_index()
    tag = OK("OK") if r["status"] == "OK" else BAD("BLOCKER")
    print(f"\n[{tag}] Index: {r['indices']}")

    # 7. FINAL VERDICT per demo query
    print(BOLD("\n=== Demo query readiness ==="))
    fund_by_bank = check_fundamentals()["per_bank"]
    price_ok = all((ROOT / "prices" / f"{s}.csv").exists() for s in BANKS)

    q1_fail = [s for s, v in fund_by_bank.items()
               if any(m in v.get("missing_critical", []) for m in ("roe", "net_profit", "nii"))]
    q2_fail = [s for s, v in fund_by_bank.items()
               if any(m in v.get("missing_critical", []) for m in ("roe", "npl", "car", "cd_ratio"))]
    q3_fail = [s for s, v in fund_by_bank.items()
               if any(m in v.get("missing_critical", []) for m in ("eps", "bvps"))] if price_ok else BANKS

    def _v(name, fail):
        if not fail:
            return f"[{OK('READY')}] {name}"
        return f"[{WARN('PARTIAL')}] {name} — blocked for: {fail}"

    print(_v("Q1 (Stage 1 screen: ROE + net profit + NII per bank)", q1_fail))
    print(_v("Q2 (Stage 2 metrics NABIL: ROE + NPL + CAR + CD ratio)", q2_fail))
    print(_v("Q3 (NABIL valuation + technicals: EPS + BVPS + price history)", q3_fail))

    print()


if __name__ == "__main__":
    main()
