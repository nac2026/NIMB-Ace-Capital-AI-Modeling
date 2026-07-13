"""Final data readiness report — active commercial banks only."""
import csv, yaml
from collections import Counter
from datetime import datetime, date
from pathlib import Path

OUT = Path("output")
ACTIVE = yaml.safe_load(open("config/banks_active.yaml"))["banks"]
HIST = yaml.safe_load(open("config/banks_historical.yaml"))["banks"]
today = date.today()


def fnum(s):
    try: return float(str(s).replace(",",""))
    except Exception: return None


def safe_date(s):
    try: return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception: return None


CRITICAL_METRICS = {
    "eps":        ["earnings per share", "earning per share"],
    "bvps":       ["net worth per share", "book value per share"],
    "roe":        ["return on equity"],
    "roa":        ["return on asset"],
    "npl":        ["non-performing loan", "non performing loan"],
    "car":        ["capital fund to rwa", "capital adequacy"],
    "cd_ratio":   ["credit to deposit ratio"],
    "net_profit": ["profit for the period", "net profit"],
    "nii":        ["net interest income"],
    "op_profit":  ["operating profit"],
    "tot_loans":  ["loans and advances to customers", "loan and advances to customers"],
    "pe":         ["p/e ratio"],
    "pb":         ["p/b ratio", "price to book"],
}


def bank_readiness(sym):
    r = {"scrip": sym}
    # prices
    pp = OUT / "prices" / f"{sym}.csv"
    if pp.exists():
        rows = list(csv.DictReader(open(pp)))
        dates = [safe_date(x["date"]) for x in rows if x.get("date")]
        dates = [d for d in dates if d]
        r["price_rows"] = len(dates)
        r["price_latest"] = max(dates).isoformat() if dates else "-"
        r["price_stale_days"] = (today - max(dates)).days if dates else None
        r["enough_for_SMA200"] = len(dates) >= 200
    else:
        r["price_rows"] = 0
        r["enough_for_SMA200"] = False

    # dividends
    dp = OUT / "dividends" / f"{sym}_dividends.csv"
    if dp.exists():
        r["dividend_rows"] = sum(1 for _ in open(dp)) - 1

    # fundamentals
    fp = OUT / "fundamentals" / f"{sym}_fundamentals_long.csv"
    if fp.exists():
        rows = list(csv.DictReader(open(fp)))
        labels = {(x["metric"] or "").lower() for x in rows}
        missing = []
        for key, patterns in CRITICAL_METRICS.items():
            if not any(any(p in m for p in patterns) for m in labels):
                missing.append(key)
        r["fund_missing"] = missing
        r["fund_rows"] = len(rows)

    # news
    np = OUT / "news" / f"{sym}_news_index.csv"
    if np.exists():
        rows = list(csv.DictReader(open(np)))
        dates = [safe_date(x["published_date"]) for x in rows if x.get("published_date")]
        dates = [d for d in dates if d]
        r["news_rows"] = len(rows)
        r["news_latest"] = max(dates).isoformat() if dates else "-"
        r["news_last_30d"] = sum(1 for d in dates if (today - d).days <= 30)

    return r


def main():
    print("\n" + "="*78)
    print("  NEPSE RESEARCH COPILOT — DATA READINESS REPORT")
    print("="*78)

    # ACTIVE banks
    print(f"\n[ACTIVE UNIVERSE] {len(ACTIVE)} commercial banks currently trading")
    print(f"{'SYM':<8} {'Prices':>7} {'Latest':<12} {'Divs':>5} {'Fund':>5} "
          f"{'News':>6} {'N30d':>5}  {'missing_metrics':<40}")
    totals = Counter()
    ok_banks = []
    for sym in ACTIVE:
        r = bank_readiness(sym)
        missing = ",".join(r.get("fund_missing", [])) or "-"
        line = (f"{sym:<8} {r.get('price_rows',0):>7} {r.get('price_latest','-'):<12} "
                f"{r.get('dividend_rows',0):>5} {r.get('fund_rows',0):>5} "
                f"{r.get('news_rows',0):>6} {r.get('news_last_30d',0):>5}  {missing:<40}")
        print(line)
        totals["prices"] += r.get("price_rows", 0)
        totals["dividends"] += r.get("dividend_rows", 0)
        totals["news"] += r.get("news_rows", 0)
        if not r.get("fund_missing") and r.get("enough_for_SMA200"):
            ok_banks.append(sym)

    print()
    print(f"Aggregate: {totals['prices']:,} price rows  |  {totals['dividends']} dividend events  |  "
          f"{totals['news']:,} news articles")
    print(f"Banks with ALL critical metrics + ≥200 price days: {len(ok_banks)}/{len(ACTIVE)}")

    # HISTORICAL banks
    print(f"\n[HISTORICAL UNIVERSE] {len(HIST)} merged/delisted banks (kept for archive)")
    print(f"  {', '.join(HIST)}")

    # Index + Macro
    nepse = list(csv.DictReader(open(OUT/"index"/"NEPSE_history.csv")))
    bank_idx = list(csv.DictReader(open(OUT/"index"/"BANKING_history.csv")))
    print(f"\n[INDEX DATA]")
    print(f"  NEPSE: {len(nepse)} rows, {nepse[-1]['published_date']} → {nepse[0]['published_date']}")
    print(f"  BANKING sub-index: {len(bank_idx)} rows")

    # Readiness per demo query
    print("\n" + "="*78)
    print("  DEMO QUERY READINESS")
    print("="*78)
    q1 = q2 = q3 = True
    q1_missing = q2_missing = q3_missing = []
    for sym in ACTIVE:
        r = bank_readiness(sym)
        missing = r.get("fund_missing", [])
        if any(m in missing for m in ("roe","net_profit","nii")): q1 = False; q1_missing = q1_missing+[sym]
        if any(m in missing for m in ("roe","npl","car","cd_ratio")): q2 = False; q2_missing = q2_missing+[sym]
        if any(m in missing for m in ("eps","bvps")) or not r.get("enough_for_SMA200"):
            q3 = False; q3_missing = q3_missing+[sym]

    def v(ok, label, miss):
        status = "✓ READY" if ok else f"✗ PARTIAL (gap for: {miss})"
        print(f"  {status}  |  {label}")

    v(q1, "Q1: Stage 1 screen across banks (needs ROE, net_profit, NII)", q1_missing)
    v(q2, "Q2: NABIL Stage 2 + peer rank (needs ROE, NPL, CAR, CD ratio)", q2_missing)
    v(q3, "Q3: NABIL valuation + technicals (needs EPS, BVPS, ≥200d price)", q3_missing)

    print("\n" + "="*78)
    print("  KNOWN LIMITATIONS (non-blocking for prototype)")
    print("="*78)
    print("  • Fundamentals: Sharesansar free endpoint returns only CURRENT quarter per bank.")
    print("    → Cross-sectional peer ranking works; quarter-over-quarter GROWTH")
    print("       (Stage 1 growth component) will need historical quarterly report PDFs.")
    print("       Sources: each bank's IR page, or NEPSE financial-reports announcements.")
    print("  • Macros excluded (user decision — can be added later from /inflation, /remittance,")
    print("    /short-term-interest-rates, /bfis-deposit-lending pages; scraper already written).")
    print("  • News is title+URL+date only (no body). Body fetch is a second pass per article")
    print("    when we wire up the news-embedding job.")
    print()


if __name__ == "__main__":
    main()
