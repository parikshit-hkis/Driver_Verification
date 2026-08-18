"""
Shared Normalizer Utility for Microservices
"""

import re
from typing import Optional, Dict
from datetime import datetime

_MONTH_MAP: Dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

_DATE_PATTERNS = [
    (r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", "ymd"),
    (r"(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})", "dmy"),
    (r"(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{2})", "dmy2"),
    (r"(\d{1,2})[\s\-]+([A-Za-z]{3,9})[\s\-]+(\d{4})", "dmy_alpha"),
    (r"([A-Za-z]{3,9})[\s\-]+(\d{1,2})[,\s]+(\d{4})", "mdy_alpha"),
]


def normalize_dob(text: str) -> Optional[str]:
    return _parse_date(text)


def normalize_date(text: str) -> Optional[str]:
    return _parse_date(text)


def _parse_date(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.strip()

    for pattern, fmt in _DATE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        g = m.groups()
        try:
            if fmt == "ymd":
                year, month, day = int(g[0]), int(g[1]), int(g[2])
            elif fmt == "dmy":
                day, month, year = int(g[0]), int(g[1]), int(g[2])
            elif fmt == "dmy2":
                day, month = int(g[0]), int(g[1])
                yr = int(g[2])
                year = (2000 + yr) if yr < 30 else (1900 + yr)
            elif fmt == "dmy_alpha":
                day = int(g[0])
                month = _MONTH_MAP.get(g[1].lower()[:3], 0)
                year = int(g[2])
                if month == 0:
                    continue
            elif fmt == "mdy_alpha":
                month = _MONTH_MAP.get(g[0].lower()[:3], 0)
                day = int(g[1])
                year = int(g[2])
                if month == 0:
                    continue
            else:
                continue

            dt = datetime(year, month, day)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OverflowError):
            continue

    return None


def normalize_name(text: str) -> Dict[str, Optional[str]]:
    empty = {"full_name": None}
    if not text:
        return empty

    cleaned = re.sub(r"[^A-Za-z\s'\.]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().title()

    words = [
        w for w in cleaned.split()
        if len(w) > 1 or w.isalpha()
    ]

    if not words:
        return empty

    return {"full_name": " ".join(words)}


def normalize_aadhaar_number(text: str) -> Optional[str]:
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 12:
        return f"{digits[:4]} {digits[4:8]} {digits[8:]}"
    return None


def normalize_pan_number(text: str) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r"[\s\-]", "", text).upper()
    if re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", cleaned):
        return cleaned
    return None


def normalize_dl_number(text: str) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
    m = re.fullmatch(r"([A-Z]{2})(\d{2})(\d{4})(\d{7})", cleaned)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}"
    if len(cleaned) >= 10 and re.match(r"^[A-Z]{2}\d", cleaned):
        return cleaned
    return None


def normalize_rc_number(text: str) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
    m_bh = re.fullmatch(r"(\d{2})(BH)(\d{4})([A-Z]{1,2})", cleaned)
    if m_bh:
        return f"{m_bh.group(1)}-{m_bh.group(2)}-{m_bh.group(3)}-{m_bh.group(4)}"
    m_state = re.fullmatch(r"([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{4})", cleaned)
    if m_state:
        rto = f"{int(m_state.group(2)):02d}"
        return f"{m_state.group(1)}-{rto}-{m_state.group(3)}-{m_state.group(4)}"
    if len(cleaned) >= 8 and re.match(r"^[A-Z]{2}\d", cleaned):
        return cleaned
    return None
