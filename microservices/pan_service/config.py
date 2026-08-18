"""
Configuration for PAN Extractor Microservice
"""

import os
import re
from typing import Set, List
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class PanConfig:
    PORT: int = int(os.getenv("PAN_PORT", "8004"))
    HOST: str = os.getenv("PAN_HOST", "0.0.0.0")
    OCR_SERVICE_URL: str = os.getenv("OCR_SERVICE_URL", "http://127.0.0.1:8001")

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


pan_config = PanConfig()
