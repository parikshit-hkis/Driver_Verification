"""
Identity Cross-Validator Configuration
======================================
Domain configuration for fuzzy matching thresholds and validation output paths.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _get_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default


def _get_str(key: str, default: str) -> str:
    return os.getenv(key, default).strip()


class CrossValidatorConfig:
    """Identity Cross-Validation Domain Settings."""

    NAME_MATCH_THRESHOLD: float = _get_float("CROSS_VAL_NAME_MATCH_THRESHOLD", 60.0)
    NAME_REVIEW_THRESHOLD: float = _get_float("CROSS_VAL_NAME_REVIEW_THRESHOLD", 50.0)

    DEFAULT_EXTRACTION_DIR: str = _get_str("EXTRACTION_OUTPUT_DIR", "result/extr_result")
    DEFAULT_VALIDATION_DIR: str = _get_str("VALIDATION_OUTPUT_DIR", "result/vldt_result")


# Service Singleton
cross_validator_config = CrossValidatorConfig()
