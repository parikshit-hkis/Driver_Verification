"""
PAN Card Extractor Microservice (Port 8004)
===========================================
Domain service for Permanent Account Number (PAN), cardholder name, father name, and DOB.
"""

import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, File, UploadFile, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import uvicorn

from microservices.pan_service.config import pan_config
from microservices.pan_service.extractor.pan_extractor import PanExtractor
from microservices.shared.clients.ocr_client import OCRClient
from microservices.shared.models import OCRResult, PanData
from microservices.shared.responses import ApiResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s")
logger = logging.getLogger("pan_service")

_extractor = PanExtractor()
_ocr_client = OCRClient(ocr_service_url=pan_config.OCR_SERVICE_URL)

app = FastAPI(
    title="PAN Card Extractor Microservice",
    description="Extracts 10-character PAN number, cardholder full name, father's name, and date of birth via OCR delegation.",
    version="2.0.0",
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
        "service": "pan_service",
        "status": "HEALTHY" if ocr_ok else "DEGRADED",
        "port": pan_config.PORT,
        "ocr_service_url": pan_config.OCR_SERVICE_URL,
        "ocr_service_connected": ocr_ok,
    }


@app.post("/extract", summary="Extract structured data from PAN Card images")
async def extract_pan(
    front_image: UploadFile = File(..., description="PAN Card front image"),
    back_image: Optional[UploadFile] = File(None, description="Optional PAN Card back image"),
):
    try:
        front_bytes = await front_image.read()
        if not front_bytes:
            raise HTTPException(status_code=400, detail="Empty front image file")

        # 1. Front image OCR
        ocr_front, quality_front = await _ocr_client.extract_ocr(
            image_bytes=front_bytes,
            filename=front_image.filename or "pan_front.jpg"
        )

        # 2. Back image OCR (optional)
        ocr_back, quality_back = (None, None)
        if back_image:
            back_bytes = await back_image.read()
            if back_bytes:
                ocr_back, quality_back = await _ocr_client.extract_ocr(
                    image_bytes=back_bytes,
                    filename=back_image.filename or "pan_back.jpg"
                )

        # 3. Domain extraction
        data: PanData = _extractor.extract_pan(ocr_front, ocr_back)
        status = "SUCCESS" if (data.pan_number or data.full_name) else "PARTIAL"

        return ApiResponse(
            success=True,
            status=status,
            data=data.model_dump(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PAN extraction error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PAN Card extraction failed: {str(e)}")


@app.post("/extract-from-ocr", summary="Extract PAN data directly from OCR payload")
async def extract_from_ocr(
    payload: Dict[str, Any] = Body(..., description="Payload containing ocr_front and optional ocr_back")
):
    try:
        ocr_front_data = payload.get("ocr_front")
        ocr_back_data = payload.get("ocr_back")

        ocr_front = OCRResult(**ocr_front_data) if ocr_front_data else None
        ocr_back = OCRResult(**ocr_back_data) if ocr_back_data else None

        data = _extractor.extract_pan(ocr_front, ocr_back)
        return ApiResponse(
            success=True,
            status="SUCCESS" if (data.pan_number or data.full_name) else "PARTIAL",
            data=data.model_dump(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction from OCR failed: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("microservices.pan_service.main:app", host=pan_config.HOST, port=pan_config.PORT, reload=True)
