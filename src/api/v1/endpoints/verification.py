from fastapi import APIRouter, Depends, Form, File, UploadFile
from typing import Optional, List, Dict
from src.schemas.request_schemas import DriverVerificationRequest, BatchDriverVerificationRequest
from src.schemas.response_schemas import DriverVerificationResponse, BatchDriverVerificationResponse
from src.verification.cross_validator import CrossValidator
from src.api.dependencies import get_cross_validator

router = APIRouter(tags=["Driver Verification"])

@router.post(
    "/verify-driver",
    response_model=DriverVerificationResponse,
    summary="Verify Single Driver Document Set (S3 URLs)",
    description="Synchronously downloads, decrypts, OCR-processes, and cross-verifies driver identity documents from URLs."
)
async def verify_single_driver(
    payload: DriverVerificationRequest,
    validator: CrossValidator = Depends(get_cross_validator)
) -> DriverVerificationResponse:
    return await validator.process_and_verify(payload)

@router.post(
    "/batch-verify",
    response_model=BatchDriverVerificationResponse,
    summary="Verify Drivers in Batch (Concurrent)",
    description="Simultaneously verifies multiple drivers using an asynchronous worker pool with bounded concurrency."
)
async def verify_drivers_batch(
    payload: BatchDriverVerificationRequest,
    validator: CrossValidator = Depends(get_cross_validator)
) -> BatchDriverVerificationResponse:
    return await validator.batch_process_and_verify(payload)

@router.post(
    "/verify-driver-files",
    response_model=DriverVerificationResponse,
    summary="Verify Driver via Direct File Upload (Interactive)",
    description="Select and upload local document images directly (Aadhaar, PAN, Licence, RC) without requiring URLs or password encryption."
)
async def verify_single_driver_files(
    driver_id: str = Form(..., description="Unique driver ID (e.g. driver-101)"),
    mobile_number: str = Form(..., description="Driver 10-digit mobile number"),
    vehicle_class: str = Form(..., description="Applied vehicle class (e.g. 2 wheeler, car, truck, 3 wheeler)"),
    adhar_front: Optional[UploadFile] = File(None, description="Aadhaar Front Image"),
    adhar_back: Optional[UploadFile] = File(None, description="Aadhaar Back Image"),
    pan_front: Optional[UploadFile] = File(None, description="PAN Front Image"),
    licence_front: Optional[UploadFile] = File(None, description="Driving Licence Front Image"),
    licence_back: Optional[UploadFile] = File(None, description="Driving Licence Back Image"),
    rc_front: Optional[UploadFile] = File(None, description="RC Front Image"),
    rc_back: Optional[UploadFile] = File(None, description="RC Back Image"),
    aadhaar_front: Optional[UploadFile] = File(None, description="Alias for adhar_front"),
    aadhaar_back: Optional[UploadFile] = File(None, description="Alias for adhar_back"),
    validator: CrossValidator = Depends(get_cross_validator)
) -> DriverVerificationResponse:
    files_map: Dict[str, List[bytes]] = {
        "aadhaar": [],
        "pan": [],
        "licence": [],
        "rc": []
    }

    # Aadhaar front & back
    af = adhar_front or aadhaar_front
    ab = adhar_back or aadhaar_back
    if af and af.filename:
        files_map["aadhaar"].append(await af.read())
    if ab and ab.filename:
        files_map["aadhaar"].append(await ab.read())

    # PAN front
    if pan_front and pan_front.filename:
        files_map["pan"].append(await pan_front.read())

    # Licence front & back
    if licence_front and licence_front.filename:
        files_map["licence"].append(await licence_front.read())
    if licence_back and licence_back.filename:
        files_map["licence"].append(await licence_back.read())

    # RC front & back
    if rc_front and rc_front.filename:
        files_map["rc"].append(await rc_front.read())
    if rc_back and rc_back.filename:
        files_map["rc"].append(await rc_back.read())

    return await validator.process_and_verify_direct_files(
        driver_id=driver_id,
        mobile_number=mobile_number,
        vehicle_class=vehicle_class,
        files=files_map
    )
