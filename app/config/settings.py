"""
Application Settings & Environment Configuration
================================================
Centralized configuration manager that loads environment variables from .env
with fallback default values and type validation.
"""

import os
from pathlib import Path
from typing import Set, Tuple
from dotenv import load_dotenv

# Base workspace directory (Driver_Verification root)
ROOT_DIR = Path(__file__).resolve().parents[2]

# Explicitly load .env from project root
ENV_PATH = ROOT_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "t", "on")


def _get_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default


def _get_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


def _get_str(key: str, default: str) -> str:
    return os.getenv(key, default).strip()


def _get_path(key: str, default_relative: str) -> Path:
    val = os.getenv(key, default_relative).strip()
    p = Path(val)
    if p.is_absolute():
        return p
    return ROOT_DIR / p


def _get_tuple_int(key: str, default: Tuple[int, int]) -> Tuple[int, int]:
    val = os.getenv(key)
    if not val:
        return default
    try:
        parts = [int(p.strip()) for p in val.split(",")]
        if len(parts) == 2:
            return (parts[0], parts[1])
    except Exception:
        pass
    return default


class Settings:
    """Strongly-typed application settings."""

    # ── Root Directory ────────────────────────────────────────────────────────
    PROJECT_ROOT: Path = ROOT_DIR

    # ── OCR Engine Settings ───────────────────────────────────────────────────
    OCR_DET_MODEL_DIR: str = _get_str(
        "OCR_DET_MODEL_DIR", "models/det_server/ch_PP-OCRv4_det_server_infer"
    )
    OCR_REC_MODEL_DIR: str = _get_str(
        "OCR_REC_MODEL_DIR", "models/rec_server/en_PP-OCRv4_rec_server_infer"
    )
    OCR_CLS_MODEL_DIR: str = _get_str(
        "OCR_CLS_MODEL_DIR", "models/cls/ch_ppocr_mobile_v2.0_cls_infer"
    )
    OCR_MIN_CONFIDENCE: float = _get_float("OCR_MIN_CONFIDENCE", 0.70)
    OCR_REC_IMAGE_SHAPE: str = _get_str("OCR_REC_IMAGE_SHAPE", "3,64,320")
    OCR_USE_GPU: bool = _get_bool("OCR_USE_GPU", True)
    OCR_USE_ANGLE_CLS: bool = _get_bool("OCR_USE_ANGLE_CLS", True)
    OCR_LANG: str = _get_str("OCR_LANG", "en")
    OCR_SHOW_LOG: bool = _get_bool("OCR_SHOW_LOG", False)

    # ── Image Preprocessor & Quality Thresholds ───────────────────────────────
    PREPROCESSOR_BLUR_THRESHOLD: float = _get_float("PREPROCESSOR_BLUR_THRESHOLD", 80.0)
    PREPROCESSOR_DARK_THRESHOLD: float = _get_float("PREPROCESSOR_DARK_THRESHOLD", 55.0)
    PREPROCESSOR_BRIGHT_THRESHOLD: float = _get_float("PREPROCESSOR_BRIGHT_THRESHOLD", 215.0)
    PREPROCESSOR_GLARE_THRESHOLD_PERCENT: float = _get_float(
        "PREPROCESSOR_GLARE_THRESHOLD_PERCENT", 12.0
    )
    PREPROCESSOR_GAMMA: float = _get_float("PREPROCESSOR_GAMMA", 1.6)
    PREPROCESSOR_CLAHE_CLIP_LIMIT: float = _get_float("PREPROCESSOR_CLAHE_CLIP_LIMIT", 2.0)
    PREPROCESSOR_CLAHE_TILE_GRID_SIZE: Tuple[int, int] = _get_tuple_int(
        "PREPROCESSOR_CLAHE_TILE_GRID_SIZE", (8, 8)
    )

    SUPPORTED_IMAGE_EXTENSIONS: Set[str] = {
        ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"
    }

    # ── Identity Cross-Validation Thresholds ──────────────────────────────────
    CROSS_VAL_NAME_MATCH_THRESHOLD: float = _get_float("CROSS_VAL_NAME_MATCH_THRESHOLD", 60.0)
    CROSS_VAL_NAME_REVIEW_THRESHOLD: float = _get_float("CROSS_VAL_NAME_REVIEW_THRESHOLD", 50.0)

    # ── Document Extractor Settings ───────────────────────────────────────────
    RC_FUZZY_MATCH_THRESHOLD: float = _get_float("RC_FUZZY_MATCH_THRESHOLD", 85.0)
    MASK_AADHAAR_NUMBER: bool = _get_bool("MASK_AADHAAR_NUMBER", False)

    # ── Storage & Directory Paths ─────────────────────────────────────────────
    SAMPLE_DOCUMENTS_DIR: str = _get_str("SAMPLE_DOCUMENTS_DIR", "sample_documents")
    EXTRACTION_OUTPUT_DIR: str = _get_str("EXTRACTION_OUTPUT_DIR", "result/extr_result")
    VALIDATION_OUTPUT_DIR: str = _get_str("VALIDATION_OUTPUT_DIR", "result/vldt_result")

    # Config files paths
    RC_CONFIG_PATH: Path = ROOT_DIR / "app" / "config" / "rc_config.json"
    KNOWN_MANUFACTURERS_PATH: Path = ROOT_DIR / "app" / "config" / "known_manufacturers.json"

    def get_absolute_path(self, relative_or_absolute: str) -> Path:
        """Resolve a relative or absolute path against the project root."""
        p = Path(relative_or_absolute)
        if p.is_absolute():
            return p
        return self.PROJECT_ROOT / p


# Global singleton settings instance
settings = Settings()
