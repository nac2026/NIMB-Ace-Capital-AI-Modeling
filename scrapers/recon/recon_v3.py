"""Pass 3: capture POST bodies, open Financials dropdown → click Quarterly Reports,
dump macro page HTML tables."""
from __future__ import annotations
import asyncio, json, re
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "screenshots"
DOMDUMP = ROOT / "dom_dumps"
APILOG = ROOT / "api_log"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )

        # --- PASS A: NABIL page, capture POST bodies + Quarterly Reports ---
        page = await ctx.new_page()
        call_log = []

        async def on_request(req):
            if req.method == "POST" and "sharesansar.com" in req.url:
                try:
                    call_log.append({
                        "phase": "request",
                        "method": req.method,
                        "url": req.url,
                        "headers": dict(req.headers),
                        "post_data": req.post_data,
                    })
                except Exception:
                    pass

        async def on_response(resp):
            try:
                if "sharesansar.com" in resp.url and resp.request.method == "POST":
                    ct = (resp.headers or {}).get("content-type", "")
                    if "json" in ct:
                        body = None
                        try:
                            body = (await resp.text())[:1200]
                        except Exception:
                            pass
                        call_log.append({
                            "phase": "response",
                            "url": resp.url,
                            "status": resp.status,
                            "content_type": ct[:80],
                            "body_preview": body,
                        })
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        print("[A] NABIL company page with tab clicks")
        await page.goto("https://www.sharesansar.com/company/NABIL",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)
        await page.evaluate("window.scrollTo(0,600)")
        await page.wait_for_timeout(800)

        # Tabs: open Financials dropdown first, then Quarterly Reports
        # Click each tab in turn; for nested ones use evaluate to trigger the Bootstrap tab
        tab_sequence = [
            ("#cpricehistory",      "price history"),
            ("#cdividend",          "dividend/bonus"),
            ("#crightshare",        "rights"),
            ("#cagm",               "agm"),
            ("#cfinanrep",          "financial reports"),
            ("#cqtrreport",         "quarterly reports"),
            ("#cnews",              "news"),
            ("#cannouncements",     "announcements"),
            ("#cfloorsheet",        "floorsheet"),
            ("#cauction",           "auction"),
            ("#ccanalysis",         "company analysis"),
            ("#ctanalysis",         "technical analysis"),
        ]

        for anchor, label in tab_sequence:
            before = len(call_log)
            # Activate Bootstrap tab by jQuery (works for nested dropdown tabs too)
            try:
                await page.evaluate(f"jQuery('a[href=\"{anchor}\"]').tab('show')")
                await page.wait_for_timeout(2200)
                new_calls = [c for c in call_log[before:] if c.get("phase") == "request"]
                print(f"  tab {anchor:22} ({label:20}) → new_post_requests={len(new_calls)}")
                for c in new_calls:
                    print(f"    POST {c['url']}  body={str(c.get('post_data'))[:120]}")
            except Exception as e:
                print(f"  tab {anchor} failed: {str(e)[:100]}")

        # Save screenshot showing whatever is open now
        await page.screenshot(path=str(SHOTS / "NABIL_all_tabs_v3.png"), full_page=True)
        (APILOG / "NABIL_all_tabs_v3.json").write_text(
            json.dumps(call_log, indent=2, ensure_ascii=False), encoding="utf-8")
        await page.close()

        # --- PASS B: macro pages (server-rendered) — dump tables from HTML ---
        for url, tag in [
            ("https://www.sharesansar.com/inflation", "macro_inflation"),
            ("https://www.sharesansar.com/remittance", "macro_remittance"),
            ("https://www.sharesansar.com/short-term-interest-rates", "macro_rates"),
            ("https://www.sharesansar.com/bfis-deposit-lending", "macro_bfi_deposits"),
            ("https://www.sharesansar.com/gdp-market-capitalization", "macro_gdp_mcap"),
            ("https://www.sharesansar.com/budget", "macro_budget"),
            ("https://www.sharesansar.com/government-revenue-expenditure", "macro_gov_rev"),
            ("https://www.sharesansar.com/sectorwise-share-price", "sector_prices"),
            ("https://www.sharesansar.com/datewise-indices", "index_datewise"),
        ]:
            page = await ctx.new_page()
            print(f"[B] {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3500)
            except Exception as e:
                print(f"    nav error {e}")
            await page.screenshot(path=str(SHOTS / f"{tag}.png"), full_page=True)
            html = await page.content()
            (DOMDUMP / f"{tag}.html").write_text(html, encoding="utf-8")
            # Extract first 3 data rows from every visible table
            summary = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('table')).slice(0,8).map((tb,i) => {
                    const headers = Array.from(tb.querySelectorAll('thead th, tr:first-child th, tr:first-child td'))
                        .slice(0,20).map(h => h.innerText.trim().replace(/\\s+/g,' ').slice(0,40));
                    const rows = Array.from(tb.querySelectorAll('tbody tr')).slice(0,3).map(r =>
                        Array.from(r.querySelectorAll('td')).slice(0,20).map(c =>
                            c.innerText.trim().replace(/\\s+/g,' ').slice(0,40)));
                    return {i, id: tb.id, rowCount: tb.querySelectorAll('tr').length, headers, rows};
                });
            }""")
            (APILOG / f"{tag}.tables.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"    tables found: {len(summary)}  first_tbl_rows={summary[0]['rowCount'] if summary else 0}")
            await page.close()
            await asyncio.sleep(1.2)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
