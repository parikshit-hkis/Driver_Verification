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
    # YYYY-MM-DD or YYYY/MM/DD
    (r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", "ymd"),
    
    # DD-MM-YYYY or DD/MM/YYYY
    (r"(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})", "dmy"),
    
    # DD-MM-YY or DD/MM/YY
    (r"(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{2})", "dmy2"),
    
    
    # DD Mon YYYY -> EXACTLY 3 CAPTURE GROUPS FOR THE PARSER
    (r"(\d{1,2})[\s\-]+([A-Za-z]{3,9})[\s\-]+(\d{4})", "dmy_alpha"),
    
    # Mon DD, YYYY -> EXACTLY 3 CAPTURE GROUPS FOR THE PARSER
    (r"([A-Za-z]{3,9})[\s\-]+(\d{1,2})[,\s]+(\d{4})", "mdy_alpha"),
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
    Normalize an Indian name string:
      - Strips digits, non-alpha symbols (preserves internal dots and apostrophes)
      - Standardizes casing to Title Case
      - Collapses whitespace
    Returns a dict with 'full_name'.
    """
    empty = {"full_name": None}

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
    return {"full_name": full_name}


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


# List of all Indian State and Union Territory 2-letter codes
_ALL_INDIA_STATE_CODES = (
    "AP|AR|AS|BR|CG|CT|GA|GJ|HR|HP|JH|KA|KL|MP|MH|MN|ML|MZ|NL|"
    "OD|OR|PB|RJ|SK|TN|TS|TG|TR|UP|UK|UA|WB|AN|CH|DN|DD|DH|DL|JK|LA|LD|PY"
)


def normalize_dl_number(text: str) -> Optional[str]:
    """
    Normalize Indian Driving Licence (DL) number for ALL States & UTs.
    Standard Sarathi format → ``SS-RR-YYYY-NNNNNNN``

    Examples:
        MH0220180012345  →  MH-02-2018-0012345
        DL-04-2020-0098765 → DL-04-2020-0098765
        RJ14 2015 0043210 →  RJ-14-2015-0043210
        GJ0120210012345  →  GJ-01-2021-0012345
    """
    if not text:
        return None

    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())

    # Standard Sarathi DL: 2-letter State code + 2-digit RTO + 4-digit Year + 7-digit Serial
    m = re.fullmatch(r"([A-Z]{2})(\d{2})(\d{4})(\d{7})", cleaned)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}"

    # Accept any 2-letter state prefix followed by numbers/alphanumeric (minimum 10 chars)
    if len(cleaned) >= 10 and re.match(r"^[A-Z]{2}\d", cleaned):
        return cleaned

    return None


def normalize_rc_number(text: str) -> Optional[str]:
    """
    Normalize Indian Vehicle Registration (RC) number for ALL States & UTs.
    Formats:
        State Series: ``SS-RR-XX-NNNN``  (e.g. MH-02-CD-1234, DL-03-AB-5678)
        BH Series:    ``YY-BH-NNNN-XX``  (e.g. 22-BH-1234-AB)

    Accepts with or without separators.
    """
    if not text:
        return None

    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())

    # 1. BH Series (Bharat Series): YY + BH + 4 digits + 1-2 letters
    m_bh = re.fullmatch(r"(\d{2})(BH)(\d{4})([A-Z]{1,2})", cleaned)
    if m_bh:
        return f"{m_bh.group(1)}-{m_bh.group(2)}-{m_bh.group(3)}-{m_bh.group(4)}"

    # 2. Standard State Series: 2-letter State code + 1-2 digit RTO + 1-3 letters + 4 digits
    m_state = re.fullmatch(r"([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{4})", cleaned)
    if m_state:
        rto = f"{int(m_state.group(2)):02d}"
        return f"{m_state.group(1)}-{rto}-{m_state.group(3)}-{m_state.group(4)}"

    # Looser match — 2-letter state code followed by digits/letters
    if len(cleaned) >= 8 and re.match(r"^[A-Z]{2}\d", cleaned):
        return cleaned

    return None
