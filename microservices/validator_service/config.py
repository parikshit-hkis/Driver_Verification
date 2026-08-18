"""
Configuration for Identity Cross-Validator Microservice
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class CrossValidatorConfig:
    PORT: int = int(os.getenv("VALIDATOR_PORT", "8006"))
    HOST: str = os.getenv("VALIDATOR_HOST", "0.0.0.0")

    NAME_MATCH_THRESHOLD: float = float(os.getenv("CROSS_VAL_NAME_MATCH_THRESHOLD", "60.0"))
    NAME_REVIEW_THRESHOLD: float = float(os.getenv("CROSS_VAL_NAME_REVIEW_THRESHOLD", "50.0"))


validator_config = CrossValidatorConfig()
