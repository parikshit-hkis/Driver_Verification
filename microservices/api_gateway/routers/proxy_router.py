"""
Reverse-Proxy Router for Specialized Individual Microservices
"""

import httpx
from typing import Optional, Dict, Any
from fastapi import APIRouter, File, UploadFile, Query, HTTPException, Body
from microservices.api_gateway.config import gateway_config
from microservices.shared.responses import ApiResponse

router = APIRouter(tags=["Microservice Reverse Proxies"])


async def _proxy_multipart(
    url: str,
    files_dict: Dict[str, UploadFile],
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 60.0,
):
    upload_payload = {}
    for key, file_obj in files_dict.items():
        if file_obj:
            content = await file_obj.read()
            upload_payload[key] = (file_obj.filename or f"{key}.jpg", content, file_obj.content_type or "image/jpeg")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(url, params=params, files=upload_payload)
            res.raise_for_status()
            return res.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Proxy error connecting to {url}: {str(e)}")


@router.post("/ocr/extract", summary="Proxy to OCR Engine Microservice (Port 8001)")
async def proxy_ocr_extract(
    file: UploadFile = File(..., description="Document image file"),
    min_confidence: Optional[float] = Query(None, description="Minimum confidence threshold"),
    fix_orientation: bool = Query(True),
    enhance: bool = Query(True),
):
    url = f"{gateway_config.OCR_SERVICE_URL.rstrip('/')}/extract"
    params = {"fix_orientation": fix_orientation, "enhance": enhance}
    if min_confidence is not None:
        params["min_confidence"] = min_confidence
    return await _proxy_multipart(url, {"file": file}, params=params)


@router.post("/aadhaar/extract", summary="Proxy to Aadhaar Microservice (Port 8002)")
async def proxy_aadhaar_extract(
    front_image: UploadFile = File(..., description="Aadhaar front image"),
    back_image: Optional[UploadFile] = File(None, description="Optional Aadhaar back image"),
):
    url = f"{gateway_config.AADHAAR_SERVICE_URL.rstrip('/')}/extract"
    return await _proxy_multipart(url, {"front_image": front_image, "back_image": back_image})


@router.post("/dl/extract", summary="Proxy to Driving Licence Microservice (Port 8003)")
async def proxy_dl_extract(
    front_image: UploadFile = File(..., description="Driving Licence front image"),
    back_image: Optional[UploadFile] = File(None, description="Optional Driving Licence back image"),
):
    url = f"{gateway_config.DL_SERVICE_URL.rstrip('/')}/extract"
    return await _proxy_multipart(url, {"front_image": front_image, "back_image": back_image})


@router.post("/pan/extract", summary="Proxy to PAN Microservice (Port 8004)")
async def proxy_pan_extract(
    front_image: UploadFile = File(..., description="PAN Card front image"),
    back_image: Optional[UploadFile] = File(None, description="Optional PAN Card back image"),
):
    url = f"{gateway_config.PAN_SERVICE_URL.rstrip('/')}/extract"
    return await _proxy_multipart(url, {"front_image": front_image, "back_image": back_image})


@router.post("/rc/extract", summary="Proxy to RC Microservice (Port 8005)")
async def proxy_rc_extract(
    front_image: UploadFile = File(..., description="RC front image"),
    back_image: Optional[UploadFile] = File(None, description="Optional RC back image"),
):
    url = f"{gateway_config.RC_SERVICE_URL.rstrip('/')}/extract"
    return await _proxy_multipart(url, {"front_image": front_image, "back_image": back_image})


@router.post("/validate/cross-verify", summary="Proxy to Validator Microservice (Port 8006)")
async def proxy_validate_cross_verify(payload: Dict[str, Any] = Body(...)):
    url = f"{gateway_config.VALIDATOR_SERVICE_URL.rstrip('/')}/cross-verify"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            return res.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Proxy error connecting to validator: {str(e)}")
