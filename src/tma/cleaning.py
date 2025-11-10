import re, unicodedata
from html import unescape
from typing import List, Optional

ACTION_FRAGMENTS = [
    "Unequip this Item","Equip this Item","Return to Faction","Send this Item","Take this Item",
    "Trash this Item","Donate this Item","Open this Item","Turn on this Item","Use this Item",
]
ACTION_RX = re.compile("|".join(re.escape(a) for a in ACTION_FRAGMENTS), flags=re.I)
QTY_RX    = re.compile(r'\bx(\d+)\b', flags=re.I)
FLOAT_RX  = re.compile(r'\b\d+\.\d+\b')
STANDALONE_INT_RX = re.compile(r'(?<=\s)\d+(?=\s)')
LOWER_UPPER_RX = re.compile(r'([a-z])([A-Z])')

def strip_accents(s: str) -> str:
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def to_key(name: str) -> str:
    s = unescape(name or "").strip().lower()
    s = strip_accents(s)
    s = re.sub(r'[^a-z0-9]+', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s

def split_lower_upper(s: str) -> str:
    return LOWER_UPPER_RX.sub(r'\1 \2', s)

def split_raw_into_segments(raw_text: str) -> List[str]:
    s = split_lower_upper(raw_text)
    s = ACTION_RX.sub("|", s)
    s = s.replace("|", " | ")
    s = re.sub(r'\s+', ' ', s).strip()
    parts = [p.strip() for p in s.split("|")]
    return [p for p in parts if p]

def extract_quantity(text: str) -> Optional[int]:
    m = QTY_RX.search(text)
    return int(m.group(1)) if m else None

def drop_color_prefix(text: str) -> str:
    s = text.strip()
    m = re.match(r'^(yellow|orange)([\s\-_]*)(.*)$', s, flags=re.I)
    return (m.group(3).strip() if m else s)

def strip_noise_keep_name(text: str) -> str:
    text = QTY_RX.sub(" ", text)
    text = FLOAT_RX.sub(" ", text)
    text = STANDALONE_INT_RX.sub(" ", text)
    text = split_lower_upper(text)
    text = text.replace('-', '_')
    text = re.sub(r'\s+', ' ', text).strip(" :_").strip()
    return text