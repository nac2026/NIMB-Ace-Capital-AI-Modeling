"""Debug: single-shot call to /company-price-history with length=1000 — see what comes back."""
import sys
sys.path.insert(0, "..")
from sharesansar.client import SharesansarClient

with SharesansarClient() as c:
    cid = c.company_id("NABIL")
    print(f"company id: {cid}  token: {c.token[:16]}")

    # Single-shot post
    body = c._dt_body(cid, start=0, length=50)
    print(f"body keys: {list(body.keys())[:5]}...  company={body.get('company')}")
    r = c.c.post("/company-price-history", data=body,
                 headers=c._ajax_headers("/company/NABIL"))
    print(f"status: {r.status_code}  ct: {r.headers.get('content-type')}")
    print(f"body first 400: {r.text[:400]}")
    if "json" in r.headers.get("content-type", "").lower():
        j = r.json()
        print(f"recordsTotal: {j.get('recordsTotal')}  data_len: {len(j.get('data', []))}")

    # Try with length=1000
    body = c._dt_body(cid, start=0, length=1000)
    r = c.c.post("/company-price-history", data=body,
                 headers=c._ajax_headers("/company/NABIL"))
    print(f"\nlength=1000 → status: {r.status_code}  body first 300: {r.text[:300]}")
