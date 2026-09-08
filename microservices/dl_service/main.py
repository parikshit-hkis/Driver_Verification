"""
Driving Licence Extractor Microservice (Port 8003)
==================================================
Domain service for Sarathi DL format, validity dates, and vehicle category classes.
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

from microservices.dl_service.config import dl_config
from microservices.dl_service.extractor.dl_extractor import DrivingLicenceExtractor
from microservices.shared.clients.ocr_client import OCRClient
from microservices.shared.models import OCRResult, DrivingLicenceData
from microservices.shared.responses import ApiResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s")
logger = logging.getLogger("dl_service")

_extractor = DrivingLicenceExtractor()
_ocr_client = OCRClient(ocr_service_url=dl_config.OCR_SERVICE_URL)

app = FastAPI(
    title="Driving Licence Extractor Microservice",
    description="Extracts Sarathi DL number, holder name, DOB, issue/expiry dates, and vehicle class categories via OCR delegation.",
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
        "service": "dl_service",
        "status": "HEALTHY" if ocr_ok else "DEGRADED",
        "port": dl_config.PORT,
        "ocr_service_url": dl_config.OCR_SERVICE_URL,
        "ocr_service_connected": ocr_ok,
    }


@app.post("/extract", summary="Extract structured data from Driving Licence images")
async def extract_dl(
    front_image: UploadFile = File(..., description="Driving Licence front image"),
    back_image: Optional[UploadFile] = File(None, description="Optional Driving Licence back image"),
):
    try:
        front_bytes = await front_image.read()
        if not front_bytes:
            raise HTTPException(status_code=400, detail="Empty front image file")

        # 1. OCR for front image
        ocr_front, quality_front = await _ocr_client.extract_ocr(
            image_bytes=front_bytes,
            filename=front_image.filename or "dl_front.jpg"
        )

        # 2. OCR for back image (if provided)
        ocr_back, quality_back = (None, None)
        if back_image:
            back_bytes = await back_image.read()
            if back_bytes:
                ocr_back, quality_back = await _ocr_client.extract_ocr(
                    image_bytes=back_bytes,
                    filename=back_image.filename or "dl_back.jpg"
                )

        # 3. Domain extraction
        data: DrivingLicenceData = _extractor.extract_dl(ocr_front, ocr_back)
        status = "SUCCESS" if (data.licence_number or data.full_name) else "PARTIAL"

        return ApiResponse(
            success=True,
            status=status,
            data=data.model_dump(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"DL extraction error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Driving Licence extraction failed: {str(e)}")


@app.post("/extract-from-ocr", summary="Extract Driving Licence data directly from OCR payload")
async def extract_from_ocr(
    payload: Dict[str, Any] = Body(..., description="Payload containing ocr_front and optional ocr_back")
):
    try:
        ocr_front_data = payload.get("ocr_front")
        ocr_back_data = payload.get("ocr_back")

        ocr_front = OCRResult(**ocr_front_data) if ocr_front_data else None
        ocr_back = OCRResult(**ocr_back_data) if ocr_back_data else None

        data = _extractor.extract_dl(ocr_front, ocr_back)
        return ApiResponse(
            success=True,
            status="SUCCESS" if (data.licence_number or data.full_name) else "PARTIAL",
            data=data.model_dump(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction from OCR failed: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("microservices.dl_service.main:app", host=dl_config.HOST, port=dl_config.PORT, reload=True)
