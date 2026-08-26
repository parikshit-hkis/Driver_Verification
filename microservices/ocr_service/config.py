"""
Configuration for OCR Microservice
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class OCRConfig:
    PORT: int = int(os.getenv("OCR_PORT", "8001"))
    HOST: str = os.getenv("OCR_HOST", "0.0.0.0")

    DET_MODEL_DIR: str = os.getenv(
        "OCR_DET_MODEL_DIR", str(ROOT_DIR / "models/det_server/ch_PP-OCRv4_det_server_infer")
    )
    REC_MODEL_DIR: str = os.getenv(
        "OCR_REC_MODEL_DIR", str(ROOT_DIR / "models/rec_server/en_PP-OCRv4_rec_server_infer")
    )
    CLS_MODEL_DIR: str = os.getenv(
        "OCR_CLS_MODEL_DIR", str(ROOT_DIR / "models/cls/ch_ppocr_mobile_v2.0_cls_infer")
    )
    DET_MODEL_DIR: str = os.getenv("OCR_DET_MODEL_DIR") or None
    REC_MODEL_DIR: str = os.getenv("OCR_REC_MODEL_DIR") or None
    CLS_MODEL_DIR: str = os.getenv("OCR_CLS_MODEL_DIR") or None

    MIN_CONFIDENCE: float = float(os.getenv("OCR_MIN_CONFIDENCE", "0.70"))
    REC_IMAGE_SHAPE: str = os.getenv("OCR_REC_IMAGE_SHAPE", "3,64,320")
    USE_GPU: bool = os.getenv("OCR_USE_GPU", "true").lower() in ("true", "1", "yes")
    USE_ANGLE_CLS: bool = os.getenv("OCR_USE_ANGLE_CLS", "true").lower() in ("true", "1", "yes")
    LANG: str = os.getenv("OCR_LANG", "en")
    SHOW_LOG: bool = os.getenv("OCR_SHOW_LOG", "false").lower() in ("true", "1", "yes")

    BLUR_THRESHOLD: float = float(os.getenv("PREPROCESSOR_BLUR_THRESHOLD", "80.0"))
    DARK_THRESHOLD: float = float(os.getenv("PREPROCESSOR_DARK_THRESHOLD", "55.0"))
    BRIGHT_THRESHOLD: float = float(os.getenv("PREPROCESSOR_BRIGHT_THRESHOLD", "215.0"))
    GLARE_THRESHOLD_PERCENT: float = float(os.getenv("PREPROCESSOR_GLARE_THRESHOLD_PERCENT", "12.0"))
    GAMMA: float = float(os.getenv("PREPROCESSOR_GAMMA", "1.6"))
    CLAHE_CLIP_LIMIT: float = float(os.getenv("PREPROCESSOR_CLAHE_CLIP_LIMIT", "2.0"))


ocr_config = OCRConfig()
