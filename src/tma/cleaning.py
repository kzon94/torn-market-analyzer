import re
from typing import Any

_PRICE_RE = re.compile(r"^\$([\d,]+)$")
_QTY_RE = re.compile(r"^x(\d+)$", re.IGNORECASE)
_STAT_RE = re.compile(r"^\d+(?:\.\d+)?$")

_SKIP_EXACT = {"Qty", "Price", "RRP", "Untradable", "Equipped"}


def parse_add_listings_clipboard(raw_text: str) -> list[dict[str, Any]]:
    lines = [ln.strip() for ln in raw_text.splitlines()]
    lines = [ln for ln in lines if ln]

    items: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal cur
        if not cur:
            return
        if cur.get("untradable") or cur.get("equipped"):
            cur = None
            return
        items.append(cur)
        cur = None

    def is_name_line(s: str) -> bool:
        if s in _SKIP_EXACT:
            return False
        if s == "N/A":
            return False
        if s.startswith("Make my listing of "):
            return False
        if s.startswith("Select "):
            return False
        if "anonymous (+10% fee" in s:
            return False
        if _PRICE_RE.match(s):
            return False
        if _QTY_RE.match(s):
            return False
        if _STAT_RE.match(s):
            return False
        return True

    for ln in lines:
        if is_name_line(ln):
            flush()
            cur = {
                "name": ln,
                "qty": 1,
                "rrp": None,
                "equipped": False,
                "untradable": False,
                "has_select": False,
            }
            continue

        if not cur:
            continue

        if ln == "Equipped":
            cur["equipped"] = True
            continue

        if ln == "Untradable":
            cur["untradable"] = True
            continue

        if ln.startswith("Select "):
            cur["has_select"] = True
            continue

        if ln.startswith("Make my listing of "):
            continue

        m = _QTY_RE.match(ln)
        if m:
            cur["qty"] = int(m.group(1))
            continue

        m = _PRICE_RE.match(ln)
        if m:
            cur["rrp"] = int(m.group(1).replace(",", ""))
            continue

    flush()
    return items
