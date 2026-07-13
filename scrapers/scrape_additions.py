"""Scrape NIMB and LSL — the two post-merger commercial banks missing from the
original 27-bank list."""
import sys, time
sys.path.insert(0, ".")
from sharesansar.client import SharesansarClient
from sharesansar import prices, dividends, fundamentals, news, company_info

ADDS = ["NIMB", "LSL"]

with SharesansarClient(rate_limit_seconds=1.2, jitter=0.4, snapshot_raw=True) as c:
    print(f"bootstrapped: {len(c.symbol_to_id)} symbols", flush=True)

    # Append to existing scrip_master.csv
    import csv
    master_path = "output/company_info/scrip_master.csv"
    existing = list(csv.DictReader(open(master_path)))
    existing_syms = {r["scrip"] for r in existing}

    new_rows = []
    for sym in ADDS:
        if sym in existing_syms:
            print(f"[{sym}] already in master, skipping master row")
            continue
        row = company_info.scrape_scrip(c, sym)
        new_rows.append(row)
        print(f"[{sym}] master row captured: {row['company_name']}")

    if new_rows:
        with open(master_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=company_info.MASTER_FIELDS)
            w.writerows(new_rows)

    # Now per-scrip data
    for sym in ADDS:
        t0 = time.time()
        out = [f"[{sym}]"]
        try:
            out.append(f"prices={prices.scrape_scrip(c, sym)}")
            out.append(f"div={dividends.scrape_dividend(c, sym)}")
            out.append(f"rights={dividends.scrape_rights(c, sym)}")
            out.append(f"fund={fundamentals.scrape_fundamentals(c, sym)}")
            out.append(f"news={news.scrape_news_index(c, sym)}")
            out.append(f"({time.time()-t0:.1f}s)")
        except Exception as e:
            out.append(f"ERROR: {e}")
        print(" ".join(out), flush=True)
