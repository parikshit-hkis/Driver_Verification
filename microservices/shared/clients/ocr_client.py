"""
Shared OCR HTTP Client for Downstream Extractor Microservices
"""

import httpx
from typing import Optional, Tuple
from microservices.shared.models import OCRResult, ImageQualityReport, OCRText, BoundingBox, Point


class OCRClient:
    """Client for communicating with the standalone OCR Microservice (Port 8001)."""

    def __init__(self, ocr_service_url: str = "http://127.0.0.1:8001"):
        self.ocr_service_url = ocr_service_url.rstrip("/")

    async def extract_ocr(
        self,
        image_bytes: bytes,
        filename: str = "document.jpg",
        min_confidence: Optional[float] = None,
        fix_orientation: bool = True,
        enhance: bool = True,
        timeout: float = 60.0,
    ) -> Tuple[OCRResult, ImageQualityReport]:
        """Send image bytes to the OCR Microservice and receive parsed OCRResult & ImageQualityReport."""
        params = {
            "fix_orientation": fix_orientation,
            "enhance": enhance,
        }
        if min_confidence is not None:
            params["min_confidence"] = min_confidence

        files = {
            "file": (filename, image_bytes, "image/jpeg")
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.ocr_service_url}/extract",
                params=params,
                files=files,
            )
            response.raise_for_status()
            res_json = response.json()

            data = res_json.get("data", {})
            ocr_dict = data.get("ocr_result", {})
            quality_dict = data.get("quality_report", {})

            ocr_result = OCRResult(**ocr_dict)
            quality_report = ImageQualityReport(**quality_dict)

            return ocr_result, quality_report

    async def is_healthy(self) -> bool:
        """Check if the OCR service is reachable and healthy."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.ocr_service_url}/health")
                return res.status_code == 200 and res.json().get("status") == "HEALTHY"
        except Exception:
            return False
