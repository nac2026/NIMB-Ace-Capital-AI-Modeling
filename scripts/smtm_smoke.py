"""SMTM Data API smoke test — run BEFORE building ingestion adapters.

Verifies the live NEPSE feed end to end against the documented contract:
  * auth login → token, then refresh-token round-trips
  * market-status / market-summary / indices-live / company_list / stock-live-v2
  * floorsheet-live pagination semantics + field shape
  * rate-limit headers (if the server exposes them)

Reads SMTM_BASE_URL / SMTM_USERNAME / SMTM_PASSWORD from the repo-root .env
(same loader pattern as the rest of the stack). No secrets are hard-coded.

Run:  uv run python scripts/smtm_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> dict[str, str]:
    """Minimal .env reader (avoids importing a settings package for a smoke test)."""
    env: dict[str, str] = {}
    dotenv = _REPO_ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    # real env vars win over .env
    for k in ("SMTM_BASE_URL", "SMTM_USERNAME", "SMTM_PASSWORD"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def _hdr(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def _show_rate_headers(resp: httpx.Response) -> None:
    rl = {k: v for k, v in resp.headers.items() if "rate" in k.lower() or "limit" in k.lower()}
    if rl:
        print(f"  rate-limit headers: {rl}")


def main() -> int:
    env = _load_env()
    base = env.get("SMTM_BASE_URL", "https://dataapi.smtmcapital.com.np").rstrip("/")
    user = env.get("SMTM_USERNAME", "")
    pw = env.get("SMTM_PASSWORD", "")
    if not user or not pw:
        print("ERROR: set SMTM_USERNAME / SMTM_PASSWORD in .env", file=sys.stderr)
        return 2

    client = httpx.Client(base_url=base, timeout=60.0)

    # ---- 1. login ----
    _hdr("1. POST /smtm/auth/login")
    r = client.post("/smtm/auth/login", json={"username": user, "password": pw})
    print(f"  status={r.status_code}")
    _show_rate_headers(r)
    r.raise_for_status()
    body = r.json()
    payload = body.get("response", body)
    token = payload.get("token", "")
    refresh = payload.get("refreshToken", "")
    print(f"  token len={len(token)}  refreshToken len={len(refresh)}  userId={payload.get('userId')}")
    if not token:
        print("ERROR: no token in login response:", json.dumps(body)[:500], file=sys.stderr)
        return 1
    auth = {"Authorization": f"Bearer {token}"}

    # ---- 2. refresh-token ----
    _hdr("2. POST /smtm/auth/refresh-token")
    r = client.post("/smtm/auth/refresh-token", json={"refreshToken": refresh})
    print(f"  status={r.status_code}")
    if r.status_code == 200:
        rt = r.json().get("response", r.json())
        new_token = rt.get("token", "")
        print(f"  refreshed token len={len(new_token)}  (changed={new_token != token})")
        if new_token:
            token = new_token
            auth = {"Authorization": f"Bearer {token}"}
    else:
        print(f"  WARN refresh returned {r.status_code}: {r.text[:200]}")

    # ---- 3. simple GETs ----
    for name, path in [
        ("market-status", "/smtm/live/market-status"),
        ("market-summary", "/smtm/live/market-summary"),
        ("indices-live", "/smtm/live/indices-live"),
    ]:
        _hdr(f"3. GET /smtm/live/{name}")
        r = client.get(path, headers=auth)
        print(f"  status={r.status_code}")
        _show_rate_headers(r)
        if r.status_code == 200:
            data = r.json().get("data", r.json())
            if isinstance(data, list):
                print(f"  rows={len(data)}  sample={json.dumps(data[0], default=str)[:300] if data else '(empty)'}")
            else:
                print(f"  data={json.dumps(data, default=str)[:400]}")
        else:
            print(f"  body={r.text[:200]}")

    # ---- 4. company_list (universe + sectors) ----
    _hdr("4. GET /smtm/general/company_list")
    r = client.get("/smtm/general/company_list", headers=auth)
    print(f"  status={r.status_code}")
    if r.status_code == 200:
        rows = r.json().get("data", [])
        sectors: dict[str, int] = {}
        active = 0
        for c in rows:
            sectors[c.get("sector", "?")] = sectors.get(c.get("sector", "?"), 0) + 1
            if c.get("status") == "A":
                active += 1
        print(f"  total companies={len(rows)}  active(status=A)={active}")
        print(f"  sectors ({len(sectors)}): {json.dumps(dict(sorted(sectors.items(), key=lambda x: -x[1])), indent=0)[:600]}")
        print(f"  sample={json.dumps(rows[0], default=str)[:300] if rows else '(empty)'}")

    # ---- 5. stock-live-v2 (all scrips in one call) ----
    _hdr("5. GET /smtm/live/stock-live-v2")
    r = client.get("/smtm/live/stock-live-v2", headers=auth)
    print(f"  status={r.status_code}")
    if r.status_code == 200:
        rows = r.json().get("data", [])
        print(f"  scrips={len(rows)}")
        if rows:
            print(f"  keys={list(rows[0].keys())}")
            print(f"  sample={json.dumps(rows[0], default=str)[:400]}")

    # ---- 6. floorsheet-live (pagination semantics) ----
    _hdr("6. GET /smtm/live/floorsheet-live?pageSize=500&page=1")
    r = client.get("/smtm/live/floorsheet-live", params={"pageSize": 500, "page": 1}, headers=auth)
    print(f"  status={r.status_code}")
    _show_rate_headers(r)
    if r.status_code == 200:
        j = r.json()
        rows = j.get("data", [])
        print(f"  totalCount={j.get('totalCount')}  totalPages={j.get('totalPages')}  currentPage={j.get('currentPage')}")
        print(f"  rows_this_page={len(rows)}")
        if rows:
            print(f"  keys={list(rows[0].keys())}")
            print(f"  first={json.dumps(rows[0], default=str)[:300]}")
            print(f"  last ={json.dumps(rows[-1], default=str)[:300]}")
            # Is page 1 newest or oldest? Inspect timestamp ordering to design the incremental cursor.
            ts = [row.get("timestamp") for row in rows if row.get("timestamp")]
            if ts:
                print(f"  ts range on page1: {ts[0]}  ..  {ts[-1]}  (ordering tells us cursor direction)")

    client.close()
    print("\nSMTM smoke test complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
