"""
Master Driver Verification & Records Management Router
"""

import os
import json
import zipfile
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Query, Response, Body
from pydantic import BaseModel, Field
import httpx

from microservices.api_gateway.config import gateway_config
from microservices.api_gateway.clients.service_clients import ServiceClients
from microservices.shared.responses import ApiResponse

logger = logging.getLogger("gateway.driver_router")
router = APIRouter(prefix="/driver", tags=["Driver Verification Gateway"])

_clients = ServiceClients()


class DriverVerifyUrlsRequest(BaseModel):
    driver_id: str = Field(..., description="Unique driver ID (phone number or UUID)")
    aadhaar_url: Optional[str] = Field(None, description="Aadhaar Zip or Direct Image URL")
    aadhaar_zip_url: Optional[str] = Field(None, description="Alias for aadhaar_url")
    aadhaar_front_url: Optional[str] = Field(None, description="Direct Aadhaar Front Image URL")
    aadhaar_back_url: Optional[str] = Field(None, description="Direct Aadhaar Back Image URL")

    licence_url: Optional[str] = Field(None, description="Driving Licence Zip or Direct Image URL")
    licence_zip_url: Optional[str] = Field(None, description="Alias for licence_url")
    licence_front_url: Optional[str] = Field(None, description="Direct DL Front Image URL")
    licence_back_url: Optional[str] = Field(None, description="Direct DL Back Image URL")

    pan_url: Optional[str] = Field(None, description="PAN Card Zip or Direct Image URL")
    pan_zip_url: Optional[str] = Field(None, description="Alias for pan_url")
    pan_front_url: Optional[str] = Field(None, description="Direct PAN Front Image URL")
    pan_back_url: Optional[str] = Field(None, description="Direct PAN Back Image URL")

    rc_url: Optional[str] = Field(None, description="RC Book Zip or Direct Image URL")
    rc_zip_url: Optional[str] = Field(None, description="Alias for rc_url")
    rc_front_url: Optional[str] = Field(None, description="Direct RC Front Image URL")
    rc_back_url: Optional[str] = Field(None, description="Direct RC Back Image URL")


async def _read_file_safe(upload: Optional[UploadFile]) -> Optional[bytes]:
    if not upload:
        return None
    content = await upload.read()
    return content if content else None


async def _fetch_url_bytes(client: httpx.AsyncClient, url: Optional[str]) -> Optional[bytes]:
    """Downloads binary bytes from a remote URL (e.g. S3 pre-signed URL)."""
    if not url or not str(url).strip():
        return None
    clean_url = str(url).strip()
    try:
        res = await client.get(clean_url, follow_redirects=True)
        if res.status_code == 200 and res.content:
            return res.content
        logger.warning(f"Download failed for {clean_url}: HTTP {res.status_code}")
        return None
    except Exception as e:
        logger.error(f"Exception downloading from {clean_url}: {e}")
        return None


def _extract_images_from_zip_bytes(zip_bytes: bytes) -> Tuple[Optional[bytes], Optional[bytes]]:
    """Extracts front and back images from an in-memory zip archive."""
    if not zip_bytes:
        return None, None

    # Check if buffer is a zip archive
    if not (len(zip_bytes) >= 4 and zip_bytes[:4] == b"PK\x03\x04"):
        return zip_bytes, None

    valid_exts = (".jpg", ".jpeg", ".png", ".webp")
    front_bytes = None
    back_bytes = None
    other_images = []

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for file_info in z.infolist():
                if file_info.is_dir() or file_info.filename.startswith("__MACOSX"):
                    continue

                fname_lower = file_info.filename.lower()
                if fname_lower.endswith(valid_exts):
                    img_data = z.read(file_info.filename)
                    if "front" in fname_lower:
                        front_bytes = img_data
                    elif "back" in fname_lower:
                        back_bytes = img_data
                    else:
                        other_images.append(img_data)

        if not front_bytes and other_images:
            front_bytes = other_images.pop(0)
        if not back_bytes and other_images:
            back_bytes = other_images.pop(0)

        return front_bytes, back_bytes
    except Exception as e:
        logger.error(f"Failed to unzip document archive: {e}")
        return zip_bytes, None


async def _resolve_doc_images(
    client: httpx.AsyncClient,
    main_url: Optional[str],
    zip_alias_url: Optional[str],
    front_url: Optional[str],
    back_url: Optional[str],
) -> Tuple[Optional[bytes], Optional[bytes]]:
    """Downloads and unzips in memory, returning (front_image_bytes, back_image_bytes)."""
    if front_url or back_url:
        f_bytes, b_bytes = await asyncio.gather(
            _fetch_url_bytes(client, front_url),
            _fetch_url_bytes(client, back_url),
        )
        return f_bytes, b_bytes

    target_url = main_url or zip_alias_url
    if not target_url:
        return None, None

    downloaded = await _fetch_url_bytes(client, target_url)
    if not downloaded:
        return None, None

    return _extract_images_from_zip_bytes(downloaded)


@router.post("/verify-urls", summary="Verify complete driver document set from S3 pre-signed Zip or Image URLs")
async def verify_driver_urls(payload: DriverVerifyUrlsRequest):
    """
    Master Driver Verification Gateway for Cloud / S3 URLs:
    1. Downloads all document zip archives or image URLs in parallel into RAM memory (zero disk I/O).
    2. Unzips each archive in memory and auto-identifies Front and Back images.
    3. Concurrently dispatches image bytes to specialized microservices (Aadhaar, DL, PAN, RC).
    4. Cross-validates Name (fuzzy ratio) and DOB.
    5. Persists extraction and validation audit reports to disk.
    6. Returns consolidated verification result.
    """
    driver_id = payload.driver_id.strip()
    if not driver_id:
        raise HTTPException(status_code=400, detail="driver_id cannot be empty")

    try:
        # 1. Download and unzip all documents in memory concurrently
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            (
                (a_front_b, a_back_b),
                (dl_front_b, dl_back_b),
                (pan_front_b, pan_back_b),
                (rc_front_b, rc_back_b),
            ) = await asyncio.gather(
                _resolve_doc_images(
                    http_client,
                    payload.aadhaar_url,
                    payload.aadhaar_zip_url,
                    payload.aadhaar_front_url,
                    payload.aadhaar_back_url,
                ),
                _resolve_doc_images(
                    http_client,
                    payload.licence_url,
                    payload.licence_zip_url,
                    payload.licence_front_url,
                    payload.licence_back_url,
                ),
                _resolve_doc_images(
                    http_client,
                    payload.pan_url,
                    payload.pan_zip_url,
                    payload.pan_front_url,
                    payload.pan_back_url,
                ),
                _resolve_doc_images(
                    http_client,
                    payload.rc_url,
                    payload.rc_zip_url,
                    payload.rc_front_url,
                    payload.rc_back_url,
                ),
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

        # 4. Identity Cross-Validation
        val_res = await _clients.cross_verify(extraction_payload)

        # 5. Persist records to disk
        extr_dir = gateway_config.EXTRACTION_OUTPUT_DIR
        val_dir = gateway_config.VALIDATION_OUTPUT_DIR
        extr_dir.mkdir(parents=True, exist_ok=True)
        val_dir.mkdir(parents=True, exist_ok=True)

        extr_file = extr_dir / f"{driver_id}.json"
        val_file = val_dir / f"{driver_id}.json"

        with open(extr_file, "w", encoding="utf-8") as f:
            json.dump(extraction_payload, f, indent=2, ensure_ascii=False)

        with open(val_file, "w", encoding="utf-8") as f:
            json.dump(val_res, f, indent=2, ensure_ascii=False)

        ov_status = str(val_res.get("overall_status", "UNKNOWN")).upper()
        is_approved = ov_status in ("APPROVED", "MATCHED", "MATCH")

        return ApiResponse(
            success=True,
            status="SUCCESS",
            data={
                "driver_id": driver_id,
                "over_all_status": is_approved,
            }
        )

    except Exception as e:
        logger.error(f"URL driver verification failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Driver verification orchestration failed: {str(e)}")


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

        ov_status = str(val_res.get("overall_status", "UNKNOWN")).upper()
        is_approved = ov_status in ("APPROVED", "MATCHED", "MATCH")

        return ApiResponse(
            success=True,
            status="SUCCESS",
            data={
                "driver_id": driver_id,
                "over_all_status": is_approved,
            }
        )

    except Exception as e:
        logger.error(f"Master verification failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Driver verification orchestration failed: {str(e)}")


# ── Historical Records Management Endpoints ────────────────────────────────────

@router.get("/records", summary="List historical verified driver records")
async def list_driver_records(
    limit: int = Query(10, ge=1, le=500),
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
    global_approved = 0
    global_review = 0
    global_rejected = 0
    global_total = len(json_files)

    for jf in json_files:
        driver_id = jf.stem
        val_file = val_dir / f"{driver_id}.json"

        overall_status = "UNKNOWN"
        name_status = "UNKNOWN"
        dob_status = "UNKNOWN"
        val_data = None

        if val_file.exists():
            try:
                with open(val_file, "r", encoding="utf-8") as vf:
                    val_data = json.load(vf)
                    overall_status = val_data.get("overall_status", "UNKNOWN")
                    name_status = val_data.get("overall_name_status", "UNKNOWN")
                    dob_status = val_data.get("overall_dob_status", "UNKNOWN")
            except Exception:
                pass

        # Global statistics calculation across entire dataset
        s_upper = overall_status.upper()
        if s_upper in ("APPROVED", "MATCHED", "MATCH"):
            global_approved += 1
        elif s_upper == "REVIEW":
            global_review += 1
        elif s_upper in ("REJECTED", "MISMATCH", "MISMATCHED", "FAILED"):
            global_rejected += 1

        # Handle status filter (supporting both APPROVED/REJECTED and MATCHED/MISMATCH)
        if status_filter:
            norm_filter = status_filter.upper()
            if norm_filter in ("APPROVED", "MATCHED", "MATCH") and overall_status.upper() not in ("APPROVED", "MATCHED", "MATCH"):
                continue
            elif norm_filter in ("REJECTED", "MISMATCH", "MISMATCHED", "FAILED") and overall_status.upper() not in ("REJECTED", "MISMATCH", "MISMATCHED", "FAILED"):
                continue
            elif norm_filter == "REVIEW" and overall_status.upper() != "REVIEW":
                continue

        # Extract Driver Name from Aadhaar Card (primary) or DL / PAN (fallback)
        driver_name = "-"
        if jf.exists():
            try:
                with open(jf, "r", encoding="utf-8") as ef:
                    extr_data = json.load(ef)
                    docs = extr_data.get("documents", {})
                    a_name = docs.get("aadhaar", {}).get("data", {}).get("full_name")
                    if a_name and a_name.strip():
                        driver_name = a_name.strip()
                    else:
                        dl_name = docs.get("licence", {}).get("data", {}).get("full_name")
                        pan_name = docs.get("pan", {}).get("data", {}).get("full_name")
                        driver_name = dl_name or pan_name or "-"
            except Exception:
                pass

        records.append({
            "driver_id": driver_id,
            "driver_name": driver_name,
            "overall_status": overall_status,
            "name_status": name_status,
            "dob_status": dob_status,
            "validation": val_data,
            "extraction_file": str(jf.name),
        })

    paginated = records[offset : offset + limit]

    pass_rate = round((global_approved / global_total * 100), 1) if global_total > 0 else 0.0

    return ApiResponse(
        success=True,
        data={
            "total": len(records),
            "total_unfiltered": global_total,
            "limit": limit,
            "offset": offset,
            "summary": {
                "total": global_total,
                "approved": global_approved,
                "review": global_review,
                "rejected": global_rejected,
                "pass_rate": pass_rate,
            },
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
