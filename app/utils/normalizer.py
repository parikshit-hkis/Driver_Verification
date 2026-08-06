"""
Shared Normalizer
=================
Converts raw extracted strings into clean, standardized formats.

All functions are pure (no side effects) and return None on failure
rather than raising exceptions.
"""

import re
from typing import Optional, Dict
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════════════
# Date normalization
# ══════════════════════════════════════════════════════════════════════════════

_MONTH_MAP: Dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

# Ordered from most to least specific to avoid wrong matches
_DATE_PATTERNS = [
    # YYYY-MM-DD or YYYY/MM/DD  (already ISO)
    (r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", "ymd"),
    # DD-MM-YYYY or DD/MM/YYYY or DD.MM.YYYY  (Indian standard)
    (r"(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})", "dmy"),
    # DD-MM-YY or DD/MM/YY
    (r"(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{2})", "dmy2"),
    # DD Mon YYYY   e.g.  18 May 1999  /  18-May-1999
    (r"(\d{1,2})[\s\-]([A-Za-z]{3,9})[\s\-](\d{4})", "dmy_alpha"),
    # Mon DD, YYYY  e.g.  May 18, 1999
    (r"([A-Za-z]{3,9})[\s\-](\d{1,2})[,\s]+(\d{4})", "mdy_alpha"),
]


def normalize_dob(text: str) -> Optional[str]:
    """Normalize a date-of-birth string → ISO ``YYYY-MM-DD``."""
    return _parse_date(text)


def normalize_date(text: str) -> Optional[str]:
    """Normalize any date string → ISO ``YYYY-MM-DD``."""
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


# ══════════════════════════════════════════════════════════════════════════════
# Name normalization
# ══════════════════════════════════════════════════════════════════════════════

def normalize_name(text: str) -> Dict[str, Optional[str]]:
    """
    Normalize an Indian name string.

    Gujarat naming convention is typically:
        Surname  FirstName  FatherName
        e.g. "Patel Jay Dhansukhbhai"

    Returns a dict with keys:
        full_name, first_name, middle_name, last_name
    """
    empty = {
        "full_name": None,
        "first_name": None,
        "middle_name": None,
        "last_name": None,
    }

    if not text:
        return empty

    # Clean: strip digits, punctuation (keep apostrophes / dots inside names)
    cleaned = re.sub(r"[^A-Za-z\s'\.]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().title()

    # Filter single-char or purely non-alpha tokens
    words = [
        w for w in cleaned.split()
        if len(w) > 1 or w.isalpha()
    ]

    if not words:
        return empty

    full_name = " ".join(words)

    if len(words) == 1:
        return {**empty, "full_name": full_name, "first_name": words[0]}

    if len(words) == 2:
        # Two words: [0] = Surname (first_name), [1] = Given Name (middle_name)
        return {
            "full_name": full_name,
            "first_name": words[0],
            "middle_name": words[1],
            "last_name": None,
        }

    if len(words) == 3:
        # Three words: [0] = Surname (first_name), [1] = Given Name (middle_name), [2] = Father/Last (last_name)
        return {
            "full_name": full_name,
            "first_name": words[0],
            "middle_name": words[1],
            "last_name": words[2],
        }

    # 4+ words: [0] = Surname (first_name), [1] = Given Name (middle_name), rest = last_name
    return {
        "full_name": full_name,
        "first_name": words[0],
        "middle_name": words[1],
        "last_name": " ".join(words[2:]),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Document number normalization
# ══════════════════════════════════════════════════════════════════════════════

def normalize_aadhaar_number(text: str) -> Optional[str]:
    """
    Format Aadhaar number as ``XXXX XXXX XXXX``.
    Accepts any string containing 12 consecutive digits.
    """
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 12:
        return f"{digits[:4]} {digits[4:8]} {digits[8:]}"
    return None


def normalize_pan_number(text: str) -> Optional[str]:
    """
    Normalize PAN to uppercase 10-char ``AAAAA9999A`` format.
    Returns None if it doesn't match the format.
    """
    if not text:
        return None
    cleaned = re.sub(r"[\s\-]", "", text).upper()
    if re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", cleaned):
        return cleaned
    return None


def normalize_dl_number(text: str) -> Optional[str]:
    """
    Normalize Gujarat DL number.
    Various input formats → ``GJ-RR-YYYY-NNNNNNN``

    Examples:
        GJ0120210012345  →  GJ-01-2021-0012345
        GJ-01-2021-0012345  →  GJ-01-2021-0012345
        GJ01 2021 0012345   →  GJ-01-2021-0012345
    """
    if not text:
        return None
    # Strip everything except alphanumeric
    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())

    # GJ + 2-digit RTO + 4-digit year + 7-digit serial
    m = re.fullmatch(r"(GJ)(\d{2})(\d{4})(\d{7})", cleaned)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}"

    # Accept as-is if starts with GJ (partial / non-standard)
    if cleaned.startswith("GJ") and len(cleaned) >= 10:
        return cleaned

    return None


def normalize_rc_number(text: str) -> Optional[str]:
    """
    Normalize Gujarat RC/registration number.
    Format: ``GJ-RR-XX-NNNN``  (e.g. GJ-01-AB-1234)

    Accepts with or without separators.
    """
    if not text:
        return None
    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())

    # GJ + 2-digit RTO + 1-2 letters + 4 digits
    m = re.fullmatch(r"(GJ)(\d{2})([A-Z]{1,3})(\d{4})", cleaned)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}"

    # Looser match — starts with GJ
    if cleaned.startswith("GJ") and len(cleaned) >= 8:
        return cleaned

    return None
