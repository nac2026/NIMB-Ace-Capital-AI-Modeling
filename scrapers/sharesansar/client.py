"""Sharesansar HTTP client. Owns session, CSRF token, symbol→company-id map, rate limiting.

One instance per scraper run. Re-acquires token + map on 419 (CSRF stale)."""
from __future__ import annotations
import gzip, hashlib, random, re, time
from pathlib import Path
from typing import Any
import httpx

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

BASE = "https://www.sharesansar.com"
RAW_DIR = Path(__file__).resolve().parent.parent / "output" / "raw_html"


class SharesansarClient:
    def __init__(self, rate_limit_seconds: float = 2.0, jitter: float = 1.0,
                 snapshot_raw: bool = True):
        self.c = httpx.Client(
            base_url=BASE,
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=60.0,
            follow_redirects=True,
        )
        self.token: str = ""
        self.symbol_to_id: dict[str, int] = {}
        self.rate = rate_limit_seconds
        self.jitter = jitter
        self.snapshot = snapshot_raw
        self._last_req_t = 0.0

    # ---- rate limiting + snapshot ----
    def _wait(self) -> None:
        elapsed = time.time() - self._last_req_t
        target = self.rate + random.uniform(0, self.jitter)
        if elapsed < target:
            time.sleep(target - elapsed)
        self._last_req_t = time.time()

    def _snapshot(self, url: str, body: str) -> None:
        if not self.snapshot:
            return
        h = hashlib.sha1(url.encode()).hexdigest()[:16]
        ts = time.strftime("%Y%m%d")
        p = RAW_DIR / f"{ts}__{h}.html.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.write(f"<!-- URL: {url} -->\n{body}")

    # ---- session bootstrap ----
    def bootstrap(self, seed_symbol: str = "NABIL") -> None:
        """Load a company page to acquire CSRF token + cookies + symbol→id map."""
        self._wait()
        r = self.c.get(f"/company/{seed_symbol}")
        r.raise_for_status()
        self._snapshot(str(r.url), r.text)
        self.token = self._extract_token(r.text)
        self.symbol_to_id = self._build_symbol_map(r.text)
        if not self.token or not self.symbol_to_id:
            raise RuntimeError("bootstrap failed: missing token or symbol map")

    @staticmethod
    def _extract_token(html: str) -> str:
        m = re.search(r'<meta name="_token" content="([^"]+)"', html)
        return m.group(1) if m else ""

    @staticmethod
    def _build_symbol_map(html: str) -> dict[str, int]:
        pat = re.compile(r'\{"id":(\d+),"symbol":"([^"]+)","companyname":"[^"]*"\}')
        return {sym: int(cid) for cid, sym, *_ in pat.findall(html)}

    def company_id(self, symbol: str) -> int:
        if not self.symbol_to_id:
            self.bootstrap()
        cid = self.symbol_to_id.get(symbol.upper())
        if cid is None:
            raise KeyError(f"symbol not in Sharesansar map: {symbol}")
        return cid

    # ---- low-level request helpers ----
    def _ajax_headers(self, referer: str) -> dict:
        return {
            "Referer": f"{BASE}{referer}",
            "Origin": BASE,
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-Token": self.token,
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

    def post_datatable(self, path: str, company_id: int, length: int = 50,
                       referer: str = "/company/NABIL") -> list[dict]:
        """POST to a /company-* endpoint and paginate through all rows."""
        all_rows: list[dict] = []
        start = 0
        draw = 0
        while True:
            draw += 1
            body = self._dt_body(company_id, start=start, length=length, draw=draw)
            self._wait()
            r = self.c.post(path, data=body, headers=self._ajax_headers(referer))
            if r.status_code == 419:
                # CSRF expired → re-bootstrap once then retry
                self.bootstrap()
                body["draw"] = str(draw)
                r = self.c.post(path, data=body, headers=self._ajax_headers(referer))
            r.raise_for_status()
            j = r.json()
            rows = j.get("data", []) or []
            all_rows.extend(rows)
            total = j.get("recordsTotal", 0)
            if start + len(rows) >= total or not rows:
                break
            start += len(rows)
        return all_rows

    def post_quarterly_report(self, symbol: str, company_id: int, sector: str) -> str:
        """Returns raw HTML of the quarterly-report tab (balance sheet, P&L, key metrics)."""
        self._wait()
        r = self.c.post("/company-quarterly-report",
                        data={"company": str(company_id), "symbol": symbol, "sector": sector},
                        headers={**self._ajax_headers(f"/company/{symbol}"),
                                 "Content-Type": "application/x-www-form-urlencoded"})
        r.raise_for_status()
        self._snapshot(str(r.url) + f"?symbol={symbol}", r.text)
        return r.text

    def get_page(self, path: str) -> str:
        """Plain GET of an HTML page (for macro, sectorwise lists, etc.)."""
        self._wait()
        r = self.c.get(path)
        r.raise_for_status()
        self._snapshot(str(r.url), r.text)
        return r.text

    def get_datatable(self, path: str, length: int = 50) -> list[dict]:
        """GET a public list endpoint (like /icra-rating) with DataTables params."""
        all_rows: list[dict] = []
        start = 0
        draw = 0
        while True:
            draw += 1
            params = {"draw": str(draw), "start": str(start), "length": str(length),
                      "search[value]": "", "search[regex]": "false"}
            self._wait()
            r = self.c.get(path, params=params,
                           headers={"X-Requested-With": "XMLHttpRequest",
                                    "Accept": "application/json"})
            r.raise_for_status()
            j = r.json()
            rows = j.get("data", []) or []
            all_rows.extend(rows)
            total = j.get("recordsTotal", 0)
            if start + len(rows) >= total or not rows:
                break
            start += len(rows)
        return all_rows

    # ---- datatable body builder ----
    @staticmethod
    def _dt_body(company_id: int, start: int = 0, length: int = 1000, draw: int = 1,
                 n_cols: int = 9) -> dict:
        body: dict[str, str] = {"draw": str(draw)}
        for i in range(n_cols):
            body[f"columns[{i}][data]"] = f"col{i}"
            body[f"columns[{i}][name]"] = ""
            body[f"columns[{i}][searchable]"] = "true"
            body[f"columns[{i}][orderable]"] = "false"
            body[f"columns[{i}][search][value]"] = ""
            body[f"columns[{i}][search][regex]"] = "false"
        body["start"] = str(start)
        body["length"] = str(length)
        body["search[value]"] = ""
        body["search[regex]"] = "false"
        body["company"] = str(company_id)
        return body

    def close(self) -> None:
        self.c.close()

    def __enter__(self):
        self.bootstrap()
        return self

    def __exit__(self, *a):
        self.close()
