"""
Shared Normalizer Utility for Microservices
"""

import re
from typing import Optional, Dict, List
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
    (r"(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{2})(?!\d)", "dmy2"),
    (r"(\d{1,2})[\s\-]*(?:[/\-])?[\s\-]*([A-Za-z]{3,9})[\s\-]*(?:[/\-])?[\s\-]*(\d{4})", "dmy_alpha"),
    (r"(\d{1,2})[\s\-]*(?:[/\-])?[\s\-]*([A-Za-z]{3,9})[\s\-]*(?:[/\-])?[\s\-]*(\d{2})(?!\d)", "dmy_alpha2"),
    (r"([A-Za-z]{3,9})[\s\-]+(\d{1,2})[,\s]+(\d{4})", "mdy_alpha"),
    (r"(?<!\d)(\d{2})[/\.]?(\d{2})[/\.]?(\d{4})(?!\d)", "dmy_compact"),
]

_STATE_PREFIX_REPAIR = {
    "G": "GJ",
    "P": "MP",
    "M": "MH",
    "U": "UP",
    "R": "RJ",
    "J": "JH",
    "D": "DL",
}


_OCR_DATE_CHAR_MAP = {
    "S": "5", "s": "5",
    "O": "0", "o": "0", "Q": "0", "D": "0",
    "I": "1", "l": "1", "!": "1",
    "Z": "2", "z": "2",
    "B": "8",
}
_OCR_DATE_TRANS = str.maketrans(_OCR_DATE_CHAR_MAP)


def normalize_dob(text: str) -> Optional[str]:
    return _parse_date(text)


def normalize_date(text: str) -> Optional[str]:
    return _parse_date(text)


def _parse_date(text: str) -> Optional[str]:
    dates = parse_all_dates(text)
    return dates[0] if dates else None


def parse_all_dates(text: str) -> List[str]:
    if not text:
        return []
    dates = []

    # 1. Direct standard patterns
    for pattern, fmt in _DATE_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            g = m.groups()
            try:
                if fmt == "ymd":
                    year, month, day = int(g[0]), int(g[1]), int(g[2])
                elif fmt == "dmy" or fmt == "dmy_compact":
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
                elif fmt == "dmy_alpha2":
                    day = int(g[0])
                    month = _MONTH_MAP.get(g[1].lower()[:3], 0)
                    yr = int(g[2])
                    year = (2000 + yr) if yr < 45 else (1900 + yr)
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

                if month > 12 and 1 <= day <= 12:
                    day, month = month, day

                if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100:
                    d_str = f"{year:04d}-{month:02d}-{day:02d}"
                    if d_str not in dates:
                        dates.append(d_str)
            except (ValueError, OverflowError):
                continue

    # 2. Compact slash pattern like 0909/1993 or 0909/1393
    compact_slash = r"(?<!\d)(\d{2})(\d{2})[/\.\-](\d{4})(?!\d)"
    for m in re.finditer(compact_slash, text):
        try:
            dy, mo, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1300 <= yr <= 1399:
                yr += 600
            if mo > 12 and 1 <= dy <= 12:
                dy, mo = mo, dy
            if 1 <= mo <= 12 and 1 <= dy <= 31 and 1900 <= yr <= 2100:
                d_str = f"{yr:04d}-{mo:02d}-{dy:02d}"
                if d_str not in dates:
                    dates.append(d_str)
        except Exception:
            continue

    # 3. OCR noisy pattern parse
    noisy_pat = r"([0-9SOIlZB]{1,2})[-/\.]([0-9SOIlZB]{1,2})[-/\.]([0-9SOIlZB]{2,4})"
    for m in re.finditer(noisy_pat, text):
        clean_parts = [p.translate(_OCR_DATE_TRANS) for p in m.groups()]
        if all(p.isdigit() for p in clean_parts):
            try:
                g = [int(x) for x in clean_parts]
                if len(clean_parts[2]) == 4:
                    day, month, year = g
                elif len(clean_parts[0]) == 4:
                    year, month, day = g
                else:
                    day, month = g[0], g[1]
                    year = (2000 + g[2]) if g[2] < 30 else (1900 + g[2])

                # Fix OCR digit typo 13xx -> 19xx
                if 1300 <= year <= 1399:
                    year += 600

                if month > 12 and 1 <= day <= 12:
                    day, month = month, day

                if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100:
                    d_str = f"{year:04d}-{month:02d}-{day:02d}"
                    if d_str not in dates:
                        dates.append(d_str)
            except (ValueError, OverflowError):
                continue

    return dates


def normalize_name(text: str) -> Dict[str, Optional[str]]:
    empty = {"full_name": None}
    if not text:
        return empty

    cleaned = re.sub(r"^(?:4/)?\s*(?:name|namie|mame|applicant\s*name|holder\s*name|applicant|holder|namc|nam)[\s:\-/]*", "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"[^A-Za-z\s'\.]", " ", cleaned)
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
    
    # 1. Direct regex search in text first
    m_search = re.search(r"([A-Z]{2})\s*[-]?\s*(\d{2}[A-Z0-9]?)\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{7})", text.upper())
    if m_search:
        return f"{m_search.group(1)}-{m_search.group(2)}-{m_search.group(3)}-{m_search.group(4)}"

    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
    # Strip common label prefixes attached to the DL number
    cleaned = re.sub(r"^(?:DLNO|DLN0|LN0|D/LNO|LICENCENO|LICENSENO|DRIVINGLICENCENO|DRIVINGLICENSENO)", "", cleaned)
    if cleaned.startswith("DL") and len(cleaned) > 15:
        cleaned = cleaned[2:]

    m = re.fullmatch(r"([A-Z]{2})(\d{2}[A-Z0-9]?)(\d{4})(\d{7})", cleaned)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}"
    
    # Check 1-char state code drop (e.g. G0520020065484 -> GJ-05-2002-0065484)
    m_one_char = re.fullmatch(r"([A-Z])(\d{2})(\d{4})(\d{7})", cleaned)
    if m_one_char:
        state_letter = m_one_char.group(1)
        if state_letter in _STATE_PREFIX_REPAIR:
            state_code = _STATE_PREFIX_REPAIR[state_letter]
            return f"{state_code}-{m_one_char.group(2)}-{m_one_char.group(3)}-{m_one_char.group(4)}"

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


