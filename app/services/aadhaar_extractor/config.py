"""
Aadhaar Extractor Configuration
================================
Domain configuration for Aadhaar Card parsing, blacklists, and privacy masking.
"""

import os
from typing import Set
from dotenv import load_dotenv

load_dotenv()


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "t", "on")


def _get_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


class AadhaarConfig:
    """Aadhaar Extraction Domain Settings."""

    MASK_AADHAAR_NUMBER: bool = _get_bool("AADHAAR_MASK_NUMBER", False)
    MIN_DOB_YEAR: int = _get_int("AADHAAR_MIN_DOB_YEAR", 1930)
    MAX_DOB_YEAR: int = _get_int("AADHAAR_MAX_DOB_YEAR", 2026)

    # Words that must NOT be recognized as a person's name
    NAME_BLACKLIST: Set[str] = {
        "government", "india", "aadhaar", "uidai", "address", "authentication",
        "proof", "citizenship", "birth", "help", "xml", "qr", "male", "female",
        "transgender", "download", "date", "dob", "year", "permanent", "resident",
        "unique", "identification", "authority", "enrolment", "enrollment",
        "village", "post", "district", "state", "pin", "pincode", "s/o", "d/o",
        "w/o", "c/o", "care", "of", "house", "near", "sector", "ward", "taluka",
        "tehsil", "nagar", "gujarat", "ahmedabad", "surat", "vadodara",
        "bharat", "sarkar", "mera", "meri", "pechan", "pehchan", "issued",
    }


# Service Singleton
aadhaar_config = AadhaarConfig()
