"""
Master Driver Verification Gateway Router
==========================================
API Gateway orchestrating end-to-end multi-document extraction and identity verification.
"""

from typing import Optional
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
import numpy as np
import cv2

from app.services.doc_type_detector import DocumentType
from app.models.driver_models import DocumentExtractionResult, DriverVerificationResult
from app.services.directory_scanner import DocumentFilesSpec, MANDATORY_DOC_ORDER
from app.dependencies import get_pipeline, get_cross_validator

router = APIRouter(prefix="/driver", tags=["Driver Verification Gateway"])


async def _read_image(upload_file: Optional[UploadFile]):
    if not upload_file:
        return None
    contents = await upload_file.read()
    if not contents:
        return None
    nparr = np.frombuffer(contents, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)


@router.post("/verify", summary="Verify complete driver document set")
async def verify_driver(
    driver_id: str = Form(..., description="Unique driver ID (phone number or UUID)"),
    aadhaar_front: Optional[UploadFile] = File(None, description="Aadhaar Card Front Image"),
    aadhaar_back: Optional[UploadFile] = File(None, description="Aadhaar Card Back Image"),
    licence_front: Optional[UploadFile] = File(None, description="Driving Licence Front Image"),
    licence_back: Optional[UploadFile] = File(None, description="Driving Licence Back Image"),
    pan_front: Optional[UploadFile] = File(None, description="PAN Card Front Image"),
    pan_back: Optional[UploadFile] = File(None, description="PAN Card Back Image"),
    rc_front: Optional[UploadFile] = File(None, description="RC Front Image"),
    rc_back: Optional[UploadFile] = File(None, description="RC Back Image"),
):
    """
    Accepts all 4 document images for a driver, executes full verification pipeline:
    1. Aadhaar -> Driving Licence -> PAN -> RC (Front & Back isolated processing)
    2. Computer vision auto-orientation, deskew, and CLAHE enhancement
    3. PP-OCRv4 neural extraction & spatial layout reasoning
    4. Automatic JSON persistence
    5. Identity cross-validation (Pairwise Name Fuzzy Score + Exact DOB Match)
    """
    try:
        pipeline = get_pipeline()
        cross_validator = get_cross_validator()

        doc_uploads = {
            DocumentType.AADHAAR: (aadhaar_front, aadhaar_back),
            DocumentType.DRIVING_LICENCE: (licence_front, licence_back),
            DocumentType.PAN: (pan_front, pan_back),
            DocumentType.RC: (rc_front, rc_back),
        }

        driver_result = DriverVerificationResult(driver_id=driver_id)

        for doc_type in MANDATORY_DOC_ORDER:
            front_up, back_up = doc_uploads[doc_type]
            front_img = await _read_image(front_up)
            back_img = await _read_image(back_up)

            if front_img is None and back_img is None:
                doc_res = DocumentExtractionResult(
                    document_type=doc_type,
                    status="MISSING",
                    warning=f"No {doc_type.value} images uploaded",
                )
            else:
                doc_spec = DocumentFilesSpec(
                    doc_type=doc_type,
                    front_path=front_img,
                    back_path=back_img,
                )
                doc_res = pipeline.extract_document(doc_spec)

            if doc_type == DocumentType.AADHAAR:
                driver_result.aadhaar_result = doc_res
            elif doc_type == DocumentType.DRIVING_LICENCE:
                driver_result.licence_result = doc_res
            elif doc_type == DocumentType.PAN:
                driver_result.pan_result = doc_res
            elif doc_type == DocumentType.RC:
                driver_result.rc_result = doc_res

        # Save extraction JSON
        driver_result.save_json()

        # Run identity cross-validation
        cross_val = cross_validator.validate_driver_json(driver_result.to_dict())
        cross_val.save_json()

        return {
            "status": "SUCCESS",
            "driver_id": driver_id,
            "extraction": driver_result.to_dict(),
            "cross_validation": cross_val.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Driver verification failed: {str(e)}")
