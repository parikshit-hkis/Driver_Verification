"""
Configuration for Aadhaar Extractor Microservice
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class AadhaarConfig:
    PORT: int = int(os.getenv("AADHAAR_PORT", "8002"))
    HOST: str = os.getenv("AADHAAR_HOST", "0.0.0.0")
    OCR_SERVICE_URL: str = os.getenv("OCR_SERVICE_URL", "http://127.0.0.1:8001")

    MASK_NUMBER: bool = os.getenv("AADHAAR_MASK_NUMBER", "false").lower() in ("true", "1", "yes")
    MIN_DOB_YEAR: int = int(os.getenv("AADHAAR_MIN_DOB_YEAR", "1930"))
    MAX_DOB_YEAR: int = int(os.getenv("AADHAAR_MAX_DOB_YEAR", "2026"))

    NAME_BLACKLIST: list = [
        "government", "india", "unique", "identification", "authority",
        "male", "female", "transgender", "dob", "birth", "year", "date",
        "aadhaar", "help", "enrollment", "download", "masked", "qr", "mera",
        "pehchan", "meraaadhaar", "uidai", "vid", "address", "father",
        "husband", "s/o", "w/o", "d/o",
    ]


aadhaar_config = AadhaarConfig()
