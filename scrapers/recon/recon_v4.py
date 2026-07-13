"""Pass 4: actual page.click + request body capture + open dropdowns."""
from __future__ import annotations
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
APILOG = ROOT / "api_log"
SHOTS = ROOT / "screenshots"


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

        events = []

        async def on_request(req):
            if "sharesansar.com" in req.url and req.method in ("POST", "GET"):
                url = req.url
                # skip assets
                if any(x in url for x in (".js", ".css", ".png", ".jpg", ".gif", ".woff")):
                    return
                if "google" in url or "facebook" in url or "doubleclick" in url:
                    return
                events.append({
                    "type": "request",
                    "method": req.method,
                    "url": url,
                    "headers": {k: v for k, v in req.headers.items() if k in ("x-requested-with", "content-type", "referer")},
                    "post_data": req.post_data,
                })

        async def on_response(resp):
            if "sharesansar.com" in resp.url:
                url = resp.url
                if any(x in url for x in (".js", ".css", ".png", ".jpg", ".gif", ".woff")):
                    return
                if "google" in url or "facebook" in url or "doubleclick" in url:
                    return
                ct = (resp.headers or {}).get("content-type", "")
                body = None
                if "json" in ct and resp.status == 200:
                    try:
                        body = (await resp.text())[:1200]
                    except Exception:
                        pass
                events.append({
                    "type": "response",
                    "status": resp.status,
                    "url": url,
                    "content_type": ct[:60],
                    "body_preview": body,
                })

        page.on("request", on_request)
        page.on("response", on_response)

        print("→ loading NABIL company page")
        await page.goto("https://www.sharesansar.com/company/NABIL",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        # Top-level tabs (real <a> with href="#xxx")
        clicks = [
            ("a[href='#cpricehistory']", "price_history"),
            ("a[href='#cdividend']",     "dividend"),
            ("a[href='#crightshare']",   "rights"),
            ("a[href='#cagm']",          "agm"),
            ("a[href='#cfinanrep']",     "financial_reports"),
            ("a[href='#cnews']",         "news"),
            ("a[href='#cannouncements']","announcements"),
            ("a[href='#cfloorsheet']",   "floorsheet"),
            ("a[href='#cauction']",      "auction"),
        ]

        for sel, label in clicks:
            marker = f"--MARK:{label}--"
            events.append({"type": "marker", "label": marker})
            try:
                await page.click(sel, timeout=3000)
                await page.wait_for_timeout(2500)
                print(f"  ✓ clicked {label}")
            except Exception as e:
                print(f"  ✗ miss {label}: {str(e)[:80]}")

        # Financials is a dropdown parent; its children #cqtrreport and (sub-items) need the parent opened first.
        # Strategy: hover the parent to open dropdown, then click the child.
        events.append({"type": "marker", "label": "--MARK:qtrreport_attempt--"})
        try:
            # Multiple strategies
            # (a) try direct click first (maybe it works if Bootstrap tab handler is attached)
            await page.click("a[href='#cqtrreport']", timeout=2500, force=True)
            await page.wait_for_timeout(2200)
            print("  ✓ clicked qtrreport (direct force)")
        except Exception as e:
            print(f"  ✗ direct qtrreport miss: {str(e)[:80]}")
            # (b) open Financials dropdown first
            try:
                await page.click("a[href='#finanace-menu'], a[data-toggle='dropdown']:has-text('Financials')", timeout=2500)
                await page.wait_for_timeout(800)
                await page.click("a[href='#cqtrreport']", timeout=2500)
                await page.wait_for_timeout(2200)
                print("  ✓ clicked qtrreport via dropdown")
            except Exception as e2:
                print(f"  ✗ dropdown strategy also failed: {str(e2)[:80]}")

        # Also try company-analysis and technical-analysis (nested under Analysis)
        for label, sel_parent, sel_child in [
            ("company_analysis", "a[href='#analysis-menu']", "a[href='#ccanalysis']"),
            ("technical_analysis", "a[href='#analysis-menu']", "a[href='#ctanalysis']"),
        ]:
            events.append({"type": "marker", "label": f"--MARK:{label}--"})
            try:
                await page.click(sel_child, timeout=2500, force=True)
                await page.wait_for_timeout(2000)
                print(f"  ✓ {label} via force click")
            except Exception:
                try:
                    await page.click(sel_parent, timeout=2500)
                    await page.wait_for_timeout(600)
                    await page.click(sel_child, timeout=2500)
                    await page.wait_for_timeout(2000)
                    print(f"  ✓ {label} via dropdown")
                except Exception as e:
                    print(f"  ✗ {label}: {str(e)[:80]}")

        await page.screenshot(path=str(SHOTS / "NABIL_v4.png"), full_page=True)
        (APILOG / "NABIL_v4_events.json").write_text(
            json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")
        await browser.close()
        print(f"total events logged: {len(events)}")


if __name__ == "__main__":
    asyncio.run(main())
