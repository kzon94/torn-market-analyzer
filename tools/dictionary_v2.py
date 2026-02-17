import csv
import json
from pathlib import Path

import requests

BASE_URL = "https://api.torn.com/v2"


def fetch_items(api_key: str):
    r = requests.get(
        f"{BASE_URL}/torn/items",
        params={"key": api_key},
        headers={"accept": "application/json"},
        timeout=20,
    )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    items = data.get("items") or data.get("torn", {}).get("items")
    if isinstance(items, dict):
        return list(items.values())
    return items or []


def build_dictionary(items):
    out, seen = [], set()
    for it in items:
        item_id, name = it.get("id"), it.get("name")
        if not item_id or not name:
            continue
        key = name.strip()
        k = key.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append({"key": key, "id": int(item_id)})
    out.sort(key=lambda x: x["id"])
    return out


def main():
    api_key = input("Enter Torn API key: ").strip()
    if not api_key:
        raise SystemExit("API key is empty.")

    out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    items = fetch_items(api_key)

    (out_dir / "torn_items_v2.json").write_text(
        json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    with (out_dir / "torn_item_dictionary.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["key", "id"])
        w.writeheader()
        w.writerows(build_dictionary(items))

    print(f"Saved in: {out_dir}")


if __name__ == "__main__":
    main()