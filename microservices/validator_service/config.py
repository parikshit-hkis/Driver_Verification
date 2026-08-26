"""
Configuration for Identity Cross-Validator Microservice
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Any
from dotenv import load_dotenv

logger = logging.getLogger("validator_service.config")

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class CrossValidatorConfig:
    PORT: int = int(os.getenv("VALIDATOR_PORT", "8006"))
    HOST: str = os.getenv("VALIDATOR_HOST", "0.0.0.0")

    CONFIG_DIR: Path = Path(__file__).resolve().parent / "config_data"
    CONFIG_JSON_PATH: Path = CONFIG_DIR / "validator_config.json"

    NAME_MATCH_THRESHOLD: float = float(os.getenv("CROSS_VAL_NAME_MATCH_THRESHOLD", "60.0"))
    NAME_REVIEW_THRESHOLD: float = float(os.getenv("CROSS_VAL_NAME_REVIEW_THRESHOLD", "50.0"))

    CANONICAL_VEHICLE_CLASSES: Dict[str, Set[str]] = {}
    VEHICLE_CATEGORY_ALIASES: Dict[str, List[str]] = {}
    VEHICLE_HEURISTIC_KEYWORDS: Dict[str, List[str]] = {}

    def __init__(self):
        self._load_config_json()

    def _load_config_json(self):
        if not self.CONFIG_JSON_PATH.exists():
            logger.warning(f"Validator config file not found at {self.CONFIG_JSON_PATH}, using defaults")
            return

        try:
            with open(self.CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "name_match_threshold" in data and not os.getenv("CROSS_VAL_NAME_MATCH_THRESHOLD"):
                self.NAME_MATCH_THRESHOLD = float(data["name_match_threshold"])
            if "name_review_threshold" in data and not os.getenv("CROSS_VAL_NAME_REVIEW_THRESHOLD"):
                self.NAME_REVIEW_THRESHOLD = float(data["name_review_threshold"])

            vc_data = data.get("vehicle_categories", {})
            self.VEHICLE_CATEGORY_ALIASES = vc_data.get("aliases", {})
            self.VEHICLE_HEURISTIC_KEYWORDS = vc_data.get("heuristic_keywords", {})

            raw_canonical = vc_data.get("canonical_classes", {})
            self.CANONICAL_VEHICLE_CLASSES = {
                cat: set(classes) for cat, classes in raw_canonical.items()
            }
            logger.info(f"Loaded {len(self.CANONICAL_VEHICLE_CLASSES)} vehicle category definitions from {self.CONFIG_JSON_PATH}")
        except Exception as e:
            logger.error(f"Error loading validator config from {self.CONFIG_JSON_PATH}: {e}", exc_info=True)


validator_config = CrossValidatorConfig()

