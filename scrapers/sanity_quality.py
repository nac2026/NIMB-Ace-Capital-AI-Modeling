"""Deeper data-quality checks: value sanity, continuity, corroboration."""
import csv
from collections import Counter
from datetime import datetime, timedelta, date
from pathlib import Path

OUT = Path("output")
BANKS = ["ADBL","BOKL","CCBL","CZBIL","CBL","EBL","GBIME","HBL","JBNL","KBL","LBL",
         "MBL","MEGA","NABIL","NBB","NBL","NCCB","NIB","SBI","NICA","NMB","PRVU",
         "PCBL","SANIMA","SBL","SCB","SRBL"]


def fnum(s):
    try: return float(str(s).replace(",",""))
    except Exception: return None


def check_price_quality():
    print("=== Price-quality scan ===")
    bad = []
    for sym in BANKS:
        rows = list(csv.DictReader(open(OUT/"prices"/f"{sym}.csv")))
        issues = []
        closes = [fnum(r.get("close")) for r in rows]
        closes = [c for c in closes if c is not None]
        if not closes:
            issues.append("no closes")
        else:
            if min(closes) <= 0:       issues.append(f"non-positive close: {min(closes)}")
            if max(closes) > 100000:   issues.append(f"absurd close: {max(closes)}")
        # date continuity: max gap in trading days (not calendar)
        dates = sorted({r["date"] for r in rows if r.get("date")})
        # Compute longest calendar gap
        if len(dates) > 2:
            gaps = []
            for i in range(1, len(dates)):
                d1 = datetime.strptime(dates[i-1], "%Y-%m-%d").date()
                d2 = datetime.strptime(dates[i], "%Y-%m-%d").date()
                gaps.append((d2 - d1).days)
            biggest = max(gaps)
            if biggest > 90:
                issues.append(f"gap of {biggest}d")
        # Stale? latest date vs today
        latest = datetime.strptime(dates[-1], "%Y-%m-%d").date() if dates else None
        today = date.today()
        if latest and (today - latest).days > 14:
            issues.append(f"stale: latest {latest} ({(today-latest).days}d ago)")

        if issues:
            bad.append((sym, issues))
    if not bad:
        print("  all 27 banks: closes in valid range, no gaps >90d, latest within 14d → OK")
    else:
        for sym, iss in bad:
            print(f"  {sym}: {iss}")
    print()


def cross_check_prices_vs_scrip_master():
    print("=== Cross-check: prices vs scrip master ===")
    master = {r["scrip"]: r for r in csv.DictReader(open(OUT/"company_info"/"scrip_master.csv"))}
    probs = []
    for sym in BANKS:
        rows = list(csv.DictReader(open(OUT/"prices"/f"{sym}.csv")))
        latest = rows[0] if rows else None
        if not latest: continue
        close_from_prices = fnum(latest.get("close"))
        close_from_master = fnum(master.get(sym, {}).get("latest_close"))
        # They may legitimately differ if master caught a different date;
        # only flag if master close is missing.
        if close_from_master is None:
            probs.append(f"{sym}: master latest_close blank")
    if not probs:
        print(f"  latest_close populated for all 27 banks in master ✓")
    else:
        for p in probs: print(f"  {p}")
    print()


def cross_check_dividends_vs_announcement():
    print("=== Cross-check: dividend announcement_date looks sane ===")
    today = date.today()
    bad = []
    for sym in BANKS:
        rows = list(csv.DictReader(open(OUT/"dividends"/f"{sym}_dividends.csv")))
        for r in rows:
            d = r.get("announcement_date","").strip()
            if not d: continue
            try:
                dd = datetime.strptime(d, "%Y-%m-%d").date()
                if dd > today: bad.append(f"{sym}: future announcement {d}")
                if dd.year < 2000: bad.append(f"{sym}: very old {d}")
            except Exception:
                bad.append(f"{sym}: unparseable date {d!r}")
    if not bad:
        print(f"  all announcement dates in [2000, today] ✓")
    else:
        for b in bad[:10]: print(f"  {b}")
    print()


def fundamentals_period_coverage():
    print("=== Fundamentals period coverage ===")
    all_periods = Counter()
    for sym in BANKS:
        rows = list(csv.DictReader(open(OUT/"fundamentals"/f"{sym}_fundamentals_long.csv")))
        for r in rows:
            all_periods[r["period"]] += 1
    for p, n in all_periods.most_common():
        print(f"  {p!r}: {n} rows across all banks")
    if len(all_periods) == 1:
        print("  NOTE: only 1 period per bank — Sharesansar free endpoint returns current")
        print("        quarter only. Multi-quarter growth (Stage 1 YoY) requires either")
        print("        SSPro, or parsing the Financial Reports announcement PDFs (deferred).")
    print()


def index_vs_bank_latest_date():
    print("=== Latest trading date: index vs banks (should agree) ===")
    nepse = list(csv.DictReader(open(OUT/"index"/"NEPSE_history.csv")))
    nepse_latest = nepse[0]["published_date"] if nepse else "-"
    sample_latest = {}
    for sym in BANKS[:5]:
        rows = list(csv.DictReader(open(OUT/"prices"/f"{sym}.csv")))
        sample_latest[sym] = rows[0]["date"] if rows else "-"
    print(f"  NEPSE index latest: {nepse_latest}")
    for k, v in sample_latest.items():
        agree = "✓" if v == nepse_latest else "✗"
        print(f"    {k} latest: {v}  {agree}")
    print()


def news_freshness():
    print("=== News freshness per bank (top/bottom 5 by last-30-days count) ===")
    today = date.today()
    counts = []
    for sym in BANKS:
        rows = list(csv.DictReader(open(OUT/"news"/f"{sym}_news_index.csv")))
        recent = sum(1 for r in rows
                     if r.get("published_date") and
                     (today - datetime.strptime(r["published_date"], "%Y-%m-%d").date()).days <= 30)
        counts.append((sym, recent, len(rows)))
    counts.sort(key=lambda x: x[1], reverse=True)
    print("  most news (last 30d):")
    for s, r, t in counts[:5]: print(f"    {s}: {r} (total {t})")
    print("  least news (last 30d):")
    for s, r, t in counts[-5:]: print(f"    {s}: {r} (total {t})")
    print()


if __name__ == "__main__":
    check_price_quality()
    cross_check_prices_vs_scrip_master()
    cross_check_dividends_vs_announcement()
    fundamentals_period_coverage()
    index_vs_bank_latest_date()
    news_freshness()
