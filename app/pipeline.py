"""
Document Extraction Pipeline
=============================
Single entry point for end-to-end text extraction from any document image.

Usage:
    pipeline = Pipeline()

    # Auto-detect document type
    result = pipeline.extract("path/to/image.jpg")

    # Force document type
    from app.services.doc_type_detector import DocumentType
    result = pipeline.extract("path/to/image.jpg", doc_type=DocumentType.AADHAAR)

    # From numpy array
    import cv2
    img = cv2.imread("path/to/image.jpg")
    result = pipeline.extract(img)

    # From base64
    result = pipeline.extract("data:image/jpeg;base64,/9j/4AAQSkZJR...")

    # Print results
    result.display()

Steps:
    1. Preprocess  — fix orientation, enhance quality
    2. OCR         — extract text + bounding boxes via PaddleOCR
    3. Detect type — classify AADHAAR / PAN / DRIVING_LICENCE / RC
    4. Extract     — parse fields using label-proximity + regex
    5. Normalize   — standardize names, dates, numbers
"""

from dataclasses import dataclass
from typing import Optional, Union

from app.models.ocr_models import ImageQualityReport, OCRResult
from app.ocr.preprocessor import ImagePreprocessor
from app.ocr.paddle_ocr import PaddleOCRService
from app.services.doc_type_detector import DocTypeDetector, DocumentType
from app.services.aadhaar_extractor.extractor import AadhaarExtractor
from app.services.aadhaar_extractor.models import AadhaarData
from app.services.pan_extractor.extractor import PanExtractor
from app.services.pan_extractor.models import PanData
from app.services.driving_license_extractor.extractor import DrivingLicenceExtractor
from app.services.driving_license_extractor.models import DrivingLicenceData
from app.services.rc_extractor.extractor import RCExtractor
from app.services.rc_extractor.models import RCData


DocumentData = Union[AadhaarData, PanData, DrivingLicenceData, RCData, None]


@dataclass
class ExtractionResult:
    document_type: DocumentType
    data: DocumentData
    quality_report: ImageQualityReport
    ocr_result: OCRResult

    def display(self) -> str:
        """Pretty-print the full extraction result."""
        sep = "=" * 55
        thin_sep = "-" * 55

        lines = [
            "",
            sep,
            f"  DOCUMENT TYPE : {self.document_type.value}",
            sep,
        ]

        # Quality report
        lines.append("\nImage Quality:")
        lines.append(self.quality_report.summary())

        # Extracted fields
        lines.append(f"\n{thin_sep}")
        lines.append("  Extracted Fields:")
        lines.append(thin_sep)

        if self.data is not None:
            lines.append(self.data.display())
        else:
            lines.append("  [No extractor available for this document type]")

        lines.append(sep)
        lines.append("")

        return "\n".join(lines)


class Pipeline:
    """
    End-to-end document text extraction pipeline.

    Stateful — holds pre-loaded OCR model (slow first load, fast subsequent)'.
    Instantiate once and reuse.
    """

    def __init__(self):
        self._preprocessor = ImagePreprocessor()
        self._ocr = PaddleOCRService()
        self._detector = DocTypeDetector()
        self._extractors = {
            DocumentType.AADHAAR: AadhaarExtractor(),
            DocumentType.PAN: PanExtractor(),
            DocumentType.DRIVING_LICENCE: DrivingLicenceExtractor(),
            DocumentType.RC: RCExtractor(),
        }

    def extract(self,image_input,*,doc_type: Optional[DocumentType] = None,fix_orientation: bool = True,enhance: bool = True,) -> ExtractionResult:
        """
        Run the full extraction pipeline on an image.

        Args:
            image_input:     Any supported format (path, bytes, base64, URL,
                             numpy array, PIL Image).
            doc_type:        If provided, skip auto-detection and use this type.
            fix_orientation: Whether to correct image rotation/skew.
            enhance:         Whether to apply CLAHE / brightness enhancement.

        Returns:
            ExtractionResult with all extracted fields and quality report.
        """
        # Step 1: Preprocess
        img_array, quality_report = self._preprocessor.preprocess(
            image_input,
            fix_orientation=fix_orientation,
            enhance=enhance,
        )

        # Step 2: OCR
        ocr_result = self._ocr.extract(img_array)

        # Step 3: Document type detection
        if doc_type is None:
            doc_type = self._detector.detect(ocr_result.texts)

        # Step 4 & 5: Extract + normalize
        extractor = self._extractors.get(doc_type)
        data: DocumentData = extractor.extract(ocr_result) if extractor else None

        return ExtractionResult(
            document_type=doc_type,
            data=data,
            quality_report=quality_report,
            ocr_result=ocr_result,
        )
