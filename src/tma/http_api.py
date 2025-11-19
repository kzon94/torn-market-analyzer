import time, requests, math
from .config import BASE_URL, MAX_WORKERS, RETRIES, TIMEOUT
from .rate_limit import TokenBucket

def session_for_requests():
    s = requests.Session()
    a = requests.adapters.HTTPAdapter(pool_connections=MAX_WORKERS*4, pool_maxsize=MAX_WORKERS*4)
    s.mount("https://", a)
    s.headers.update({"accept": "application/json", "User-Agent": "torn-itemmarket-web/1.1"})
    return s

def attempt_call(session, bucket: TokenBucket, api_key: str, item_id: int, mode: int):
    url = f"{BASE_URL}/market/{item_id}/itemmarket"
    headers, params = {}, {"limit": 20, "offset": 0}
    if mode == 1: headers["Authorization"] = f"Apikey {api_key}"
    elif mode == 2: headers["Authorization"] = f"ApiKey {api_key}"
    else: params["key"] = api_key
    bucket.take(1)
    r = session.get(url, headers=headers, params=params, timeout=TIMEOUT)
    return r.status_code, r.json()

def fetch_first10(session, bucket, api_key: str, item_id: int, my_quantity: int):
    backoff = 0.8
    for _ in range(1, RETRIES+1):
        for mode in (1,2,3):
            try:
                status, data = attempt_call(session, bucket, api_key, item_id, mode)
            except Exception as e:
                status, data = None, {"error": {"code": -1, "error": str(e)}}
            if isinstance(data, dict) and "error" in data:
                code = data["error"].get("code"); msg = data["error"].get("error")
                if code == 2 and mode != 3: continue
                if code in (0,10) or status in (429,500,502,503,504):
                    time.sleep(backoff); backoff *= 1.6; break
                return {"item_id": item_id, "my_quantity": my_quantity, "error": f"API error {code}: {msg}"}
            else:
                im = (data or {}).get("itemmarket", {})
                item = im.get("item", {})
                listings = im.get("listings", []) or []
                row = {
                    "item_id": item.get("id"),
                    "item_name": item.get("name"),
                    "item_type": item.get("type"),
                    "average_price": item.get("average_price"),
                    "my_quantity": my_quantity,
                }
                for i, l in enumerate(listings[:20], start=1):
                    row[f"price_{i}"]  = l.get("price")
                    row[f"amount_{i}"] = l.get("amount")
                for i in range(len(listings)+1, 11):
                    row[f"price_{i}"]  = None
                    row[f"amount_{i}"] = None
                return row
        time.sleep(backoff); backoff *= 1.6

    return {"item_id": item_id, "my_quantity": my_quantity, "error": "Exhausted retries"}


