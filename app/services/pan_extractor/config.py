"""
PAN Extractor Configuration
============================
Domain configuration for PAN card parsing, regex patterns, and blacklist words.
"""

import re
from typing import Set, List


class PanConfig:
    """PAN Extraction Domain Settings."""

    PAN_REGEX = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b")

    NAME_KEYWORDS: List[str] = ["Name", "NAME"]
    FATHER_KEYWORDS: List[str] = [
        "Father's Name", "Father Name", "Father", "FATHER'S NAME", "FATHER NAME", "FATHER"
    ]
    DOB_KEYWORDS: List[str] = [
        "Date of Birth", "DOB", "D.O.B", "Birth", "DATE OF BIRTH"
    ]

    NAME_BLACKLIST: Set[str] = {
        "income", "tax", "department", "government", "india", "permanent",
        "account", "number", "pan", "name", "father", "birth", "date",
        "signature",
    }


# Service Singleton
pan_config = PanConfig()
