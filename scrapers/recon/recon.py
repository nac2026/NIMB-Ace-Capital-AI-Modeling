"""Reconnaissance helper: visit a URL, screenshot, dump DOM summary, capture network."""
from __future__ import annotations
import asyncio, json, re, sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parent.parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
DOMDUMP = Path(__file__).resolve().parent.parent / "dom_dumps"
DOMDUMP.mkdir(parents=True, exist_ok=True)


def slug(url: str, tag: str = "") -> str:
    p = urlparse(url)
    base = re.sub(r"[^a-zA-Z0-9]+", "_", p.path.strip("/") or "root")
    if p.query:
        base += "__" + re.sub(r"[^a-zA-Z0-9]+", "_", p.query)[:40]
    return (base + ("__" + tag if tag else ""))[:120]


async def recon(url: str, tag: str = "", click_selectors: list[str] | None = None,
                wait_ms: int = 3000, scroll: bool = True):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        page = await ctx.new_page()

        calls: list[dict] = []

        async def on_response(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "")
                if any(k in ct for k in ("json", "javascript", "xml")) or "api" in resp.url or "ajax" in resp.url.lower():
                    body = None
                    if "json" in ct:
                        try:
                            body_text = await resp.text()
                            body = body_text[:600]
                        except Exception:
                            body = None
                    calls.append({
                        "url": resp.url,
                        "status": resp.status,
                        "method": resp.request.method,
                        "content_type": ct,
                        "size": len(await resp.body()) if resp.status == 200 else 0,
                        "body_preview": body,
                    })
            except Exception:
                pass

        page.on("response", on_response)

        print(f"[recon] → {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"[recon]   nav error: {e}")

        await page.wait_for_timeout(wait_ms)

        if scroll:
            for y in (300, 800, 1400):
                await page.evaluate(f"window.scrollTo(0,{y})")
                await page.wait_for_timeout(300)
            await page.evaluate("window.scrollTo(0,0)")

        if click_selectors:
            for sel in click_selectors:
                try:
                    await page.click(sel, timeout=2500)
                    await page.wait_for_timeout(1500)
                    print(f"[recon]   clicked: {sel}")
                except Exception as e:
                    print(f"[recon]   click miss [{sel}]: {str(e)[:80]}")

        name = slug(url, tag)
        shot = OUT / f"{name}.png"
        await page.screenshot(path=str(shot), full_page=True)
        print(f"[recon]   shot: {shot.relative_to(OUT.parent.parent)}")

        html = await page.content()
        (DOMDUMP / f"{name}.html").write_text(html, encoding="utf-8")

        summary = {
            "url": url,
            "tag": tag,
            "title": await page.title(),
            "final_url": page.url,
            "tables": await page.evaluate("""() => {
                const t = Array.from(document.querySelectorAll('table'));
                return t.slice(0,12).map((tb,i) => {
                    const headers = Array.from(tb.querySelectorAll('thead th, tr:first-child th, tr:first-child td'))
                        .slice(0,20).map(h => h.innerText.trim().replace(/\\s+/g,' ').slice(0,60));
                    const rowCount = tb.querySelectorAll('tr').length;
                    const firstRow = Array.from(tb.querySelectorAll('tr')).slice(1,2)[0];
                    const firstRowTexts = firstRow ? Array.from(firstRow.querySelectorAll('td'))
                        .slice(0,20).map(c => c.innerText.trim().replace(/\\s+/g,' ').slice(0,60)) : [];
                    return {index: i, id: tb.id, class: tb.className.slice(0,120),
                            rowCount, headers, firstRow: firstRowTexts};
                });
            }"""),
            "tabs": await page.evaluate("""() => {
                const sel = 'a[role=tab], .nav-tabs a, .nav-pills a, ul.nav li a, .tabs a, [data-toggle=tab]';
                const els = Array.from(document.querySelectorAll(sel));
                return els.slice(0,30).map(a => ({text: a.innerText.trim().slice(0,40),
                                                   href: a.getAttribute('href'),
                                                   data_target: a.getAttribute('data-target') || a.getAttribute('data-tab')}));
            }"""),
            "downloadables": await page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('a[href], button'));
                return els.filter(e => /excel|csv|download|export/i.test(e.innerText + ' ' + (e.getAttribute('href')||'')))
                    .slice(0,30).map(e => ({text: e.innerText.trim().slice(0,60),
                                            href: e.tagName==='A'?e.getAttribute('href'):null}));
            }"""),
            "network_api_calls": calls[:60],
        }
        summary_path = DOMDUMP / f"{name}.summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[recon]   summary: {summary_path.relative_to(OUT.parent.parent)}"
              f"  tables={len(summary['tables'])} tabs={len(summary['tabs'])} "
              f"dl={len(summary['downloadables'])} api={len(summary['network_api_calls'])}")

        await browser.close()
        return summary


async def main():
    # Each target: (url, tag, optional click selectors to reveal hidden tabs)
    targets = [
        ("https://www.sharesansar.com/company/NABIL", "ss_nabil_home", None),
        ("https://www.sharesansar.com/existing-bonus-share", "ss_bonus", None),
        ("https://www.sharesansar.com/existing-right-share", "ss_rights", None),
        ("https://www.sharesansar.com/existing-dividend", "ss_dividend", None),
        ("https://www.sharesansar.com/today-share-price", "ss_today", None),
        ("https://www.sharesansar.com/live-trading", "ss_live", None),
    ]
    for url, tag, clicks in targets:
        try:
            await recon(url, tag, click_selectors=clicks, wait_ms=3500)
        except Exception as e:
            print(f"[recon] FAILED {url}: {e}")
        await asyncio.sleep(2)  # polite delay

if __name__ == "__main__":
    asyncio.run(main())
