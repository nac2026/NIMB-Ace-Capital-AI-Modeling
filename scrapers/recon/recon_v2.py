"""Pass 2: correct URLs + click tabs on company page to trigger AJAX."""
from __future__ import annotations
import asyncio, json, re
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "screenshots"
DOMDUMP = ROOT / "dom_dumps"
APILOG = ROOT / "api_log"
APILOG.mkdir(parents=True, exist_ok=True)


def slug(url: str, tag: str = "") -> str:
    p = urlparse(url)
    base = re.sub(r"[^a-zA-Z0-9]+", "_", p.path.strip("/") or "root")
    return (base + ("__" + tag if tag else ""))[:120]


async def collect_page(ctx, url, tag, tab_clicks=None, wait_ms=4000):
    page = await ctx.new_page()
    calls = []

    async def on_response(resp):
        try:
            ct = (resp.headers or {}).get("content-type", "") or ""
            # Only log interesting non-asset calls
            host = urlparse(resp.url).netloc
            if host.endswith("sharesansar.com") or host.endswith("merolagani.com") \
                    or "nepalstock" in host or "nrb.org.np" in host:
                if "json" in ct or "ajax" in resp.url.lower() or "api" in resp.url.lower() \
                        or "data" in urlparse(resp.url).path.lower():
                    body = None
                    if "json" in ct and resp.status == 200:
                        try:
                            t = await resp.text()
                            body = t[:800]
                        except Exception:
                            body = None
                    calls.append({
                        "url": resp.url,
                        "status": resp.status,
                        "method": resp.request.method,
                        "content_type": ct[:80],
                        "body_preview": body,
                    })
        except Exception:
            pass

    page.on("response", on_response)

    print(f"[recon] → {url}  (tag={tag})")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"[recon]   nav error: {str(e)[:100]}")

    await page.wait_for_timeout(wait_ms)

    # gentle scroll to trigger lazy loads
    for y in (400, 1000, 1600):
        await page.evaluate(f"window.scrollTo(0,{y})")
        await page.wait_for_timeout(400)
    await page.evaluate("window.scrollTo(0,0)")

    if tab_clicks:
        for sel in tab_clicks:
            calls_before = len(calls)
            try:
                await page.click(sel, timeout=3000)
                await page.wait_for_timeout(2200)
                print(f"[recon]   clicked {sel}  ← new_calls={len(calls)-calls_before}")
            except Exception as e:
                print(f"[recon]   click miss [{sel}]: {str(e)[:60]}")

    name = slug(url, tag)
    await page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)

    html = await page.content()
    (DOMDUMP / f"{name}.html").write_text(html, encoding="utf-8")

    # tables summary
    tables = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('table')).slice(0,15).map((tb,i) => {
            const headers = Array.from(tb.querySelectorAll('thead th, tr:first-child th, tr:first-child td'))
                .slice(0,20).map(h => h.innerText.trim().replace(/\\s+/g,' ').slice(0,50));
            const rows = Array.from(tb.querySelectorAll('tbody tr')).slice(0,2).map(r =>
                Array.from(r.querySelectorAll('td')).slice(0,20).map(c =>
                    c.innerText.trim().replace(/\\s+/g,' ').slice(0,50)));
            return {i, id: tb.id, rowCount: tb.querySelectorAll('tr').length, headers, rows};
        });
    }""")

    summary = {
        "url": url, "tag": tag, "final_url": page.url,
        "title": await page.title(),
        "tables": tables,
        "api_calls": calls,
    }
    (APILOG / f"{name}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[recon]   saved  tables={len(tables)} api_calls={len(calls)}")
    await page.close()
    return summary


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )

        # 1. Company page — click through every data-bearing tab
        tabs = [
            "a[href='#cpricehistory']",
            "a[href='#cdividend']",
            "a[href='#crightshare']",
            "a[href='#cagm']",
            "a[href='#cqtrreport']",
            "a[href='#cfinanrep']",
            "a[href='#cnews']",
            "a[href='#cannouncements']",
            "a[href='#cfloorsheet']",
        ]
        await collect_page(ctx, "https://www.sharesansar.com/company/NABIL", "nabil_all_tabs",
                           tab_clicks=tabs, wait_ms=5000)

        # 2. The CORRECT cross-company list URLs (found in menu)
        list_pages = [
            "https://www.sharesansar.com/company-list",
            "https://www.sharesansar.com/proposed-dividend",
            "https://www.sharesansar.com/agm-list",
            "https://www.sharesansar.com/existing-issues",
            "https://www.sharesansar.com/icra-rating",
            "https://www.sharesansar.com/merger-acquisition",
            "https://www.sharesansar.com/sectorwise-share-price",
            # Macro
            "https://www.sharesansar.com/inflation",
            "https://www.sharesansar.com/remittance",
            "https://www.sharesansar.com/short-term-interest-rates",
            "https://www.sharesansar.com/bfis-deposit-lending",
            # Index
            "https://www.sharesansar.com/indices-sub-indices",
            "https://www.sharesansar.com/index-history-data",
            "https://www.sharesansar.com/datewise-indices",
        ]
        for url in list_pages:
            await collect_page(ctx, url, tag="v2", wait_ms=3500)
            await asyncio.sleep(1.5)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
