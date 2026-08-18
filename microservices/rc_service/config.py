"""
Configuration for RC Extractor Microservice
"""

import os
import re
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class RCConfig:
    PORT: int = int(os.getenv("RC_PORT", "8005"))
    HOST: str = os.getenv("RC_HOST", "0.0.0.0")
    OCR_SERVICE_URL: str = os.getenv("OCR_SERVICE_URL", "http://127.0.0.1:8001")

    FUZZY_MATCH_THRESHOLD: float = float(os.getenv("RC_FUZZY_MATCH_THRESHOLD", "85.0"))

    CONFIG_DIR: Path = Path(__file__).resolve().parent / "config_data"
    RC_CONFIG_PATH: Path = CONFIG_DIR / "rc_config.json"
    KNOWN_MANUFACTURERS_PATH: Path = CONFIG_DIR / "known_manufacturers.json"

    RC_REGEX = re.compile(
        r"\b([A-Z]{2}[\s\-]?\d{1,2}[\s\-]?[A-Z]{1,3}[\s\-]?\d{4}|\d{2}[\s\-]?BH[\s\-]?\d{4}[\s\-]?[A-Z]{1,2})\b",
        re.IGNORECASE,
    )


rc_config = RCConfig()
