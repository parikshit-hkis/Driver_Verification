"""
OCR Microservice Router
========================
Provides standalone OCR inference & image quality analysis endpoint.
"""

from typing import Optional
from fastapi import APIRouter, File, UploadFile, Query, HTTPException
import numpy as np
import cv2

from app.dependencies import get_preprocessor, get_ocr_service

router = APIRouter(prefix="/ocr", tags=["OCR Engine"])


@router.post("/extract", summary="Run OCR on document image")
async def extract_ocr(
    file: UploadFile = File(..., description="Document image file (JPG, PNG, WebP)"),
    min_confidence: Optional[float] = Query(None, description="Override minimum OCR confidence threshold"),
    fix_orientation: bool = Query(True, description="Apply auto-rotation and deskewing"),
    enhance: bool = Query(True, description="Apply adaptive LAB CLAHE / gamma enhancement"),
):
    """
    Accepts a document image, executes computer vision preprocessing (EXIF, rotation, deskew, CLAHE),
    and runs PP-OCRv4 neural inference to extract text lines, bounding boxes, and confidence scores.
    """
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file or unsupported format")

        preprocessed_img, quality_report = get_preprocessor().preprocess(
            img,
            fix_orientation=fix_orientation,
            enhance=enhance,
        )

        ocr_res = get_ocr_service().extract(preprocessed_img, min_confidence=min_confidence)

        return {
            "status": "SUCCESS",
            "full_text": ocr_res.full_text,
            "text_count": len(ocr_res.texts),
            "texts": [t.model_dump() for t in ocr_res.texts],
            "quality_report": {
                "blur_score": quality_report.blur_score,
                "is_blurry": quality_report.is_blurry,
                "brightness": quality_report.brightness,
                "is_too_dark": quality_report.is_too_dark,
                "is_too_bright": quality_report.is_too_bright,
                "glare_percentage": quality_report.glare_percentage,
                "has_glare": quality_report.has_glare,
                "was_rotated": quality_report.was_rotated,
                "rotation_applied": quality_report.rotation_applied,
                "skew_corrected": quality_report.skew_corrected,
                "skew_angle": quality_report.skew_angle,
                "was_enhanced": quality_report.was_enhanced,
                "warnings": quality_report.warnings,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")
