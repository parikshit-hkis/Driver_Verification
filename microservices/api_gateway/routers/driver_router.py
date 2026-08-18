"""
Master Driver Verification & Records Management Router
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Query, Response

from microservices.api_gateway.config import gateway_config
from microservices.api_gateway.clients.service_clients import ServiceClients
from microservices.shared.responses import ApiResponse

logger = logging.getLogger("gateway.driver_router")
router = APIRouter(prefix="/driver", tags=["Driver Verification Gateway"])

_clients = ServiceClients()


async def _read_file_safe(upload: Optional[UploadFile]) -> Optional[bytes]:
    if not upload:
        return None
    content = await upload.read()
    return content if content else None


@router.post("/verify", summary="Verify complete driver document set across all microservices")
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
    Master Driver Verification Gateway:
    1. Reads incoming document images asynchronously.
    2. Concurrently calls specialized domain microservices (Aadhaar, DL, PAN, RC) over HTTP.
    3. Aggregates all extracted document fields into a unified payload.
    4. Calls Identity Cross-Validator microservice for Name fuzzy matching & exact DOB matching.
    5. Persists extraction and validation JSON reports to disk.
    6. Returns consolidated verification result.
    """
    try:
        # 1. Read files into memory concurrently
        (
            a_front_b, a_back_b,
            dl_front_b, dl_back_b,
            pan_front_b, pan_back_b,
            rc_front_b, rc_back_b,
        ) = await asyncio.gather(
            _read_file_safe(aadhaar_front), _read_file_safe(aadhaar_back),
            _read_file_safe(licence_front), _read_file_safe(licence_back),
            _read_file_safe(pan_front), _read_file_safe(pan_back),
            _read_file_safe(rc_front), _read_file_safe(rc_back),
        )

        # 2. Concurrently dispatch to all 4 extraction microservices
        aadhaar_task = _clients.extract_aadhaar(a_front_b, a_back_b)
        dl_task = _clients.extract_dl(dl_front_b, dl_back_b)
        pan_task = _clients.extract_pan(pan_front_b, pan_back_b)
        rc_task = _clients.extract_rc(rc_front_b, rc_back_b)

        aadhaar_res, dl_res, pan_res, rc_res = await asyncio.gather(
            aadhaar_task, dl_task, pan_task, rc_task
        )

        # 3. Assemble consolidated extraction payload
        extraction_payload = {
            "driver_id": driver_id,
            "documents": {
                "aadhaar": {
                    "document_type": "aadhaar",
                    "status": aadhaar_res.get("status", "MISSING"),
                    "warning": aadhaar_res.get("warning"),
                    "data": aadhaar_res.get("data"),
                },
                "licence": {
                    "document_type": "driving_licence",
                    "status": dl_res.get("status", "MISSING"),
                    "warning": dl_res.get("warning"),
                    "data": dl_res.get("data"),
                },
                "pan": {
                    "document_type": "pan",
                    "status": pan_res.get("status", "MISSING"),
                    "warning": pan_res.get("warning"),
                    "data": pan_res.get("data"),
                },
                "rc": {
                    "document_type": "rc",
                    "status": rc_res.get("status", "MISSING"),
                    "warning": rc_res.get("warning"),
                    "data": rc_res.get("data"),
                },
            }
        }

        # 4. Save extraction JSON
        extr_dir = gateway_config.EXTRACTION_OUTPUT_DIR
        extr_dir.mkdir(parents=True, exist_ok=True)
        extr_file = extr_dir / f"{driver_id}.json"
        with open(extr_file, "w", encoding="utf-8") as f:
            json.dump(extraction_payload, f, indent=2, ensure_ascii=False)

        # 5. Call Cross-Validator Microservice
        val_res = await _clients.cross_verify(extraction_payload)

        # 6. Save validation JSON
        val_dir = gateway_config.VALIDATION_OUTPUT_DIR
        val_dir.mkdir(parents=True, exist_ok=True)
        val_file = val_dir / f"{driver_id}.json"
        with open(val_file, "w", encoding="utf-8") as f:
            json.dump(val_res, f, indent=2, ensure_ascii=False)

        return ApiResponse(
            success=True,
            status="SUCCESS",
            data={
                "driver_id": driver_id,
                "extraction": extraction_payload,
                "cross_validation": val_res,
            }
        )

    except Exception as e:
        logger.error(f"Master verification failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Driver verification orchestration failed: {str(e)}")


# ── Historical Records Management Endpoints ────────────────────────────────────

@router.get("/records", summary="List historical verified driver records")
async def list_driver_records(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None, description="Filter by status: MATCHED, REVIEW, MISMATCH"),
):
    """Retrieve list of verified drivers from persisted JSON records."""
    extr_dir = gateway_config.EXTRACTION_OUTPUT_DIR
    val_dir = gateway_config.VALIDATION_OUTPUT_DIR

    if not extr_dir.exists():
        return ApiResponse(success=True, data={"total": 0, "drivers": []})

    json_files = sorted(extr_dir.glob("*.json"))
    records = []

    for jf in json_files:
        driver_id = jf.stem
        val_file = val_dir / f"{driver_id}.json"

        overall_status = "UNKNOWN"
        name_status = "UNKNOWN"
        dob_status = "UNKNOWN"

        if val_file.exists():
            try:
                with open(val_file, "r", encoding="utf-8") as vf:
                    val_data = json.load(vf)
                    overall_status = val_data.get("overall_status", "UNKNOWN")
                    name_status = val_data.get("overall_name_status", "UNKNOWN")
                    dob_status = val_data.get("overall_dob_status", "UNKNOWN")
            except Exception:
                pass

        if status_filter and overall_status.upper() != status_filter.upper():
            continue

        records.append({
            "driver_id": driver_id,
            "overall_status": overall_status,
            "name_status": name_status,
            "dob_status": dob_status,
            "extraction_file": str(jf.name),
        })

    paginated = records[offset : offset + limit]

    return ApiResponse(
        success=True,
        data={
            "total": len(records),
            "limit": limit,
            "offset": offset,
            "drivers": paginated,
        }
    )


@router.get("/{driver_id}", summary="Get detailed verification report for a specific driver")
async def get_driver_record(driver_id: str):
    """Fetch complete extraction and cross-validation JSON for a driver ID."""
    extr_file = gateway_config.EXTRACTION_OUTPUT_DIR / f"{driver_id}.json"
    val_file = gateway_config.VALIDATION_OUTPUT_DIR / f"{driver_id}.json"

    if not extr_file.exists():
        raise HTTPException(status_code=404, detail=f"Driver record '{driver_id}' not found")

    with open(extr_file, "r", encoding="utf-8") as f:
        extr_data = json.load(f)

    val_data = None
    if val_file.exists():
        with open(val_file, "r", encoding="utf-8") as f:
            val_data = json.load(f)

    return ApiResponse(
        success=True,
        data={
            "driver_id": driver_id,
            "extraction": extr_data,
            "cross_validation": val_data,
        }
    )


@router.delete("/{driver_id}", summary="Delete driver verification record")
async def delete_driver_record(driver_id: str):
    """Delete extraction and validation records for a driver."""
    extr_file = gateway_config.EXTRACTION_OUTPUT_DIR / f"{driver_id}.json"
    val_file = gateway_config.VALIDATION_OUTPUT_DIR / f"{driver_id}.json"

    deleted = False
    if extr_file.exists():
        extr_file.unlink()
        deleted = True
    if val_file.exists():
        val_file.unlink()
        deleted = True

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Driver record '{driver_id}' not found")

    return ApiResponse(
        success=True,
        data={"message": f"Driver record '{driver_id}' successfully deleted"}
    )
