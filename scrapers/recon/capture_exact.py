"""Capture the FULL POST body and headers from Playwright to replay exactly in httpx."""
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parent.parent / "api_log" / "exact_capture.json"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        page = await ctx.new_page()

        captured = []

        async def on_request(req):
            if req.method == "POST" and "company-price-history" in req.url:
                captured.append({
                    "url": req.url,
                    "method": req.method,
                    "headers": dict(req.headers),
                    "post_data": req.post_data,
                })

        page.on("request", on_request)

        await page.goto("https://www.sharesansar.com/company/NABIL",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)
        await page.click("a[href='#cpricehistory']", timeout=5000)
        await page.wait_for_timeout(3000)

        cookies = await ctx.cookies()

        OUT.write_text(json.dumps({
            "captured": captured,
            "cookies": cookies,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"captured {len(captured)} POST calls")
        if captured:
            print(f"body length: {len(captured[0]['post_data']) if captured[0]['post_data'] else 0}")
            print(f"cookies: {[c['name'] for c in cookies]}")
        await browser.close()


asyncio.run(main())
