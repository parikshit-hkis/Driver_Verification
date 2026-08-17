"""
Shared Application Dependencies & Service Singletons
=====================================================
Provides lazily initialized singletons per worker process so that
only ONE model instance is loaded into GPU VRAM per worker process.
"""

from typing import Optional
from app.pipeline import Pipeline
from app.ocr.preprocessor import ImagePreprocessor
from app.ocr.paddle_ocr import PaddleOCRService
from app.services.identity_cross_validator.cross_validator import IdentityCrossValidator

_pipeline_instance: Optional[Pipeline] = None
_preprocessor_instance: Optional[ImagePreprocessor] = None
_cross_validator_instance: Optional[IdentityCrossValidator] = None


def get_pipeline() -> Pipeline:
    """Return shared Pipeline instance (one per worker process)."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = Pipeline()
    return _pipeline_instance


def get_ocr_service() -> PaddleOCRService:
    """Return shared PaddleOCRService from the pipeline."""
    return get_pipeline()._ocr


def get_preprocessor() -> ImagePreprocessor:
    """Return shared ImagePreprocessor instance."""
    global _preprocessor_instance
    if _preprocessor_instance is None:
        _preprocessor_instance = ImagePreprocessor()
    return _preprocessor_instance


def get_cross_validator() -> IdentityCrossValidator:
    """Return shared IdentityCrossValidator instance."""
    global _cross_validator_instance
    if _cross_validator_instance is None:
        _cross_validator_instance = IdentityCrossValidator()
    return _cross_validator_instance
