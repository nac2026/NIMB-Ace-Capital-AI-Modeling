"""Find the max page length the server will serve."""
import sys
sys.path.insert(0, "..")
from sharesansar.client import SharesansarClient

with SharesansarClient() as c:
    cid = c.company_id("NABIL")
    for L in (50, 100, 200, 300, 500, 750, 1000):
        body = c._dt_body(cid, start=0, length=L)
        r = c.c.post("/company-price-history", data=body,
                     headers=c._ajax_headers("/company/NABIL"))
        status = r.status_code
        try:
            j = r.json()
            data_len = len(j.get("data", []))
            total = j.get("recordsTotal")
        except Exception:
            data_len = "?"
            total = "?"
        print(f"length={L:<4}  status={status}  data_len={data_len}  recordsTotal={total}")
