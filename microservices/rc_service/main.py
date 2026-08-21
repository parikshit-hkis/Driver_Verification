"""
RC Extractor Microservice (Port 8005)
=====================================
Domain service for Vehicle Registration Certificate (RC), owner name, vehicle class, dates,
confidence scoring, observability metrics, and machine-readable explainability diagnostics.
"""

import sys
import time
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, File, UploadFile, HTTPException, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
import uvicorn

from microservices.rc_service.config import rc_config, RCConfigurationError
from microservices.rc_service.extractor.rc_extractor import RCExtractor
from microservices.rc_service.metrics import rc_metrics
from microservices.shared.clients.ocr_client import OCRClient
from microservices.shared.models import OCRResult, RCData
from microservices.shared.responses import ApiResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s")
logger = logging.getLogger("rc_service")

# Validate configuration on startup
# try:
#     rc_config.validate_config()
#     logger.info("RC Extractor configuration validated successfully at startup.")
# except RCConfigurationError as ce:
#     logger.critical(f"FATAL: RC service configuration validation failed: {ce}")
#     raise

_extractor = RCExtractor()
_ocr_client = OCRClient(ocr_service_url=rc_config.OCR_SERVICE_URL)

app = FastAPI(
    title="RC Extractor Microservice",
    description="Extracts vehicle registration number, owner name, vehicle class, dates, and calculates confidence scores via OCR delegation.",
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["System Health"])
async def health_check():
    ocr_ok = await _ocr_client.is_healthy()
    return {
        "service": "rc_service",
        "status": "HEALTHY" if ocr_ok else "DEGRADED",
        "port": rc_config.PORT,
        "ocr_service_url": rc_config.OCR_SERVICE_URL,
        "ocr_service_connected": ocr_ok,
    }


@app.get("/metrics", tags=["Observability"])
async def get_metrics():
    """Retrieve operational telemetry and field-level extraction metrics."""
    return rc_metrics.get_metrics()


@app.post("/extract", summary="Extract structured data from Vehicle Registration Certificate (RC)")
async def extract_rc(
    request: Request,
    front_image: UploadFile = File(..., description="RC front image"),
    back_image: Optional[UploadFile] = File(None, description="Optional RC back image"),
):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    t0 = time.perf_counter()
    # logger.info(f"[{request_id}] Received extract RC image request")

    try:
        front_bytes = await front_image.read()
        if not front_bytes:
            raise HTTPException(status_code=400, detail="Empty front image file")

        # 1. Front image OCR
        ocr_front, quality_front = await _ocr_client.extract_ocr(
            image_bytes=front_bytes,
            filename=front_image.filename or "rc_front.jpg"
        )

        # 2. Back image OCR (optional)
        ocr_back, quality_back = (None, None)
        if back_image:
            back_bytes = await back_image.read()
            if back_bytes:
                ocr_back, quality_back = await _ocr_client.extract_ocr(
                    image_bytes=back_bytes,
                    filename=back_image.filename or "rc_back.jpg"
                )

        # 3. Domain extraction
        data: RCData = _extractor.extract_rc(ocr_front, ocr_back)
        status = "SUCCESS" if (data.registration_number or data.owner_name) else "PARTIAL"

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        rc_metrics.record_extraction(
            rc_data=data,
            latency_ms=elapsed_ms,
            is_empty_ocr=(ocr_front is None or not ocr_front.texts),
        )

        return ApiResponse(
            success=True,
            status=status,
            data=data.model_dump(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] RC extraction error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="RC extraction failed due to internal error")


@app.post("/extract-from-ocr", summary="Extract RC data directly from OCR payload")
async def extract_from_ocr(
    request: Request,
    payload: Dict[str, Any] = Body(..., description="Payload containing ocr_front and optional ocr_back")
):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    t0 = time.perf_counter()

    try:
        ocr_front_data = payload.get("ocr_front")
        ocr_back_data = payload.get("ocr_back")

        ocr_front = OCRResult(**ocr_front_data) if ocr_front_data else None
        ocr_back = OCRResult(**ocr_back_data) if ocr_back_data else None

        data = _extractor.extract_rc(ocr_front, ocr_back)
        status = "SUCCESS" if (data.registration_number or data.owner_name) else "PARTIAL"

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        rc_metrics.record_extraction(
            rc_data=data,
            latency_ms=elapsed_ms,
            is_empty_ocr=(ocr_front is None or not ocr_front.texts),
        )

        return ApiResponse(
            success=True,
            status=status,
            data=data.model_dump(),
        )
    except Exception as e:
        logger.error(f"[{request_id}] Extraction from OCR payload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Extraction from OCR failed due to internal error")


if __name__ == "__main__":
    uvicorn.run("microservices.rc_service.main:app", host=rc_config.HOST, port=rc_config.PORT, reload=True)
