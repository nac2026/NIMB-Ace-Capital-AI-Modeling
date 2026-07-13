"""SMTM Data API client: auth + token refresh + header-aware rate limiting.

One instance owns one authenticated session. The access token is a 15-minute
JWT; we decode its `exp` claim and refresh proactively (and reactively on 401).

Rate limiting prefers the server's `ratelimit-remaining`/`ratelimit-reset`
response headers (the live policy is far more generous than the documented
100/min); it only falls back to a fixed min-interval when headers are absent."""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Iterator

import httpx

from .config import SMTMSettings, get_smtm_settings
from .models import (
    Broker,
    Company,
    FloorsheetPage,
    FloorsheetTrade,
    IndexTimeseriesPoint,
    IndexValue,
    KeyStatsRow,
    LiveStock,
    MarketSummary,
    TimeseriesPoint,
)

_log = logging.getLogger("nrc_smtm.client")

_LOGIN = "/smtm/auth/login"
_REFRESH = "/smtm/auth/refresh-token"


def _jwt_exp(token: str) -> float | None:
    """Best-effort unix-seconds `exp` from a JWT without verifying the signature."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # pad
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = claims.get("exp")
        return float(exp) if exp is not None else None
    except Exception:
        return None


class SMTMError(RuntimeError):
    """Raised for non-recoverable SMTM API failures."""


class SMTMClient:
    def __init__(self, settings: SMTMSettings | None = None, *, client: httpx.Client | None = None):
        self.s = settings or get_smtm_settings()
        self.c = client or httpx.Client(base_url=self.s.smtm_base_url.rstrip("/"),
                                        timeout=self.s.smtm_timeout_seconds)
        self._token: str = ""
        self._refresh_token: str = ""
        self._token_exp: float | None = None
        # Conservative fallback spacing when the server doesn't return rate headers.
        self._min_interval = 60.0 / max(1, self.s.smtm_rate_limit_per_min)
        self._last_req_t = 0.0

    # ---- auth -------------------------------------------------------------
    def login(self) -> None:
        user, pw = self.s.require_credentials()
        r = self.c.post(_LOGIN, json={"username": user, "password": pw})
        r.raise_for_status()
        self._absorb_auth(r.json())
        _log.info("smtm login ok (token exp=%s)", self._token_exp)

    def _refresh(self) -> bool:
        if not self._refresh_token:
            return False
        r = self.c.post(_REFRESH, json={"refreshToken": self._refresh_token})
        if r.status_code != 200:
            return False
        self._absorb_auth(r.json())
        return True

    def _absorb_auth(self, body: dict[str, Any]) -> None:
        payload = body.get("response", body)
        token = payload.get("token", "")
        if not token:
            raise SMTMError(f"login/refresh returned no token: {str(body)[:200]}")
        self._token = token
        self._refresh_token = payload.get("refreshToken", self._refresh_token)
        self._token_exp = _jwt_exp(token)

    def _ensure_token(self) -> None:
        if not self._token:
            self.login()
            return
        if self._token_exp is not None:
            if time.time() >= self._token_exp - self.s.smtm_token_refresh_margin_s:
                if not self._refresh():
                    self.login()

    # ---- rate-limited GET -------------------------------------------------
    def _throttle(self, resp: httpx.Response | None) -> None:
        """Sleep based on the previous response's rate headers, else min-interval."""
        remaining = reset = None
        if resp is not None:
            try:
                remaining = int(resp.headers.get("ratelimit-remaining", ""))
                reset = float(resp.headers.get("ratelimit-reset", ""))
            except (TypeError, ValueError):
                remaining = reset = None
        if remaining is not None and remaining <= 2 and reset:
            # Near the ceiling — wait out the window (reset is seconds in this API).
            time.sleep(min(reset, 10.0))
            self._last_req_t = time.time()
            return
        if remaining is not None and remaining > 5:
            # Plenty of headroom — only a tiny courtesy spacing.
            elapsed = time.time() - self._last_req_t
            if elapsed < 0.02:
                time.sleep(0.02 - elapsed)
            self._last_req_t = time.time()
            return
        # No headers (or low-ish): conservative fixed spacing.
        elapsed = time.time() - self._last_req_t
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_req_t = time.time()

    _last_resp: httpx.Response | None = None

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        self._ensure_token()
        self._throttle(self._last_resp)
        headers = {"Authorization": f"Bearer {self._token}"}
        r = self.c.get(path, params=params, headers=headers)
        if r.status_code == 401:
            # token rejected — re-login once and retry
            self.login()
            r = self.c.get(path, params=params, headers={"Authorization": f"Bearer {self._token}"})
        self._last_resp = r
        r.raise_for_status()
        return r.json()

    # ---- endpoints --------------------------------------------------------
    def market_status(self) -> bool:
        data = self._get("/smtm/live/market-status").get("data", {})
        return bool(data.get("isMarketLive", False))

    def market_summary(self) -> MarketSummary:
        return MarketSummary.model_validate(self._get("/smtm/live/market-summary").get("data", {}))

    def indices_live(self) -> list[IndexValue]:
        return [IndexValue.model_validate(x) for x in self._get("/smtm/live/indices-live").get("data", [])]

    def company_list(self) -> list[Company]:
        return [Company.model_validate(x) for x in self._get("/smtm/general/company_list").get("data", [])]

    def broker_list(self) -> list[Broker]:
        """Authoritative NEPSE broker directory (code → firm name + logo)."""
        return [Broker.model_validate(x) for x in self._get("/smtm/general/broker_list").get("data", [])]

    def stock_live_v2(self) -> list[LiveStock]:
        return [LiveStock.model_validate(x) for x in self._get("/smtm/live/stock-live-v2").get("data", [])]

    def floorsheet_page(self, page: int = 1, page_size: int = 500) -> FloorsheetPage:
        return FloorsheetPage.model_validate(
            self._get("/smtm/live/floorsheet-live", {"pageSize": page_size, "page": page})
        )

    def stock_timeseries(self, symbol: str) -> list[TimeseriesPoint]:
        """Intraday minute bars for `symbol` — CURRENT session only, newest-first."""
        return [TimeseriesPoint.model_validate(x)
                for x in self._get(f"/smtm/live/stock-timeseries/{symbol}").get("data", [])]

    def indices_timeseries(self, slug: str) -> list[IndexTimeseriesPoint]:
        """Index value/turnover timeseries for `slug` (e.g. 'nepse')."""
        return [IndexTimeseriesPoint.model_validate(x)
                for x in self._get(f"/smtm/live/indices-timeseries/{slug}").get("data", [])]

    # ---- financials (fundamentals) ----------------------------------------
    # `key_stats` is typed to the cross-sector subset the UI charts; the full
    # statements are broad + sector-variant, so they pass through as raw dicts.
    def key_stats(self, ticker: str, *, quarterly: bool = False) -> list[KeyStatsRow]:
        path = "get-quarterly-key-stats" if quarterly else "get-annual-key-stats"
        return [KeyStatsRow.model_validate(x)
                for x in self._get(f"/smtm/financials/{path}/{ticker}").get("data", [])]

    def income_statement(self, ticker: str, *, quarterly: bool = False) -> list[dict[str, Any]]:
        path = "get-quarterly-income-statement" if quarterly else "get-annual-income-statement"
        return self._get(f"/smtm/financials/{path}/{ticker}").get("data", [])

    def balance_sheet(self, ticker: str, *, quarterly: bool = False) -> list[dict[str, Any]]:
        path = "get-quarterly-balance-sheet" if quarterly else "get-annual-balance-sheet"
        return self._get(f"/smtm/financials/{path}/{ticker}").get("data", [])

    def cash_flow(self, ticker: str) -> list[dict[str, Any]]:
        """Annual cash-flow statement (no quarterly variant is exposed)."""
        return self._get(f"/smtm/financials/get-annual-cash-flow/{ticker}").get("data", [])

    # ---- floorsheet pagination helpers ------------------------------------
    def iter_floorsheet(self, page_size: int = 500, start_page: int = 1) -> Iterator[FloorsheetTrade]:
        """Yield every trade currently available, oldest first. Use for full-day backfill."""
        first = self.floorsheet_page(start_page, page_size)
        yield from first.data
        for page in range(start_page + 1, first.total_pages + 1):
            yield from self.floorsheet_page(page, page_size).data

    def fetch_new_trades(self, after_contract: int | None, page_size: int = 500) -> list[FloorsheetTrade]:
        """Return trades with contract_number > `after_contract`, oldest first.

        Pages are chronological-ascending and new trades land on the highest
        pages, so we walk from the last page backwards and stop once a page is
        entirely at/below the cursor. `after_contract=None` ⇒ full backfill."""
        head = self.floorsheet_page(1, page_size)
        if after_contract is None:
            out = list(head.data)
            for page in range(2, head.total_pages + 1):
                out.extend(self.floorsheet_page(page, page_size).data)
            return out
        collected: list[FloorsheetTrade] = []
        for page in range(head.total_pages, 0, -1):
            trades = head.data if page == 1 else self.floorsheet_page(page, page_size).data
            fresh = [t for t in trades if t.contract_number > after_contract]
            collected.extend(fresh)
            if len(fresh) < len(trades):  # this page reached the cursor — done
                break
        collected.sort(key=lambda t: t.contract_number)
        return collected

    # ---- lifecycle --------------------------------------------------------
    def close(self) -> None:
        self.c.close()

    def __enter__(self) -> "SMTMClient":
        self.login()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
