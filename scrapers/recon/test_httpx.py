"""Verify we can replay Sharesansar JSON endpoints with plain httpx (no browser)."""
import httpx, json, re

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

def extract_token(html: str) -> str:
    m = re.search(r'<meta name="_token" content="([^"]+)"', html)
    return m.group(1) if m else ""

# DataTables-style POST body — need company id at end
def dt_body(company_id: int, n_columns: int = 9):
    body = {"draw": "1"}
    for i in range(n_columns):
        body[f"columns[{i}][data]"] = f"col{i}"
        body[f"columns[{i}][name]"] = ""
        body[f"columns[{i}][searchable]"] = "true"
        body[f"columns[{i}][orderable]"] = "false"
        body[f"columns[{i}][search][value]"] = ""
        body[f"columns[{i}][search][regex]"] = "false"
    body["start"] = "0"
    body["length"] = "50"
    body["search[value]"] = ""
    body["search[regex]"] = "false"
    body["company"] = str(company_id)
    return body


def build_symbol_map(html: str) -> dict:
    """Parse the embedded autocomplete array → {symbol: company_id}."""
    import re
    pat = re.compile(r'\{"id":(\d+),"symbol":"([^"]+)","companyname":"([^"]*)"\}')
    return {sym: int(cid) for cid, sym, _name in pat.findall(html)}


with httpx.Client(timeout=30, headers={"User-Agent": UA}, follow_redirects=True) as c:
    # 1. seed the session by loading the company page (sets session cookies / referer)
    r = c.get("https://www.sharesansar.com/company/NABIL")
    token = extract_token(r.text)
    sym_map = build_symbol_map(r.text)
    company_id = sym_map.get("NABIL")
    print(f"GET /company/NABIL → {r.status_code}  cookies={len(c.cookies)}  "
          f"token={token[:16]}...  symbols_mapped={len(sym_map)}  NABIL.id={company_id}")

    headers = {
        "Referer": "https://www.sharesansar.com/company/NABIL",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRF-Token": token,
        "Origin": "https://www.sharesansar.com",
    }

    # 2. price history
    r = c.post("https://www.sharesansar.com/company-price-history", data=dt_body(company_id), headers=headers)
    print(f"\nPOST /company-price-history → {r.status_code}")
    try:
        j = r.json()
        print(f"  recordsTotal={j.get('recordsTotal')}  len(data)={len(j.get('data', []))}")
        if j.get("data"):
            print(f"  first row: {j['data'][0]}")
    except Exception as e:
        print(f"  not json: {r.text[:200]}")

    # 3. dividend (bonus + cash)
    r = c.post("https://www.sharesansar.com/company-dividend", data=dt_body(company_id), headers=headers)
    print(f"\nPOST /company-dividend → {r.status_code}")
    try:
        j = r.json()
        print(f"  recordsTotal={j.get('recordsTotal')}")
        for row in j.get("data", [])[:3]:
            print(f"  {row}")
    except Exception as e:
        print(f"  not json: {r.text[:200]}")

    # 4. quarterly report — special form
    r = c.post("https://www.sharesansar.com/company-quarterly-report",
               data={"company": "16", "symbol": "NABIL", "sector": "Commercial Bank"},
               headers={**headers, "Content-Type": "application/x-www-form-urlencoded"})
    print(f"\nPOST /company-quarterly-report → {r.status_code}  ct={r.headers.get('content-type','')[:40]}")
    txt = r.text
    print(f"  body len: {len(txt)}")
    print(f"  first 400 chars: {txt[:400]}")
    # search for key financial keywords
    for kw in ("EPS", "ROE", "NPL", "CAR", "Book Value", "Distributable"):
        print(f"  contains '{kw}': {kw.lower() in txt.lower()}")

    # 5. news
    r = c.post("https://www.sharesansar.com/company-news", data=dt_body(company_id), headers=headers)
    print(f"\nPOST /company-news → {r.status_code}")
    try:
        j = r.json()
        print(f"  recordsTotal={j.get('recordsTotal')}")
        for row in j.get("data", [])[:2]:
            print(f"  {row}")
    except Exception:
        print(f"  not json")

    # 6. cross-company: ICRA ratings (GET)
    r = c.get("https://www.sharesansar.com/icra-rating",
              params={"draw": "1", "start": "0", "length": "50"},
              headers=headers)
    print(f"\nGET /icra-rating → {r.status_code}")
    try:
        j = r.json()
        print(f"  recordsTotal={j.get('recordsTotal')}")
        print(f"  first: {j['data'][0] if j.get('data') else 'none'}")
    except Exception:
        print(f"  not json: {r.text[:200]}")
