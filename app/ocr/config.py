"""
OCR & Image Preprocessing Configuration
========================================
Configuration parameters for PaddleOCR inference models and OpenCV preprocessing.
"""

import os
from pathlib import Path
from typing import Set, Tuple
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]


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


class OCRConfig:
    """PaddleOCR Model and Inference Parameters."""

    DET_MODEL_DIR: str = _get_str(
        "OCR_DET_MODEL_DIR", "models/det_server/ch_PP-OCRv4_det_server_infer"
    )
    REC_MODEL_DIR: str = _get_str(
        "OCR_REC_MODEL_DIR", "models/rec_server/en_PP-OCRv4_rec_server_infer"
    )
    CLS_MODEL_DIR: str = _get_str(
        "OCR_CLS_MODEL_DIR", "models/cls/ch_ppocr_mobile_v2.0_cls_infer"
    )
    MIN_CONFIDENCE: float = _get_float("OCR_MIN_CONFIDENCE", 0.70)
    REC_IMAGE_SHAPE: str = _get_str("OCR_REC_IMAGE_SHAPE", "3,64,320")
    USE_GPU: bool = _get_bool("OCR_USE_GPU", True)
    USE_ANGLE_CLS: bool = _get_bool("OCR_USE_ANGLE_CLS", True)
    LANG: str = _get_str("OCR_LANG", "en")
    SHOW_LOG: bool = _get_bool("OCR_SHOW_LOG", False)


class PreprocessorConfig:
    """Image Preprocessing Quality Thresholds and Enhancement Settings."""

    MAX_IMAGE_DIMENSION: int = _get_int("PREPROCESSOR_MAX_IMAGE_DIMENSION", 1920)
    BLUR_THRESHOLD: float = _get_float("PREPROCESSOR_BLUR_THRESHOLD", 80.0)
    DARK_THRESHOLD: float = _get_float("PREPROCESSOR_DARK_THRESHOLD", 55.0)
    BRIGHT_THRESHOLD: float = _get_float("PREPROCESSOR_BRIGHT_THRESHOLD", 215.0)
    GLARE_THRESHOLD_PERCENT: float = _get_float(
        "PREPROCESSOR_GLARE_THRESHOLD_PERCENT", 12.0
    )
    GAMMA: float = _get_float("PREPROCESSOR_GAMMA", 1.6)
    CLAHE_CLIP_LIMIT: float = _get_float("PREPROCESSOR_CLAHE_CLIP_LIMIT", 2.0)
    CLAHE_TILE_GRID_SIZE: Tuple[int, int] = _get_tuple_int(
        "PREPROCESSOR_CLAHE_TILE_GRID_SIZE", (8, 8)
    )

    SUPPORTED_EXTENSIONS: Set[str] = {
        ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"
    }


# Service Singletons
ocr_config = OCRConfig()
preprocessor_config = PreprocessorConfig()
