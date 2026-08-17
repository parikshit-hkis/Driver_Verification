"""
PAN Card Extractor Microservice Router
=======================================
Provides Permanent Account Number (PAN) Card structured extraction endpoints.
"""

from typing import Optional
from fastapi import APIRouter, File, UploadFile, HTTPException
import numpy as np
import cv2

from app.ocr.preprocessor import ImagePreprocessor
from app.ocr.paddle_ocr import PaddleOCRService
from app.services.pan_extractor.extractor import PanExtractor
from app.services.pan_extractor.models import PanData

router = APIRouter(prefix="/pan", tags=["PAN Extractor"])

_preprocessor = ImagePreprocessor()
_ocr = PaddleOCRService()
_extractor = PanExtractor()


def _process_image(file_bytes: bytes):
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None, None
    prep_img, quality = _preprocessor.preprocess(img)
    ocr_res = _ocr.extract(prep_img)
    return ocr_res, quality


@router.post("/extract", summary="Extract structured data from PAN Card")
async def extract_pan(
    front_image: UploadFile = File(..., description="PAN Card front image"),
    back_image: Optional[UploadFile] = File(None, description="Optional PAN Card back image"),
):
    """
    Processes PAN Card front image, extracts 10-character PAN number,
    cardholder full name, father's name, and date of birth.
    """
    try:
        front_bytes = await front_image.read()
        ocr_front, quality_front = _process_image(front_bytes)

        if ocr_front is None:
            raise HTTPException(status_code=400, detail="Invalid front image file")

        ocr_back, quality_back = (None, None)
        if back_image:
            back_bytes = await back_image.read()
            if back_bytes:
                ocr_back, quality_back = _process_image(back_bytes)

        data = _extractor.extract_pan(ocr_front, ocr_back)

        return {
            "status": "SUCCESS" if (data.pan_number or data.full_name) else "PARTIAL",
            "data": data.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PAN Card extraction failed: {str(e)}")
