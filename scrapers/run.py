"""Orchestrator.

Usage:
  .venv/bin/python run.py core        # 27 banks: info+prices+div+rights+fund+news+index (NO macros)
  .venv/bin/python run.py smoke       # 2 banks quick check
  .venv/bin/python run.py prices      # prices only, 27 banks
  .venv/bin/python run.py fundamentals
  .venv/bin/python run.py news
  .venv/bin/python run.py index
  .venv/bin/python run.py macro       # skipped from 'core', run explicitly if needed
"""
from __future__ import annotations
import sys, yaml, time
from pathlib import Path
from sharesansar.client import SharesansarClient
from sharesansar import prices, dividends, fundamentals, news, macro, index, company_info

ROOT = Path(__file__).resolve().parent


def load_banks() -> list[str]:
    return yaml.safe_load(open(ROOT / "config" / "banks.yaml"))["banks"]


def per_scrip_steps(client, symbols, steps):
    for sym in symbols:
        t0 = time.time()
        out = [f"[{sym}]"]
        try:
            if "prices" in steps:
                out.append(f"prices={prices.scrape_scrip(client, sym)}")
            if "dividends" in steps:
                out.append(f"div={dividends.scrape_dividend(client, sym)}")
                out.append(f"rights={dividends.scrape_rights(client, sym)}")
            if "fundamentals" in steps:
                out.append(f"fund={fundamentals.scrape_fundamentals(client, sym)}")
            if "news" in steps:
                out.append(f"news={news.scrape_news_index(client, sym)}")
            out.append(f"({time.time()-t0:.1f}s)")
        except Exception as e:
            out.append(f"ERROR: {e}")
        print(" ".join(out), flush=True)


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "smoke").lower()
    banks = load_banks()

    plan = {
        "smoke":        (["NABIL", "NICA"], {"prices","dividends","fundamentals","news"}, False, True, False),
        "core":         (banks,             {"prices","dividends","fundamentals","news"}, True,  True, False),
        "prices":       (banks,             {"prices"},        False, False, False),
        "dividends":    (banks,             {"dividends"},     False, False, False),
        "fundamentals": (banks,             {"fundamentals"},  False, False, False),
        "news":         (banks,             {"news"},          False, False, False),
        "info":         (banks,             set(),             True,  False, False),
        "index":        ([],                set(),             False, True,  False),
        "macro":        ([],                set(),             False, False, True),
    }
    if cmd not in plan:
        print(f"unknown cmd: {cmd}"); sys.exit(2)

    symbols, steps, include_info, include_index, include_macro = plan[cmd]

    with SharesansarClient(rate_limit_seconds=1.0, jitter=0.4, snapshot_raw=True) as client:
        print(f"bootstrapped: {len(client.symbol_to_id)} symbols in map", flush=True)
        t_start = time.time()

        if include_info:
            n = company_info.scrape_all(client, banks)
            print(f"company_info: {n} rows", flush=True)

        if symbols and steps:
            per_scrip_steps(client, symbols, steps)

        if include_index:
            n = index.scrape_history(client, lookback_days=730)
            print(f"index: {n} rows", flush=True)

        if include_macro:
            res = macro.scrape_all(client, max_years=5)
            print(f"macro: {res}", flush=True)

        print(f"=== done in {(time.time()-t_start)/60:.1f} min ===", flush=True)


if __name__ == "__main__":
    main()
