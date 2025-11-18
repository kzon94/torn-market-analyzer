import re
import unicodedata
from html import unescape
from typing import List, Optional

QTY_RX = re.compile(r'\bx(\d+)\b', flags=re.I)
FLOAT_RX = re.compile(r'\b\d+\.\d+\b')
STANDALONE_INT_RX = re.compile(r'(?<=\s)\d+(?=\s)')
LOWER_UPPER_RX = re.compile(r'([a-z])([A-Z])')
NUMERIC_ONLY_RX = re.compile(r'^\d+(\.\d+)?$')  # pure numeric line


def strip_accents(s: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )


def to_key(name: str) -> str:
    s = unescape(name or "").strip().lower()
    s = strip_accents(s)
    s = re.sub(r'[^a-z0-9]+', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s


def split_lower_upper(s: str) -> str:
    return LOWER_UPPER_RX.sub(r'\1 \2', s)


def split_raw_into_segments(raw_text: str) -> List[str]:
    # Parse Torn Add Listing text into one segment per item
    lines = [l.strip() for l in raw_text.splitlines()]
    segments: List[str] = []
    current_name: Optional[str] = None
    current_qty: Optional[int] = None
    skip_current_item = False

    for line in lines:
        if not line:
            continue

        low = line.lower()

        # Top-level UI noise
        if low in {"add to market", "clear all"}:
            continue

        # Mark items that must be excluded
        if low in {"untradable", "equipped"}:
            skip_current_item = True
            continue

        # Ignore simple UI labels
        if low in {"rrp", "qty", "price"}:
            continue
        if low == "n/a":
            continue

        # Ignore "Select <item>" lines
        if low.startswith("select "):
            continue

        # Ignore pure numeric lines (weapon stats such as 67.58, 40.06, etc.)
        if NUMERIC_ONLY_RX.fullmatch(low):
            continue

        # Ignore price lines like "$12,345"
        if line.lstrip().startswith("$"):
            compact = line.replace(" ", "")
            if re.fullmatch(r"\$\s*\d[\d,\.]*", compact):
                continue

        # Quantity line "x5", "x27"...
        m_qty = re.fullmatch(r"x\s*(\d+)", low)
        if m_qty and current_name is not None:
            current_qty = int(m_qty.group(1))
            continue

        # Close item block when hitting the listing-action line
        if low.startswith("make my listing of"):
            if current_name and not skip_current_item:
                if current_qty is not None:
                    segments.append(f"{current_name} x{current_qty}")
                else:
                    segments.append(current_name)

            current_name = None
            current_qty = None
            skip_current_item = False
            continue

        # New item name: only consider lines that contain letters
        if re.search(r"[a-z]", low):
            current_name = line
            current_qty = None
            skip_current_item = False

    # Finalize last item if needed
    if current_name and not skip_current_item:
        if current_qty is not None:
            segments.append(f"{current_name} x{current_qty}")
        else:
            segments.append(current_name)

    return segments