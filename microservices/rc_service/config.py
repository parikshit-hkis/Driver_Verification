"""
Configuration for RC Extractor Microservice
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Set, Any
from dotenv import load_dotenv

logger = logging.getLogger("rc_service.config")

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class RCConfigurationError(Exception):
    """Raised when RC service configuration is missing or invalid."""
    pass


class RCConfig:
    PORT: int = int(os.getenv("RC_PORT", "8005"))
    HOST: str = os.getenv("RC_HOST", "0.0.0.0")
    OCR_SERVICE_URL: str = os.getenv("OCR_SERVICE_URL", "http://127.0.0.1:8001")

    FUZZY_MATCH_THRESHOLD: float = float(os.getenv("RC_FUZZY_MATCH_THRESHOLD", "85.0"))

    CONFIG_DIR: Path = Path(__file__).resolve().parent / "config_data"
    RC_CONFIG_PATH: Path = CONFIG_DIR / "rc_config.json"

    # Regex patterns
    RC_REGEX: re.Pattern = re.compile(
        r"\b([A-Z]{2}[\s\-]?\d{1,2}[\s\-]?[A-Z]{1,3}[\s\-]?\d{4}|\d{2}[\s\-]?BH[\s\-]?\d{4}[\s\-]?[A-Z]{1,2})\b",
        re.IGNORECASE,
    )

    VALIDITY_SPAN_REGEX: re.Pattern = re.compile(
        r"valid\s+from\s+([0-9A-Z\-\./]+)\s+to\s+([0-9A-Z\-\./]+)",
        re.IGNORECASE,
    )

    RELATION_PATTERNS: List[re.Pattern] = [
        re.compile(r"\bS[/\s\.]*[0O]\b[:\.\s]?", re.IGNORECASE),
        re.compile(r"\bD[/\s\.]*[0O]\b[:\.\s]?", re.IGNORECASE),
        re.compile(r"\bW[/\s\.]*[0O]\b[:\.\s]?", re.IGNORECASE),
        re.compile(r"\bC[/\s\.]*[0O]\b[:\.\s]?", re.IGNORECASE),
        re.compile(r"\bSON\s+OF\b[:\.\s]?", re.IGNORECASE),
        re.compile(r"\bDAUGHTER\s+OF\b[:\.\s]?", re.IGNORECASE),
        re.compile(r"\bWIFE\s+OF\b[:\.\s]?", re.IGNORECASE),
        re.compile(r"\bCARE\s+OF\b[:\.\s]?", re.IGNORECASE),
        re.compile(r"\bSON/DAUGHTER/WIFE\s+OF\b[:\.\s]?", re.IGNORECASE),
        re.compile(r"\bSON/WIFE/DAUGHTER\s+OF\b[:\.\s]?", re.IGNORECASE),
    ]

    def __init__(self):
        self.vehicle_classes: Set[str] = set()
        self.state_codes: Set[str] = set()
        self.address_blacklist: Set[str] = set()
        self.canonical_labels: List[str] = []
        self.spatial_params: Dict[str, Any] = {}
        self.scoring_weights: Dict[str, float] = {}
        self._load_and_validate()

    def _load_and_validate(self) -> None:
        """Load configuration files and validate required structures."""
        # 1. Validate RC Config Path
        if not self.RC_CONFIG_PATH.exists():
            raise RCConfigurationError(f"Mandatory RC config file missing: {self.RC_CONFIG_PATH}")

        try:
            with open(self.RC_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise RCConfigurationError(f"Failed to parse JSON from {self.RC_CONFIG_PATH}: {e}")

        # Validate mandatory keys
        required_keys = [
            "vehicle_classes",
            "state_codes",
            "address_blacklist",
            "canonical_labels",
            "spatial_parameters",
            "scoring_weights",
        ]
        for k in required_keys:
            if k not in data:
                raise RCConfigurationError(f"Missing mandatory key '{k}' in {self.RC_CONFIG_PATH}")

        self.vehicle_classes = set(data["vehicle_classes"])
        if not self.vehicle_classes:
            raise RCConfigurationError("vehicle_classes in rc_config.json cannot be empty")

        self.state_codes = set(data["state_codes"])
        if not self.state_codes:
            raise RCConfigurationError("state_codes in rc_config.json cannot be empty")

        self.address_blacklist = set(w.upper() for w in data["address_blacklist"])
        self.canonical_labels = [lbl.upper() for lbl in data["canonical_labels"]]
        self.spatial_params = data["spatial_parameters"]
        self.scoring_weights = data["scoring_weights"]

        # 2. Validate numeric thresholds
        if not (0.0 <= self.FUZZY_MATCH_THRESHOLD <= 100.0):
            raise RCConfigurationError(f"Invalid FUZZY_MATCH_THRESHOLD: {self.FUZZY_MATCH_THRESHOLD}")

        # logger.info(
        #     f"RCConfig initialized successfully: {len(self.vehicle_classes)} vehicle classes, "
        #     f"{len(self.state_codes)} state codes."
        # )

    def validate_config(self) -> bool:
        """Explicit validation method callable on service startup."""
        self._load_and_validate()
        return True


rc_config = RCConfig()
