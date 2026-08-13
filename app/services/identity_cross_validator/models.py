"""
Identity Cross-Validation Models
================================
Defines data structures for pairwise and overall identity validation results.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class NameValidationResult:
    doc1_key: str
    doc2_key: str
    doc1_name: Optional[str]
    doc2_name: Optional[str]
    similarity: float
    status: str  # "MATCH", "REVIEW", "MISMATCH", "MISSING"

    def to_dict(self) -> Dict[str, Any]:
        return {
            self.doc1_key: self.doc1_name or "",
            self.doc2_key: self.doc2_name or "",
            "similarity": round(self.similarity, 2),
            "status": self.status,
        }


@dataclass
class DobValidationResult:
    doc1_key: str
    doc2_key: str
    doc1_dob: Optional[str]
    doc2_dob: Optional[str]
    status: str  # "MATCH", "MISMATCH", "MISSING"

    def to_dict(self) -> Dict[str, Any]:
        return {
            self.doc1_key: self.doc1_dob or "",
            self.doc2_key: self.doc2_dob or "",
            "status": self.status,
        }


@dataclass
class PairwiseValidationResult:
    name: NameValidationResult
    date_of_birth: DobValidationResult
    status: str  # "MATCH", "REVIEW", "MISMATCH", "MISSING"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name.to_dict(),
            "date_of_birth": self.date_of_birth.to_dict(),
            "status": self.status,
        }


@dataclass
class DriverCrossValidationResult:
    driver_id: str
    aadhaar_vs_pan: PairwiseValidationResult
    aadhaar_vs_licence: PairwiseValidationResult
    pan_vs_licence: PairwiseValidationResult
    overall_status: str  # "MATCHED", "REVIEW", "MISMATCH"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "driver_id": self.driver_id,
            "validation": {
                "aadhaar_vs_pan": self.aadhaar_vs_pan.to_dict(),
                "aadhaar_vs_licence": self.aadhaar_vs_licence.to_dict(),
                "pan_vs_licence": self.pan_vs_licence.to_dict(),
                "overall_status": self.overall_status,
            }
        }

    def save_json(self, output_dir: str = "result/vldt_result") -> str:
        """Save validation result to result/vldt_result/{driver_id}.json."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        file_path = out_path / f"{self.driver_id}.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

        return str(file_path)
