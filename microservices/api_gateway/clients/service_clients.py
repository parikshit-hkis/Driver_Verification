"""
Downstream Microservices HTTP Clients for API Gateway
"""

import httpx
import logging
from typing import Optional, Dict, Any, Tuple
from microservices.api_gateway.config import gateway_config

logger = logging.getLogger("gateway.clients")


class ServiceClients:
    """Orchestrator client interacting with all specialized microservices over HTTP."""

    def __init__(self):
        self.ocr_url = gateway_config.OCR_SERVICE_URL.rstrip("/")
        self.aadhaar_url = gateway_config.AADHAAR_SERVICE_URL.rstrip("/")
        self.dl_url = gateway_config.DL_SERVICE_URL.rstrip("/")
        self.pan_url = gateway_config.PAN_SERVICE_URL.rstrip("/")
        self.rc_url = gateway_config.RC_SERVICE_URL.rstrip("/")
        self.validator_url = gateway_config.VALIDATOR_SERVICE_URL.rstrip("/")

    async def _post_multipart_doc(
        self,
        service_url: str,
        front_bytes: Optional[bytes],
        back_bytes: Optional[bytes],
        doc_prefix: str,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        """Generic helper to upload front and optional back images to a domain extractor microservice."""
        if not front_bytes and not back_bytes:
            return {"status": "MISSING", "warning": f"No {doc_prefix} images provided", "data": None}

        files = {}
        if front_bytes:
            files["front_image"] = (f"{doc_prefix}_front.jpg", front_bytes, "image/jpeg")
        else:
            files["front_image"] = (f"{doc_prefix}_back.jpg", back_bytes, "image/jpeg")

        if back_bytes and front_bytes:
            files["back_image"] = (f"{doc_prefix}_back.jpg", back_bytes, "image/jpeg")

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(f"{service_url}/extract", files=files)
                res.raise_for_status()
                res_json = res.json()
                return {
                    "status": res_json.get("status", "SUCCESS"),
                    "data": res_json.get("data"),
                    "warning": None,
                }
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from {service_url}: {e.response.text}")
            return {"status": "FAILED", "warning": f"Service error ({service_url}): {e.response.text}", "data": None}
        except Exception as e:
            logger.error(f"Connection error to {service_url}: {e}")
            return {"status": "FAILED", "warning": f"Connection error ({service_url}): {str(e)}", "data": None}

    async def extract_aadhaar(self, front_bytes: Optional[bytes], back_bytes: Optional[bytes]) -> Dict[str, Any]:
        return await self._post_multipart_doc(self.aadhaar_url, front_bytes, back_bytes, "aadhaar")

    async def extract_dl(self, front_bytes: Optional[bytes], back_bytes: Optional[bytes]) -> Dict[str, Any]:
        return await self._post_multipart_doc(self.dl_url, front_bytes, back_bytes, "dl")

    async def extract_pan(self, front_bytes: Optional[bytes], back_bytes: Optional[bytes]) -> Dict[str, Any]:
        return await self._post_multipart_doc(self.pan_url, front_bytes, back_bytes, "pan")

    async def extract_rc(self, front_bytes: Optional[bytes], back_bytes: Optional[bytes]) -> Dict[str, Any]:
        return await self._post_multipart_doc(self.rc_url, front_bytes, back_bytes, "rc")

    async def cross_verify(self, driver_extraction_dict: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """Send aggregated driver extraction JSON to the Validator Microservice."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(f"{self.validator_url}/cross-verify", json=driver_extraction_dict)
                res.raise_for_status()
                res_json = res.json()
                return res_json.get("data", {})
        except Exception as e:
            logger.error(f"Cross-validation error: {e}")
            return {"status": "FAILED", "error": str(e)}

    async def check_all_services_health(self) -> Dict[str, Any]:
        """Query health endpoints of all downstream services."""
        services = {
            "ocr_service": f"{self.ocr_url}/health",
            "aadhaar_service": f"{self.aadhaar_url}/health",
            "dl_service": f"{self.dl_url}/health",
            "pan_service": f"{self.pan_url}/health",
            "rc_service": f"{self.rc_url}/health",
            "validator_service": f"{self.validator_url}/health",
        }

        health_results = {}
        all_healthy = True

        async with httpx.AsyncClient(timeout=4.0) as client:
            for name, url in services.items():
                try:
                    res = await client.get(url)
                    if res.status_code == 200:
                        health_results[name] = {"status": "HEALTHY", "details": res.json()}
                    else:
                        health_results[name] = {"status": "UNHEALTHY", "status_code": res.status_code}
                        all_healthy = False
                except Exception as e:
                    health_results[name] = {"status": "UNREACHABLE", "error": str(e)}
                    all_healthy = False

        return {
            "overall_status": "HEALTHY" if all_healthy else "DEGRADED",
            "services": health_results,
        }
