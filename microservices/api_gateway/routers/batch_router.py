import os
import json
import uuid
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Form, Query, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import httpx

from microservices.api_gateway.config import gateway_config
from microservices.api_gateway.clients.service_clients import ServiceClients
from microservices.api_gateway.routers.driver_router import _resolve_doc_images
from microservices.shared.responses import ApiResponse

logger = logging.getLogger("gateway.batch_router")
router = APIRouter(prefix="/batch", tags=["Batch Verification & Analytics"])

_clients = ServiceClients()
_SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}

# In-memory batch job tracking
_active_batches: Dict[str, Dict[str, Any]] = {}


class DriverUrlItem(BaseModel):
    driver_id: str = Field(..., description="Unique driver ID (phone number or UUID)")
    mobile_number: Optional[str] = Field(None, description="Driver mobile number (used as password for protected zip archives)")
    password: Optional[str] = Field(None, description="Alias for mobile_number password")
    vehicle_class: Optional[str] = Field(None, description="Expected vehicle class: '2 wheeler', '3 wheeler', 'car', 'truck'")
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


class BatchVerifyUrlsRequest(BaseModel):
    batch_id: Optional[str] = Field(None, description="Optional batch identifier (auto-generated if omitted)")
    concurrency: int = Field(4, ge=1, le=16, description="Parallel worker concurrency limit (default: 4)")
    drivers: List[DriverUrlItem] = Field(..., description="List of driver items containing document URLs")


def _scan_driver_folder_images(folder: Path) -> Dict[str, Dict[str, Optional[bytes]]]:
    """
    Scans a driver folder (supporting document subfolders and flat files)
    and pairs front/back images for aadhaar, dl, pan, rc.
    """
    docs = {
        "aadhaar": {"front": None, "back": None},
        "licence": {"front": None, "back": None},
        "pan": {"front": None, "back": None},
        "rc": {"front": None, "back": None},
    }

    # 1. Check document-specific subfolders (e.g. adhaar_card, driving_license, pan_card, rc_book)
    for sub in folder.iterdir():
        if sub.is_dir():
            name = sub.name.lower()
            dtype = None
            if any(k in name for k in ["aadhaar", "aadhar", "adhaar", "uid"]):
                dtype = "aadhaar"
            elif any(k in name for k in ["driving_license", "licence", "license", "dl"]):
                dtype = "licence"
            elif any(k in name for k in ["pan_card", "pan", "pancard"]):
                dtype = "pan"
            elif any(k in name for k in ["rc_book", "rc", "registration", "vehicle"]):
                dtype = "rc"

            if dtype:
                imgs = sorted([p for p in sub.glob("*") if p.suffix.lower() in _SUPPORTED_IMAGE_EXTS])
                if len(imgs) >= 1:
                    try:
                        docs[dtype]["front"] = imgs[0].read_bytes()
                    except Exception as e:
                        logger.warning(f"Failed to read {imgs[0]}: {e}")
                if len(imgs) >= 2:
                    try:
                        docs[dtype]["back"] = imgs[1].read_bytes()
                    except Exception as e:
                        logger.warning(f"Failed to read {imgs[1]}: {e}")

    # 2. Also check direct files in driver folder if subfolders were not present
    for f in folder.glob("*"):
        if f.is_file() and f.suffix.lower() in _SUPPORTED_IMAGE_EXTS:
            name = f.stem.lower()
            for dtype, keywords in [
                ("aadhaar", ["aadhaar", "aadhar", "adhaar", "uid"]),
                ("licence", ["dl", "licence", "license", "driving"]),
                ("pan", ["pan"]),
                ("rc", ["rc", "registration"]),
            ]:
                if any(k in name for k in keywords):
                    if not docs[dtype]["front"]:
                        try:
                            docs[dtype]["front"] = f.read_bytes()
                        except Exception as e:
                            logger.warning(f"Failed to read {f}: {e}")
                    elif not docs[dtype]["back"]:
                        try:
                            docs[dtype]["back"] = f.read_bytes()
                        except Exception as e:
                            logger.warning(f"Failed to read {f}: {e}")

    return docs


async def _extract_single_driver_spec(driver_id: str, docs: Dict[str, Dict[str, Optional[bytes]]]) -> Dict[str, Any]:
    """Process and extract all documents for a single driver in parallel, then save to result/extraction/."""
    aadhaar_task = _clients.extract_aadhaar(docs["aadhaar"]["front"], docs["aadhaar"]["back"])
    dl_task = _clients.extract_dl(docs["licence"]["front"], docs["licence"]["back"])
    pan_task = _clients.extract_pan(docs["pan"]["front"], docs["pan"]["back"])
    rc_task = _clients.extract_rc(docs["rc"]["front"], docs["rc"]["back"])

    aadhaar_res, dl_res, pan_res, rc_res = await asyncio.gather(
        aadhaar_task, dl_task, pan_task, rc_task
    )

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
        },
    }

    # Save extraction JSON to disk
    extr_dir = gateway_config.EXTRACTION_OUTPUT_DIR
    extr_dir.mkdir(parents=True, exist_ok=True)
    extr_file = extr_dir / f"{driver_id}.json"
    with open(extr_file, "w", encoding="utf-8") as f:
        json.dump(extraction_payload, f, indent=2, ensure_ascii=False)

    return extraction_payload


@router.post("/verify-folder", summary="Trigger bulk driver document verification from a local directory")
async def verify_folder_batch(
    folder_path: str = Form("sample_documents", description="Relative or absolute path to driver directories folder"),
    concurrency: int = Form(1, ge=1, le=4, description="Concurrent driver processing batch size"),
):
    """
    Master Bulk Batch Verification API (2-Stage Optimized Pipeline):
    1. STAGE 1 (Extraction): Scans driver directories and runs OCR/domain extraction concurrently.
       Saves all raw extraction JSONs to result/extraction/{driver_id}.json.
    2. STAGE 2 (Bulk Validation): Sends all extracted payloads to Validator Microservice in ONE single
       HTTP batch call (/batch-cross-verify), executing rapid in-memory fuzzy matching and DOB validation.
    3. STAGE 3 (Persistence & Analytics): Saves result/validation/{driver_id}.json and returns unified analytics.
    """
    target_path = Path(folder_path)
    if not target_path.is_absolute():
        target_path = Path(os.getcwd()) / target_path

    if not target_path.exists() or not target_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory '{folder_path}' not found")

    driver_folders = [p for p in sorted(target_path.iterdir()) if p.is_dir() and not p.name.startswith(".")]

    if not driver_folders:
        return ApiResponse(
            success=True,
            status="SUCCESS",
            data={
                "total_drivers": 0,
                "completed": 0,
                "summary": {"matched": 0, "review": 0, "mismatch": 0},
                "drivers": [],
            },
        )

    logger.info(f"Starting 2-Stage Batch Verification on {len(driver_folders)} drivers in {target_path} (concurrency={concurrency})")

    # ── STAGE 1: Parallel Extraction & Persistence ────────────────────────────
    sem = asyncio.Semaphore(concurrency)

    async def _extraction_worker(d_folder: Path) -> Dict[str, Any]:
        driver_id = d_folder.name
        async with sem:
            try:
                docs = _scan_driver_folder_images(d_folder)
                extr_payload = await _extract_single_driver_spec(driver_id, docs)
                return extr_payload
            except Exception as e:
                logger.error(f"Error extracting driver {driver_id}: {e}", exc_info=True)
                return {
                    "driver_id": driver_id,
                    "error": str(e),
                    "documents": {},
                }

    extraction_tasks = [_extraction_worker(df) for df in driver_folders]
    all_extractions = await asyncio.gather(*extraction_tasks)

    # ── STAGE 2: Bulk Cross-Validation (1 Single HTTP Call) ───────────────────
    valid_extractions = [ex for ex in all_extractions if "error" not in ex]
    logger.info(f"Sending {len(valid_extractions)} extracted drivers to Validator in a single batch call...")
    
    validation_map = {}
    if valid_extractions:
        validation_map = await _clients.batch_cross_verify(valid_extractions)

    # ── STAGE 3: Persist Validation JSON & Build Unified Driver Summaries ─────
    val_dir = gateway_config.VALIDATION_OUTPUT_DIR
    val_dir.mkdir(parents=True, exist_ok=True)

    results = []
    stats = {"MATCHED": 0, "REVIEW": 0, "MISMATCH": 0, "FAILED": 0}

    for extraction in all_extractions:
        driver_id = extraction.get("driver_id", "UNKNOWN")
        if "error" in extraction:
            stats["FAILED"] += 1
            results.append({
                "driver_id": driver_id,
                "overall_status": "FAILED",
                "overall_name_status": "FAILED",
                "overall_dob_status": "FAILED",
                "error": extraction.get("error"),
            })
            continue

        val_res = validation_map.get(driver_id, {
            "driver_id": driver_id,
            "overall_status": "UNKNOWN",
            "overall_name_status": "UNKNOWN",
            "overall_dob_status": "UNKNOWN",
        })

        # Save individual validation JSON
        val_file = val_dir / f"{driver_id}.json"
        with open(val_file, "w", encoding="utf-8") as f:
            json.dump(val_res, f, indent=2, ensure_ascii=False)

        docs = extraction.get("documents", {})
        aadhaar_data = (docs.get("aadhaar") or {}).get("data") or {}
        dl_data = (docs.get("licence") or {}).get("data") or {}
        pan_data = (docs.get("pan") or {}).get("data") or {}
        rc_data = (docs.get("rc") or {}).get("data") or {}

        st = val_res.get("overall_status", "UNKNOWN").upper()
        if st in stats:
            stats[st] += 1
        else:
            stats["FAILED"] += 1

        results.append({
            "driver_id": driver_id,
            "overall_status": val_res.get("overall_status", "UNKNOWN"),
            "overall_name_status": val_res.get("overall_name_status", "UNKNOWN"),
            "overall_dob_status": val_res.get("overall_dob_status", "UNKNOWN"),
            "extracted_name": (
                aadhaar_data.get("full_name")
                or dl_data.get("full_name")
                or pan_data.get("full_name")
            ),
            "licence_number": dl_data.get("licence_number"),
            "vehicle_classes": dl_data.get("vehicle_classes", []),
            "rc_number": rc_data.get("registration_number"),
        })

    return ApiResponse(
        success=True,
        status="SUCCESS",
        data={
            "total_drivers": len(results),
            "completed": len(results),
            "statistics": stats,
            "drivers": results,
        },
    )


@router.get("/summary", summary="Get aggregate analytics across all historical verified drivers")
async def get_batch_summary():
    """Returns analytics and stats across all stored validation results."""
    val_dir = gateway_config.VALIDATION_OUTPUT_DIR
    if not val_dir.exists():
        return ApiResponse(success=True, data={"total": 0, "statistics": {}})

    val_files = list(val_dir.glob("*.json"))
    total = len(val_files)

    stats = {
        "overall_status": {"MATCHED": 0, "REVIEW": 0, "MISMATCH": 0, "UNKNOWN": 0},
        "name_status": {"MATCHED": 0, "REVIEW": 0, "MISMATCH": 0, "UNKNOWN": 0},
        "dob_status": {"MATCHED": 0, "MISMATCH": 0, "UNKNOWN": 0},
    }

    for vf in val_files:
        try:
            with open(vf, "r", encoding="utf-8") as f:
                data = json.load(f)
                ov = data.get("overall_status", "UNKNOWN").upper()
                nm = data.get("overall_name_status", "UNKNOWN").upper()
                db = data.get("overall_dob_status", "UNKNOWN").upper()

                stats["overall_status"][ov] = stats["overall_status"].get(ov, 0) + 1
                stats["name_status"][nm] = stats["name_status"].get(nm, 0) + 1
                stats["dob_status"][db] = stats["dob_status"].get(db, 0) + 1
        except Exception:
            pass

    return ApiResponse(
        success=True,
        data={
            "total_verified_drivers": total,
            "statistics": stats,
        },
    )


# ── Bulk URL / S3 Background Processing Endpoints ──────────────────────────────

async def _process_single_url_driver(http_client: httpx.AsyncClient, item: DriverUrlItem) -> Dict[str, Any]:
    """Processes a single driver item from S3/remote URLs in memory and saves audit files."""
    driver_id = item.driver_id.strip()
    zip_pwd = (
        (item.mobile_number and item.mobile_number.strip())
        or (item.password and item.password.strip())
        or (driver_id if driver_id.isdigit() else None)
    )
    
    # 1. Download & Unzip all documents in parallel
    (
        (a_front_b, a_back_b),
        (dl_front_b, dl_back_b),
        (pan_front_b, pan_back_b),
        (rc_front_b, rc_back_b),
    ) = await asyncio.gather(
        _resolve_doc_images(
            http_client,
            item.aadhaar_url,
            item.aadhaar_zip_url,
            item.aadhaar_front_url,
            item.aadhaar_back_url,
            password=zip_pwd,
        ),
        _resolve_doc_images(
            http_client,
            item.licence_url,
            item.licence_zip_url,
            item.licence_front_url,
            item.licence_back_url,
            password=zip_pwd,
        ),
        _resolve_doc_images(
            http_client,
            item.pan_url,
            item.pan_zip_url,
            item.pan_front_url,
            item.pan_back_url,
            password=zip_pwd,
        ),
        _resolve_doc_images(
            http_client,
            item.rc_url,
            item.rc_zip_url,
            item.rc_front_url,
            item.rc_back_url,
            password=zip_pwd,
        ),
    )

    # 2. Concurrently extract data via microservices
    aadhaar_task = _clients.extract_aadhaar(a_front_b, a_back_b)
    dl_task = _clients.extract_dl(dl_front_b, dl_back_b)
    pan_task = _clients.extract_pan(pan_front_b, pan_back_b)
    rc_task = _clients.extract_rc(rc_front_b, rc_back_b)

    aadhaar_res, dl_res, pan_res, rc_res = await asyncio.gather(
        aadhaar_task, dl_task, pan_task, rc_task
    )

    # 3. Assemble extraction payload
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

    # 4. Cross-Validation
    val_res = await _clients.cross_verify(extraction_payload)

    # 5. Persist JSON reports to disk
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

    ov_status = val_res.get("overall_status", "UNKNOWN")
    return {
        "driver_id": driver_id,
        "overall_status": ov_status,
        "overall_name_status": val_res.get("overall_name_status", "UNKNOWN"),
        "overall_dob_status": val_res.get("overall_dob_status", "UNKNOWN"),
        "extraction": extraction_payload,
        "cross_validation": val_res,
    }


async def _run_batch_worker_pool(batch_id: str, drivers: List[DriverUrlItem], concurrency: int):
    """Background worker pool executing batch driver URL verifications with controlled concurrency."""
    logger.info(f"Starting background batch '{batch_id}' with {len(drivers)} drivers (concurrency={concurrency})")
    sem = asyncio.Semaphore(concurrency)
    batch_entry = _active_batches.get(batch_id)
    if not batch_entry:
        return

    batch_entry["status"] = "PROCESSING"
    batch_entry["started_at"] = time.time()

    async with httpx.AsyncClient(timeout=60.0) as http_client:
        async def _worker(item: DriverUrlItem):
            async with sem:
                try:
                    res = await _process_single_url_driver(http_client, item)
                    status_upper = str(res.get("overall_status", "UNKNOWN")).upper()
                    
                    is_approved = status_upper in ("APPROVED", "MATCHED", "MATCH")
                    if is_approved:
                        batch_entry["summary"]["approved"] += 1
                    elif status_upper == "REVIEW":
                        batch_entry["summary"]["review"] += 1
                    else:
                        batch_entry["summary"]["rejected"] += 1

                    batch_entry["results"].append({
                        "driver_id": item.driver_id,
                        "over_all_status": is_approved,
                    })
                except Exception as e:
                    logger.error(f"Batch driver verification failed for {item.driver_id}: {e}", exc_info=True)
                    batch_entry["summary"]["rejected"] += 1
                    batch_entry["summary"]["errors"] += 1
                    batch_entry["results"].append({
                        "driver_id": item.driver_id,
                        "over_all_status": False,
                    })
                finally:
                    batch_entry["completed_count"] += 1
                    batch_entry["progress_pct"] = round(
                        (batch_entry["completed_count"] / batch_entry["total_drivers"]) * 100, 1
                    )

        tasks = [_worker(d) for d in drivers]
        await asyncio.gather(*tasks)

    batch_entry["status"] = "COMPLETED"
    batch_entry["completed_at"] = time.time()
    batch_entry["elapsed_sec"] = round(batch_entry["completed_at"] - batch_entry["started_at"], 2)
    logger.info(f"Batch '{batch_id}' completed {batch_entry['completed_count']}/{batch_entry['total_drivers']} in {batch_entry['elapsed_sec']}s")


@router.post("/verify-urls", summary="Submit bulk driver verification from S3 Zip / Image URLs (Background Job)")
async def submit_batch_verify_urls(payload: BatchVerifyUrlsRequest):
    """
    Submits a batch of 1 to 500 drivers with S3 Zip/Image URLs for background verification.
    Returns immediately (< 50ms) with a batch_id.
    Clients poll GET /api/v1/batch/status/{batch_id} for live progress and results.
    """
    if not payload.drivers:
        raise HTTPException(status_code=400, detail="Drivers list cannot be empty")

    batch_id = payload.batch_id.strip() if payload.batch_id and payload.batch_id.strip() else f"batch_{uuid.uuid4().hex[:10]}"

    _active_batches[batch_id] = {
        "batch_id": batch_id,
        "status": "QUEUED",
        "total_drivers": len(payload.drivers),
        "completed_count": 0,
        "progress_pct": 0.0,
        "concurrency": payload.concurrency,
        "started_at": None,
        "completed_at": None,
        "elapsed_sec": None,
        "summary": {
            "approved": 0,
            "review": 0,
            "rejected": 0,
            "errors": 0,
        },
        "results": [],
    }

    # Launch background task
    asyncio.create_task(_run_batch_worker_pool(batch_id, payload.drivers, payload.concurrency))

    return ApiResponse(
        success=True,
        status="ACCEPTED",
        message=f"Batch '{batch_id}' queued with {len(payload.drivers)} drivers for background processing",
        data={
            "batch_id": batch_id,
            "total_drivers": len(payload.drivers),
            "concurrency": payload.concurrency,
            "status_url": f"/api/v1/batch/status/{batch_id}",
            "poll_interval_sec": 3,
        },
    )


@router.get("/status/{batch_id}", summary="Poll status and live progress of a URL batch verification job")
async def get_batch_job_status(batch_id: str):
    """Returns the live execution state, progress percentage, summary statistics, and processed results."""
    batch_entry = _active_batches.get(batch_id)
    if not batch_entry:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")

    return ApiResponse(
        success=True,
        status=batch_entry["status"],
        data=batch_entry,
    )
