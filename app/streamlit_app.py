import re
import unicodedata
from html import unescape
from typing import List, Optional

QTY_RX = re.compile(r'\bx(\d+)\b', flags=re.I)
FLOAT_RX = re.compile(r'\b\d+\.\d+\b')
STANDALONE_INT_RX = re.compile(r'(?<=\s)\d+(?=\s)')
LOWER_UPPER_RX = re.compile(r'([a-z])([A-Z])')


# --- Utility: remove accents ---
def strip_accents(s: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )


# --- Utility: normalize name into a safe key ---
def to_key(name: str) -> str:
    s = unescape(name or "").strip().lower()
    s = strip_accents(s)
    s = re.sub(r'[^a-z0-9]+', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s


def split_lower_upper(s: str) -> str:
    return LOWER_UPPER_RX.sub(r'\1 \2', s)


# --- MAIN: Parse Torn Market listing text into item segments ---
def split_raw_into_segments(raw_text: str) -> List[str]:
    """
    Parse structured Torn market listing text into clean item segments.
    - Extracts item names
    - Captures quantities (xN)
    - Skips Equipped / Untradable items
    - Ignores RRP, prices, Qty/Price headings, and system lines
    """
    lines = [l.strip() for l in raw_text.splitlines()]
    segments: List[str] = []
    current_name: Optional[str] = None
    current_qty: Optional[int] = None
    skip_current_item = False

    for line in lines:
        if not line:
            continue

        low = line.lower()

        # Recognize and mark items that must be excluded
        if low in {"equipped", "untradable"}:
            skip_current_item = True
            continue

        # Ignore noise phrases
        if low in {"rrp", "qty", "price"}:
            continue
        if low == "n/a":
            continue

        # Ignore price lines like "$12,345"
        if line.startswith("$"):
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

        # New item name
        current_name = line
        current_qty = None
        skip_current_item = False

    # Safety: finalize last item if needed
    if current_name and not skip_current_item:
        if current_qty is not None:
            segments.append(f"{current_name} x{current_qty}")
        else:
            segments.append(current_name)

    return segments


# --- Extract quantity "xN" ---
def extract_quantity(text: str) -> Optional[int]:
    m = QTY_RX.search(text)
    return int(m.group(1)) if m else None


# --- Keep only the cleaned name ---
def drop_color_prefix(text: str) -> str:
    s = text.strip()
    m = re.match(r'^(yellow|orange)([\s\-_]*)(.*)$', s, flags=re.I)
    return (m.group(3).strip() if m else s)


# --- Clean noise while keeping a usable item name ---
def strip_noise_keep_name(text: str) -> str:
    text = QTY_RX.sub(" ", text)
    text = FLOAT_RX.sub(" ", text)
    text = STANDALONE_INT_RX.sub(" ", text)
    text = split_lower_upper(text)
    text = text.replace('-', '_')
    text = re.sub(r'\s+', ' ', text).strip(" :_").strip()
    return text
