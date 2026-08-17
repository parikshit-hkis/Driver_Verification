"""
Document Extraction Pipeline
=============================
Unified entry point for document text extraction:
  1. Driver-by-Driver Extraction (extract_driver / extract_all_drivers)
  2. Document Extraction (extract_document — handles front + back merging)
  3. Single Image Extraction (extract — for backward compatibility)

Processing Order per Driver:
  Aadhaar → Driving Licence → PAN → RC Book
"""

from dataclasses import dataclass
from typing import Optional, Union, List, Dict

from app.config.settings import settings
from app.models.ocr_models import ImageQualityReport, OCRResult, OCRText
from app.models.driver_models import DocumentExtractionResult, DriverVerificationResult, DocumentData
from app.ocr.preprocessor import ImagePreprocessor
# from app.image_straightener import ImageStraightener
from app.ocr.paddle_ocr import PaddleOCRService
from app.services.doc_type_detector import DocTypeDetector, DocumentType
from app.services.directory_scanner import DirectoryScanner, DriverFolderSpec, DocumentFilesSpec, MANDATORY_DOC_ORDER
from app.services.aadhaar_extractor.extractor import AadhaarExtractor
from app.services.pan_extractor.extractor import PanExtractor
from app.services.driving_license_extractor.extractor import DrivingLicenceExtractor
from app.services.rc_extractor.extractor import RCExtractor


@dataclass
class ExtractionResult:
    """Legacy result wrapper for single image extraction."""
    document_type: DocumentType
    data: DocumentData
    quality_report: ImageQualityReport
    ocr_result: OCRResult

    def display(self) -> str:
        sep = "=" * 55
        thin_sep = "-" * 55
        lines = [
            "",
            sep,
            f"  DOCUMENT TYPE : {self.document_type.value}",
            sep,
            "\nImage Quality:",
            self.quality_report.summary(),
            f"\n{thin_sep}",
            "  Extracted Fields:",
            thin_sep,
        ]
        if self.data is not None:
            lines.append(self.data.display())
        else:
            lines.append("  [No extractor available for this document type]")
        lines.append(sep)
        lines.append("")
        return "\n".join(lines)


class Pipeline:
    """
    Stateful document verification pipeline orchestrator.
    Pre-loads OCR engine and extractors for reuse.
    """

    def __init__(self):
        self._preprocessor = ImagePreprocessor()
        self._ocr = PaddleOCRService()
        # self._straightener = ImageStraightener(ocr_service=self._ocr)
        self._detector = DocTypeDetector()
        self._scanner = DirectoryScanner()
        self._extractors = {
            DocumentType.AADHAAR: AadhaarExtractor(),
            DocumentType.PAN: PanExtractor(),
            DocumentType.DRIVING_LICENCE: DrivingLicenceExtractor(),
            DocumentType.RC: RCExtractor(),
        }

    # ── Driver-by-Driver Orchestration ────────────────────────────────────────

    def extract_all_drivers(
        self,
        base_dir: Optional[str] = None,
        max_workers: int = 1,
        show_progress: bool = True,
    ) -> List[DriverVerificationResult]:
        """
        Scan base directory and process all discovered drivers driver-by-driver.
        Supports parallel multi-threaded extraction when max_workers > 1.
        """
        target_dir = base_dir or settings.SAMPLE_DOCUMENTS_DIR
        driver_specs = self._scanner.scan_all_drivers(target_dir)
        total = len(driver_specs)
        if total == 0:
            return []

        results: List[DriverVerificationResult] = []

        if max_workers <= 1 or total == 1:
            for idx, spec in enumerate(driver_specs, 1):
                if show_progress:
                    print(f"  [{idx:03d}/{total:03d}] Processing Driver: {spec.driver_id}...", flush=True)
                res = self.extract_driver(spec)
                results.append(res)
        else:
            import concurrent.futures
            completed = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_spec = {
                    executor.submit(self.extract_driver, spec): spec
                    for spec in driver_specs
                }
                for future in concurrent.futures.as_completed(future_to_spec):
                    spec = future_to_spec[future]
                    completed += 1
                    try:
                        res = future.result()
                        results.append(res)
                        if show_progress:
                            print(f"  [{completed:03d}/{total:03d}] Finished Driver: {spec.driver_id}", flush=True)
                    except Exception as exc:
                        print(f"  [{completed:03d}/{total:03d}] [ERROR] Driver {spec.driver_id} failed: {exc}", flush=True)

        return results

    def extract_driver(self, driver_input: Union[str, DriverFolderSpec], output_dir: Optional[str] = None) -> DriverVerificationResult:
        """
        Process all documents for a single driver in strict order:
        Aadhaar → Driving Licence → PAN → RC Book.
        Finishes the entire driver before returning.
        """
        if isinstance(driver_input, str):
            spec = self._scanner.scan_driver_folder(driver_input)
        else:
            spec = driver_input

        driver_result = DriverVerificationResult(driver_id=spec.driver_id)

        for doc_type in MANDATORY_DOC_ORDER:
            doc_spec = spec.get_document_spec(doc_type)
            doc_res = self.extract_document(doc_spec)

            if doc_type == DocumentType.AADHAAR:
                driver_result.aadhaar_result = doc_res
            elif doc_type == DocumentType.DRIVING_LICENCE:
                driver_result.licence_result = doc_res
            elif doc_type == DocumentType.PAN:
                driver_result.pan_result = doc_res
            elif doc_type == DocumentType.RC:
                driver_result.rc_result = doc_res

        target_output_dir = output_dir or settings.EXTRACTION_OUTPUT_DIR
        driver_result.save_json(target_output_dir)
        return driver_result

    def extract_document(self, doc_spec: DocumentFilesSpec) -> DocumentExtractionResult:
        """
        Process front and back images for a document, merge OCR results,
        run domain extractor, and return DocumentExtractionResult.
        """
        if doc_spec.is_missing:
            return DocumentExtractionResult(
                document_type=doc_spec.doc_type,
                status="MISSING",
                warning="Document folder or images not found",
            )

        extractor = self._extractors.get(doc_spec.doc_type)
        if not extractor:
            return DocumentExtractionResult(
                document_type=doc_spec.doc_type,
                status="FAILED",
                warning=f"No extractor found for {doc_spec.doc_type}",
            )

        ocr_front: Optional[OCRResult] = None
        ocr_back: Optional[OCRResult] = None
        quality_front: Optional[ImageQualityReport] = None
        quality_back: Optional[ImageQualityReport] = None
        warnings = []

        # 1. Process Front Image
        if doc_spec.front_path:
            try:
                img_front, quality_front = self._preprocessor.preprocess(doc_spec.front_path)
                # img_front = self._straightener.straighten(img_front)
                ocr_front = self._ocr.extract(img_front)
            except Exception as e:
                warnings.append(f"Front image error: {e}")

        # 2. Process Back Image
        if doc_spec.back_path:
            try:
                img_back, quality_back = self._preprocessor.preprocess(doc_spec.back_path)
                # img_back = self._straightener.straighten(img_back)
                ocr_back = self._ocr.extract(img_back)
            except Exception as e:
                warnings.append(f"Back image error: {e}")

        if not ocr_front and not ocr_back:
            return DocumentExtractionResult(
                document_type=doc_spec.doc_type,
                status="FAILED",
                warning="; ".join(warnings) if warnings else "Failed to process images",
            )

        # 3. Combine OCR Results & Extract Fields
        if doc_spec.doc_type == DocumentType.RC and hasattr(extractor, "extract_rc"):
            data = extractor.extract_rc(ocr_front, ocr_back)
        elif doc_spec.doc_type == DocumentType.DRIVING_LICENCE and hasattr(extractor, "extract_dl"):
            data = extractor.extract_dl(ocr_front, ocr_back)
        elif doc_spec.doc_type == DocumentType.AADHAAR and hasattr(extractor, "extract_aadhaar"):
            data = extractor.extract_aadhaar(ocr_front, ocr_back)
        elif doc_spec.doc_type == DocumentType.PAN and hasattr(extractor, "extract_pan"):
            data = extractor.extract_pan(ocr_front, ocr_back)
        else:
            combined_ocr = self._merge_ocr_results(ocr_front, ocr_back)
            data = extractor.extract(combined_ocr)
            data_front = extractor.extract(ocr_front) if ocr_front else None
            data_back = extractor.extract(ocr_back) if ocr_back else None
            data = self._merge_data(data, data_front, data_back)

        # 4. Apply image quality-based diagnostics for missing fields
        if data is not None:
            self._apply_quality_diagnostics(data, quality_front, quality_back)

        # Determine status
        status = "EXTRACTED"
        if not doc_spec.front_path or not doc_spec.back_path:
            warnings.append("Partial document (missing front or back image)")
            status = "PARTIAL"

        return DocumentExtractionResult(
            document_type=doc_spec.doc_type,
            data=data,
            front_quality=quality_front,
            back_quality=quality_back,
            front_ocr=ocr_front,
            back_ocr=ocr_back,
            status=status,
            warning="; ".join(warnings) if warnings else None,
        )

    # ── Legacy Single-Image Extraction ─────────────────────────────────────────

    def extract(self,image_input,*,doc_type: Optional[DocumentType] = None,fix_orientation: bool = True,enhance: bool = True,) -> ExtractionResult:
        """Process a single image (legacy entry point)."""
        img_array, quality_report = self._preprocessor.preprocess(image_input,fix_orientation=fix_orientation,enhance=enhance,)
        # img_array = self._straightener.straighten(img_array)
        ocr_result = self._ocr.extract(img_array)

        if doc_type is None:
            doc_type = self._detector.detect(ocr_result.texts)

        extractor = self._extractors.get(doc_type)
        data: DocumentData = extractor.extract(ocr_result) if extractor else None

        return ExtractionResult(
            document_type=doc_type,
            data=data,
            quality_report=quality_report,
            ocr_result=ocr_result,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _merge_ocr_results(ocr1: Optional[OCRResult], ocr2: Optional[OCRResult]) -> OCRResult:
        """Combine front and back OCR results into a unified OCRResult."""
        if not ocr1 and not ocr2:
            return OCRResult(full_text="", texts=[])
        if not ocr1:
            return ocr2
        if not ocr2:
            return ocr1

        texts: List[OCRText] = list(ocr1.texts) + list(ocr2.texts)
        full_text = ocr1.full_text + "\n" + ocr2.full_text
        return OCRResult(full_text=full_text, texts=texts)

    @staticmethod
    def _merge_data(primary: DocumentData, d1: DocumentData, d2: DocumentData) -> DocumentData:
        """Fill in missing None fields in primary data using fallback extractions."""
        if primary is None:
            primary = d1 or d2
        if primary is None:
            return None

        _SKIP_FIELDS = {"field_diagnostics", "confidence_scores", "overall_confidence"}

        for source in [d1, d2]:
            if source is None:
                continue
            for field_name in primary.__fields__:
                if field_name in _SKIP_FIELDS:
                    continue
                val_prim = getattr(primary, field_name, None)
                val_sec = getattr(source, field_name, None)

                # Update if primary field is None or empty list/str and secondary has value
                if (val_prim is None or val_prim == "" or val_prim == []) and (val_sec is not None and val_sec != "" and val_sec != []):
                    setattr(primary, field_name, val_sec)

        return primary

    @staticmethod
    def _apply_quality_diagnostics(data: DocumentData, quality_front: Optional[ImageQualityReport], quality_back: Optional[ImageQualityReport]) -> None:
        """Enrich field_diagnostics with image quality information for missing fields."""
        if data is None or not hasattr(data, 'field_diagnostics'):
            return

        # Build quality warning summary
        quality_issues = []
        for label, report in [("Front", quality_front), ("Back", quality_back)]:
            if report is None:
                continue
            if report.is_blurry:
                quality_issues.append(f"{label} image is blurry (blur score: {report.blur_score:.1f})")
            if report.is_too_dark:
                quality_issues.append(f"{label} image is too dark (brightness: {report.brightness:.1f})")
            if report.is_too_bright:
                quality_issues.append(f"{label} image is overexposed (brightness: {report.brightness:.1f})")
            if report.has_glare:
                quality_issues.append(f"{label} image has glare ({report.glare_percentage:.1f}%)")

        if not quality_issues:
            return

        quality_msg = "; ".join(quality_issues)

        # For each field that is still None and already has a diagnostic, prepend quality info
        for field_name, existing_reason in list(data.field_diagnostics.items()):
            val = getattr(data, field_name, None)
            if val is None or val == "" or val == []:
                data.field_diagnostics[field_name] = f"{quality_msg}. {existing_reason}"
