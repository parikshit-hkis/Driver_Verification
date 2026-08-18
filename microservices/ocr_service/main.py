"""
OCR & Computer Vision Microservice (Port 8001)
==============================================
Dedicated high-performance service hosting PaddleOCR PP-OCRv4 & OpenCV preprocessor.
"""

import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

# Ensure project root is on sys.path
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import uvicorn
import cv2
import numpy as np

from microservices.ocr_service.config import ocr_config
from microservices.ocr_service.engine.preprocessor import ImagePreprocessor
from microservices.ocr_service.engine.paddle_ocr import PaddleOCRService
from microservices.shared.responses import ApiResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s")
logger = logging.getLogger("ocr_service")

# Singletons
_preprocessor: Optional[ImagePreprocessor] = None
_ocr_service: Optional[PaddleOCRService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _preprocessor, _ocr_service
    logger.info("Starting OCR Microservice...")
    _preprocessor = ImagePreprocessor()
    _ocr_service = PaddleOCRService()
    logger.info("OCR Microservice successfully pre-warmed and ready.")
    yield
    logger.info("Shutting down OCR Microservice.")


app = FastAPI(
    title="OCR & Computer Vision Microservice",
    description="High-accuracy PP-OCRv4 neural inference and OpenCV auto-rotation/CLAHE preprocessing engine.",
    version="2.0.0",
    lifespan=lifespan,
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
    return {
        "service": "ocr_service",
        "status": "HEALTHY",
        "port": ocr_config.PORT,
        "engine": {
            "use_gpu": ocr_config.USE_GPU,
            "min_confidence": ocr_config.MIN_CONFIDENCE,
            "det_model": ocr_config.DET_MODEL_DIR,
            "rec_model": ocr_config.REC_MODEL_DIR,
        },
    }


@app.post("/extract", summary="Run OCR and image quality diagnostics on document image")
async def extract_ocr(
    file: UploadFile = File(..., description="Document image file (JPG, PNG, WebP, etc.)"),
    min_confidence: Optional[float] = Query(None, description="Override minimum confidence threshold"),
    fix_orientation: bool = Query(True, description="Apply auto-rotation and deskewing"),
    enhance: bool = Query(True, description="Apply adaptive LAB CLAHE / gamma enhancement"),
):
    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty image file received")

        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(status_code=400, detail="Could not decode image format")

        preprocessed_img, quality_report = _preprocessor.preprocess(
            img,
            fix_orientation=fix_orientation,
            enhance=enhance,
        )

        ocr_result = _ocr_service.extract(preprocessed_img, min_confidence=min_confidence)

        return ApiResponse(
            success=True,
            status="SUCCESS",
            data={
                "ocr_result": ocr_result.model_dump(),
                "quality_report": quality_report.to_dict(),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OCR extraction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("microservices.ocr_service.main:app", host=ocr_config.HOST, port=ocr_config.PORT, reload=True)
