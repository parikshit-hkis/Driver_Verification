"""
Driver Verification Data Models
================================
Defines data structures for driver-level document extraction results.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Union, List, Dict, Any

from app.services.doc_type_detector import DocumentType
from app.models.ocr_models import ImageQualityReport, OCRResult
from app.services.aadhaar_extractor.models import AadhaarData
from app.services.pan_extractor.models import PanData
from app.services.driving_license_extractor.models import DrivingLicenceData
from app.services.rc_extractor.models import RCData


DocumentData = Union[AadhaarData, PanData, DrivingLicenceData, RCData, None]


@dataclass
class DocumentExtractionResult:
    """Extraction result for a single document (front + back merged)."""
    document_type: DocumentType
    data: DocumentData = None
    front_quality: Optional[ImageQualityReport] = None
    back_quality: Optional[ImageQualityReport] = None
    front_ocr: Optional[OCRResult] = None
    back_ocr: Optional[OCRResult] = None
    status: str = "MISSING"  # "EXTRACTED", "PARTIAL", "MISSING", "FAILED"
    warning: Optional[str] = None
    front_path: Optional[str] = None
    back_path: Optional[str] = None

    def display(self) -> str:
        lines = []
        if self.status == "EXTRACTED":
            lines.append("  [OK] extracted")
        elif self.status == "PARTIAL":
            lines.append("  [!] partial extraction")
        elif self.status == "FAILED":
            lines.append("  [X] extraction failed")
        else:
            lines.append("  [-] missing")

        if self.warning:
            lines.append(f"  ({self.warning})")

        # Show image quality warnings
        for label, report in [("Front", self.front_quality), ("Back", self.back_quality)]:
            if report and report.warnings:
                for w in report.warnings:
                    lines.append(f"  [!] {label}: {w}")

        if self.data is not None:
            lines.append(self.data.display())

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        data_dict = None
        if self.data is not None:
            if hasattr(self.data, "model_dump"):
                data_dict = self.data.model_dump()
            elif hasattr(self.data, "dict"):
                data_dict = self.data.dict()
            elif hasattr(self.data, "__dict__"):
                data_dict = dict(self.data.__dict__)
        return {
            "document_type": self.document_type.value if hasattr(self.document_type, "value") else str(self.document_type),
            "status": self.status,
            "warning": self.warning,
            "data": data_dict,
        }


@dataclass
class DriverVerificationResult:
    """Consolidated verification result for a single driver."""
    driver_id: str
    aadhaar_result: Optional[DocumentExtractionResult] = None
    licence_result: Optional[DocumentExtractionResult] = None
    pan_result: Optional[DocumentExtractionResult] = None
    rc_result: Optional[DocumentExtractionResult] = None

    def display(self, detailed: bool = True) -> str:
        """Format human-readable summary of driver verification."""
        sep = "=" * 55
        thin_sep = "-" * 55

        lines = [
            "",
            sep,
            f"Driver : {self.driver_id}",
            thin_sep,
        ]

        doc_results = [
            ("AADHAAR", self.aadhaar_result),
            ("LICENCE", self.licence_result),
            ("PAN", self.pan_result),
            ("RC", self.rc_result),
        ]

        for label, res in doc_results:
            lines.append(f"\n{label}")
            if res is None or res.status == "MISSING":
                lines.append("  [—] missing")
            elif res.status == "EXTRACTED":
                lines.append("  [OK] extracted")
                if detailed and res.data is not None:
                    lines.append(res.data.display())
            elif res.status == "PARTIAL":
                lines.append("  [!] partial extraction")
                if res.warning:
                    lines.append(f"      Warning: {res.warning}")
                if detailed and res.data is not None:
                    lines.append(res.data.display())
            elif res.status == "FAILED":
                lines.append("  [X] failed")
                if res.warning:
                    lines.append(f"      Error: {res.warning}")

        lines.append("")
        lines.append(sep)
        lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to serializable dictionary."""
        return {
            "driver_id": self.driver_id,
            "documents": {
                "aadhaar": self.aadhaar_result.to_dict() if self.aadhaar_result else None,
                "licence": self.licence_result.to_dict() if self.licence_result else None,
                "pan": self.pan_result.to_dict() if self.pan_result else None,
                "rc": self.rc_result.to_dict() if self.rc_result else None,
            }
        }

    def save_json(self, output_dir: str = "result/extr_result") -> str:
        """
        Store output of extracted details of driver into a JSON file with driver number.
        File is saved as: {output_dir}/{driver_id}.json
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        file_path = out_path / f"{self.driver_id}.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

        return str(file_path)
