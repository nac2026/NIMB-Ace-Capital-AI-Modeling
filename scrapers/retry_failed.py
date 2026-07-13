"""Retry the 3 banks that errored in the main run."""
import sys, time
sys.path.insert(0, ".")
from sharesansar.client import SharesansarClient
from sharesansar import prices, dividends, fundamentals, news

with SharesansarClient(rate_limit_seconds=1.5, jitter=0.5, snapshot_raw=True) as c:
    print(f"bootstrapped: {len(c.symbol_to_id)} symbols", flush=True)

    # 1. NABIL — just news
    t0 = time.time()
    try:
        n = news.scrape_news_index(c, "NABIL")
        print(f"[NABIL] news={n} ({time.time()-t0:.1f}s)", flush=True)
    except Exception as e:
        print(f"[NABIL] news ERROR: {e}", flush=True)

    # 2. NBB + NBL — full core
    for sym in ("NBB", "NBL"):
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
