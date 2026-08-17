"""
RC Extractor Microservice Router
=================================
Provides Vehicle Registration Certificate (RC) structured extraction endpoints.
"""

from typing import Optional
from fastapi import APIRouter, File, UploadFile, HTTPException
import numpy as np
import cv2

from app.ocr.preprocessor import ImagePreprocessor
from app.ocr.paddle_ocr import PaddleOCRService
from app.services.rc_extractor.extractor import RCExtractor
from app.services.rc_extractor.models import RCData

router = APIRouter(prefix="/rc", tags=["RC Extractor"])

_preprocessor = ImagePreprocessor()
_ocr = PaddleOCRService()
_extractor = RCExtractor()


def _process_image(file_bytes: bytes):
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None, None
    prep_img, quality = _preprocessor.preprocess(img)
    ocr_res = _ocr.extract(prep_img)
    return ocr_res, quality


@router.post("/extract", summary="Extract structured data from Vehicle Registration Certificate (RC)")
async def extract_rc(
    front_image: UploadFile = File(..., description="RC front image"),
    back_image: Optional[UploadFile] = File(None, description="Optional RC back image"),
):
    """
    Processes RC front and back images, extracts registration number, owner name,
    vehicle type, registration date, validity, and calculates field-level confidence scores.
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

        data = _extractor.extract_rc(ocr_front, ocr_back)

        return {
            "status": "SUCCESS" if (data.registration_number or data.owner_name) else "PARTIAL",
            "overall_confidence": round(data.overall_confidence, 2),
            "data": data.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RC extraction failed: {str(e)}")
