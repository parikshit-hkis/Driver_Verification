from abc import ABC, abstractmethod
from typing import Any
from src.schemas.document_schemas import OCRResult

class BaseExtractor(ABC):
    """Abstract base class for all document extractors."""

    @abstractmethod
    def extract(self, ocr_result: OCRResult) -> Any:
        """Extracts structured document model from OCRResult."""
        pass
