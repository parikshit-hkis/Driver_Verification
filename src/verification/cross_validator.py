import asyncio
import os
import time
import json
import re
from typing import Optional, List, Dict, Any

from src.core.config import settings
from src.core.logger import logger
from src.core.exceptions import VerificationServiceException
from src.utils.temp_manager import TempDirectoryContext
from src.clients.s3_download_client import S3DownloadClient
from src.clients.vision_ai_client import VisionAIClient, vision_ai_client
from src.extraction.zip_extractor import ZipExtractor
from src.extraction.document_classifier import DocumentClassifier
from src.extraction.extractors.aadhaar_extractor import AadhaarExtractor
from src.extraction.extractors.pan_extractor import PanExtractor
from src.extraction.extractors.licence_extractor import LicenceExtractor
from src.extraction.extractors.rc_extractor import RcExtractor
from src.verification.decision_engine import DecisionEngine, decision_engine
from src.schemas.request_schemas import DriverVerificationRequest, BatchDriverVerificationRequest
from src.schemas.response_schemas import (
    DriverVerificationResponse,
    BatchDriverVerificationResponse
)
from src.schemas.document_schemas import AadhaarData, PanData, LicenceData, RcData, OCRResult

class CrossValidator:
    """
    Coordinates the end-to-end document verification pipeline:
    1. Ingestion & Temp Isolation
    2. Secure ZIP Download & Password Extraction
    3. Google Cloud Vision OCR
    4. Document Classification & Field Parsing
    5. Cross-Verification Rules & Decision
    """
    def __init__(
        self,
        download_client: Optional[S3DownloadClient] = None,
        zip_extractor: Optional[ZipExtractor] = None,
        vision_client: Optional[VisionAIClient] = None,
        classifier: Optional[DocumentClassifier] = None,
        engine: Optional[DecisionEngine] = None
    ):
        self.download_client = download_client or S3DownloadClient()
        self.zip_extractor = zip_extractor or ZipExtractor()
        self.vision_client = vision_client or vision_ai_client
        self.classifier = classifier or DocumentClassifier()
        self.engine = engine or decision_engine

        # Extractors
        self.aadhaar_extractor = AadhaarExtractor()
        self.pan_extractor = PanExtractor()
        self.licence_extractor = LicenceExtractor()
        self.rc_extractor = RcExtractor()

    async def process_and_verify(self, request: DriverVerificationRequest) -> DriverVerificationResponse:
        """
        Executes end-to-end verification for a single driver in an isolated temp directory.
        """
        driver_id = request.driver_id
        mobile = request.mobile_number
        logger.info("Starting verification for driver", extra={"driver_id": driver_id})

        try:
            with TempDirectoryContext(driver_id) as temp_dir:
                aadhaar_data: Optional[AadhaarData] = None
                pan_data: Optional[PanData] = None
                licence_data: Optional[LicenceData] = None
                rc_data: Optional[RcData] = None
                doc_raw_texts: Dict[str, str] = {}

                # Document download & extract tasks map
                doc_urls = {
                    "aadhaar": request.aadhaar_zip_url,
                    "pan": request.pan_zip_url,
                    "licence": request.licence_zip_url,
                    "rc": request.rc_zip_url
                }

                for doc_type, url in doc_urls.items():
                    if not url:
                        continue

                    # 1. Download ZIP
                    zip_dest = os.path.join(temp_dir, f"{doc_type}.zip")
                    await self.download_client.download_file(url, zip_dest, doc_name=doc_type)

                    # 2. Extract ZIP using mobile_number as password
                    extracted_dir = os.path.join(temp_dir, doc_type)
                    extracted_files = self.zip_extractor.extract_zip(
                        zip_path=zip_dest,
                        password=mobile,
                        target_dir=extracted_dir,
                        doc_source=doc_type
                    )

                    # 3. Vision OCR & field extraction
                    current_doc_texts = []
                    for file_path in extracted_files:
                        ocr_result = await self.vision_client.extract_text_from_file(file_path)
                        if ocr_result and ocr_result.raw_text:
                            current_doc_texts.append(ocr_result.raw_text)
                        identified_type = self.classifier.classify(ocr_result, source_hint=doc_type)

                        if identified_type == "aadhaar" and not aadhaar_data:
                            aadhaar_data = self.aadhaar_extractor.extract(ocr_result)
                        elif identified_type == "pan" and not pan_data:
                            pan_data = self.pan_extractor.extract(ocr_result)
                        elif identified_type == "licence" and not licence_data:
                            licence_data = self.licence_extractor.extract(ocr_result)
                        elif identified_type == "rc" and not rc_data:
                            rc_data = self.rc_extractor.extract(ocr_result)

                    if current_doc_texts:
                        doc_raw_texts[doc_type] = "\n".join(current_doc_texts)

                # Save raw OCR text to result/ folder
                self._save_extracted_raw_text(driver_id, doc_raw_texts)

                # 4. Deterministic Cross-Verification Decision
                return self.engine.evaluate(
                    driver_id=driver_id,
                    provided_vehicle_class=request.vehicle_class,
                    aadhaar=aadhaar_data,
                    pan=pan_data,
                    licence=licence_data,
                    rc=rc_data
                )

        except VerificationServiceException as e:
            logger.error(
                f"Infrastructure error during verification: {e.message}",
                extra={"driver_id": driver_id, "error_code": e.error_code}
            )
            return DriverVerificationResponse(
                driver_id=driver_id,
                status="ERROR",
                error_message=e.message,
                rejection_reasons=[f"PROCESSING_ERROR: {e.error_code}"]
            )
        except Exception as e:
            logger.error(f"Unexpected error verifying driver: {e}", exc_info=True, extra={"driver_id": driver_id})
            return DriverVerificationResponse(
                driver_id=driver_id,
                status="ERROR",
                error_message="An unexpected internal processing error occurred.",
                rejection_reasons=[f"INTERNAL_ERROR: {type(e).__name__}"]
            )

    async def batch_process_and_verify(
        self,
        batch_request: BatchDriverVerificationRequest,
        max_concurrency: Optional[int] = None
    ) -> BatchDriverVerificationResponse:
        """
        Processes multiple drivers simultaneously with bounded concurrency using asyncio.Semaphore.
        Guarantees individual failure isolation.
        """
        start_time = time.perf_counter()
        concurrency = max_concurrency or settings.MAX_CONCURRENT_WORKERS
        semaphore = asyncio.Semaphore(concurrency)

        async def _worker(driver_req: DriverVerificationRequest) -> DriverVerificationResponse:
            async with semaphore:
                return await self.process_and_verify(driver_req)

        tasks = [_worker(driver) for driver in batch_request.drivers]
        results: List[DriverVerificationResponse] = await asyncio.gather(*tasks)

        verified = sum(1 for r in results if r.status == "VERIFIED")
        rejected = sum(1 for r in results if r.status == "REJECTED")
        errors = sum(1 for r in results if r.status == "ERROR")
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return BatchDriverVerificationResponse(
            total_count=len(results),
            verified_count=verified,
            rejected_count=rejected,
            error_count=errors,
            processing_time_ms=elapsed_ms,
            results=results
        )

    async def process_and_verify_direct_files(
        self,
        driver_id: str,
        mobile_number: str,
        vehicle_class: str,
        files: Dict[str, List[bytes]]
    ) -> DriverVerificationResponse:
        """
        Executes verification by directly sending provided document image bytes to Vision AI.
        Supports multi-page/multi-side (front & back) uploads for Aadhaar, DL, and RC.
        """
        logger.info("Starting direct file verification for driver", extra={"driver_id": driver_id})

        try:
            with TempDirectoryContext(driver_id) as temp_dir:
                aadhaar_data: Optional[AadhaarData] = None
                pan_data: Optional[PanData] = None
                licence_data: Optional[LicenceData] = None
                rc_data: Optional[RcData] = None
                doc_raw_texts: Dict[str, str] = {}

                for doc_type, byte_list in files.items():
                    if not byte_list:
                        continue

                    combined_texts = []
                    all_blocks = []

                    for idx, content in enumerate(byte_list):
                        if not content:
                            continue
                        file_path = os.path.join(temp_dir, f"{doc_type}_{idx}.jpg")
                        with open(file_path, "wb") as f:
                            f.write(content)

                        ocr_res = await self.vision_client.extract_text_from_file(file_path)
                        if ocr_res and ocr_res.raw_text:
                            combined_texts.append(ocr_res.raw_text)
                            all_blocks.extend(ocr_res.blocks)

                    if not combined_texts:
                        continue

                    # Record raw extracted text for this document type
                    doc_raw_texts[doc_type] = "\n".join(combined_texts)

                    combined_ocr = OCRResult(
                        raw_text=doc_raw_texts[doc_type],
                        blocks=all_blocks,
                        confidence=1.0
                    )

                    if doc_type == "aadhaar":
                        aadhaar_data = self.aadhaar_extractor.extract(combined_ocr)
                    elif doc_type == "pan":
                        pan_data = self.pan_extractor.extract(combined_ocr)
                    elif doc_type == "licence":
                        licence_data = self.licence_extractor.extract(combined_ocr)
                    elif doc_type == "rc":
                        rc_data = self.rc_extractor.extract(combined_ocr)

                # Save raw OCR text to result/ folder
                self._save_extracted_raw_text(driver_id, doc_raw_texts)

                return self.engine.evaluate(
                    driver_id=driver_id,
                    provided_vehicle_class=vehicle_class,
                    aadhaar=aadhaar_data,
                    pan=pan_data,
                    licence=licence_data,
                    rc=rc_data
                )

        except VerificationServiceException as e:
            logger.error(
                f"Infrastructure error during direct file verification: {e.message}",
                extra={"driver_id": driver_id, "error_code": e.error_code}
            )
            return DriverVerificationResponse(
                driver_id=driver_id,
                status="ERROR",
                error_message=e.message,
                rejection_reasons=[f"PROCESSING_ERROR: {e.error_code}"]
            )
        except Exception as e:
            logger.error(f"Unexpected error verifying driver files: {e}", exc_info=True, extra={"driver_id": driver_id})
            return DriverVerificationResponse(
                driver_id=driver_id,
                status="ERROR",
                error_message="An unexpected internal processing error occurred.",
                rejection_reasons=[f"INTERNAL_ERROR: {type(e).__name__}"]
            )

    def _save_extracted_raw_text(self, driver_id: str, doc_raw_texts: Dict[str, str]) -> None:
        """
        Saves raw extracted OCR text to the result/ directory in JSON format.
        """
        try:
            os.makedirs("result", exist_ok=True)
            safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", driver_id)
            result_file = os.path.join("result", f"{safe_id}_ocr_extracted.json")
            data = {
                "driver_id": driver_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "extracted_text": doc_raw_texts
            }
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved raw OCR extracted text to {result_file}", extra={"driver_id": driver_id})
        except Exception as e:
            logger.error(f"Failed to save extracted OCR text to file: {e}", extra={"driver_id": driver_id})

# Default singleton instance
cross_validator = CrossValidator()

