"""
Identity Cross-Validator Service
================================
Compares extracted identity details (Full Name and Date of Birth) between
Aadhaar, Driving Licence, and PAN documents.

Consumes extraction JSON files from `result/extr_result/<driver_id>.json`
and writes validation results to `result/vldt_result/<driver_id>.json`.
"""

import re
import json
from pathlib import Path
from typing import Optional, Dict, Any

from rapidfuzz import fuzz
from app.services.identity_cross_validator.config import cross_validator_config
from app.services.identity_cross_validator.models import (
    NameValidationResult,
    DobValidationResult,
    PairwiseValidationResult,
    DriverCrossValidationResult,
)


class IdentityCrossValidator:
    """Validates extracted identity details across Aadhaar, PAN, and Driving Licence."""

    def __init__(
        self,
        name_match_threshold: float | None = None,
        name_review_threshold: float | None = None,
    ):
        self.name_match_threshold = (
            name_match_threshold
            if name_match_threshold is not None
            else cross_validator_config.NAME_MATCH_THRESHOLD
        )
        self.name_review_threshold = (
            name_review_threshold
            if name_review_threshold is not None
            else cross_validator_config.NAME_REVIEW_THRESHOLD
        )

    @staticmethod
    def normalize_name(name: Optional[str]) -> str:
        """
        Normalize a name string before fuzzy comparison:
          1. Convert to uppercase
          2. Remove punctuation
          3. Collapse repeated whitespace
          4. Strip whitespace
        """
        if not name:
            return ""
        clean = name.upper()
        clean = re.sub(r"[^\w\s]", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        Calculate fuzzy similarity percentage between two normalized names.
        Uses RapidFuzz token_sort_ratio to evaluate token similarity.
        """
        norm1 = self.normalize_name(name1)
        norm2 = self.normalize_name(name2)

        if not norm1 or not norm2:
            return 0.0

        if norm1 == norm2:
            return 100.0

        # RapidFuzz similarity percentage (0.0 to 100.0)
        similarity = float(fuzz.token_sort_ratio(norm1, norm2))
        return round(similarity, 2)

    def validate_name_pair(self,doc1_key: str,doc2_key: str,name1: Optional[str],name2: Optional[str],) -> NameValidationResult:
        """Evaluate name similarity and status for a document pair."""
        norm1 = self.normalize_name(name1)
        norm2 = self.normalize_name(name2)

        if not norm1 or not norm2:
            status = "MISSING" if (not norm1 and not norm2) else "MISMATCH"
            return NameValidationResult(
                doc1_key=doc1_key,
                doc2_key=doc2_key,
                doc1_name=norm1,
                doc2_name=norm2,
                similarity=0.0,
                status=status,
            )

        similarity = self.calculate_name_similarity(norm1, norm2)

        if similarity >= self.name_match_threshold:
            status = "MATCH"
        elif similarity >= self.name_review_threshold:
            status = "REVIEW"
        else:
            status = "MISMATCH"

        return NameValidationResult(
            doc1_key=doc1_key,
            doc2_key=doc2_key,
            doc1_name=norm1,
            doc2_name=norm2,
            similarity=similarity,
            status=status,
        )

    def validate_dob_pair(self,doc1_key: str,doc2_key: str,dob1: Optional[str],dob2: Optional[str],) -> DobValidationResult:
        """Evaluate exact DOB match for a document pair."""
        d1 = dob1.strip() if dob1 else ""
        d2 = dob2.strip() if dob2 else ""

        if not d1 or not d2:
            status = "MISSING" if (not d1 and not d2) else "MISMATCH"
            return DobValidationResult(
                doc1_key=doc1_key,
                doc2_key=doc2_key,
                doc1_dob=d1,
                doc2_dob=d2,
                status=status,
            )

        status = "MATCH" if d1 == d2 else "MISMATCH"

        return DobValidationResult(
            doc1_key=doc1_key,
            doc2_key=doc2_key,
            doc1_dob=d1,
            doc2_dob=d2,
            status=status,
        )

    def validate_pair(
        self,
        doc1_key: str,
        doc2_key: str,
        name1: Optional[str],
        dob1: Optional[str],
        name2: Optional[str],
        dob2: Optional[str],
    ) -> PairwiseValidationResult:
        """Combine name and DOB validation for a document pair."""
        name_res = self.validate_name_pair(doc1_key, doc2_key, name1, name2)
        dob_res = self.validate_dob_pair(doc1_key, doc2_key, dob1, dob2)

        # Pairwise Status Determination
        if dob_res.status == "MISMATCH" or name_res.status == "MISMATCH":
            pair_status = "MISMATCH"
        elif name_res.status == "REVIEW":
            pair_status = "REVIEW"
        elif name_res.status == "MATCH" and dob_res.status == "MATCH":
            pair_status = "MATCH"
        else:
            pair_status = "MISMATCH"

        return PairwiseValidationResult(
            name=name_res,
            date_of_birth=dob_res,
            status=pair_status,
        )

    def validate_driver_json(self, json_dict: Dict[str, Any]) -> DriverCrossValidationResult:
        """Perform cross-validation on an extracted driver JSON dictionary."""
        driver_id = str(json_dict.get("driver_id", "UNKNOWN"))
        docs = json_dict.get("documents", {})

        def get_field(doc_type: str, field_name: str) -> Optional[str]:
            doc = docs.get(doc_type) or {}
            data = doc.get("data") or {}
            val = data.get(field_name)
            return str(val) if val is not None else None

        a_name = get_field("aadhaar", "full_name")
        a_dob = get_field("aadhaar", "date_of_birth")

        p_name = get_field("pan", "full_name")
        p_dob = get_field("pan", "date_of_birth")

        l_name = get_field("licence", "full_name")
        l_dob = get_field("licence", "date_of_birth")

        # 1. Aadhaar ↔ PAN
        aadhaar_vs_pan = self.validate_pair("aadhaar", "pan", a_name, a_dob, p_name, p_dob)

        # 2. Aadhaar ↔ Licence
        aadhaar_vs_licence = self.validate_pair("aadhaar", "licence", a_name, a_dob, l_name, l_dob)

        # 3. PAN ↔ Licence
        pan_vs_licence = self.validate_pair("pan", "licence", p_name, p_dob, l_name, l_dob)

        # Overall Status Determination
        pairs = [aadhaar_vs_pan, aadhaar_vs_licence, pan_vs_licence]

        # 1. Overall Name Status across all document pairs
        if any(p.name.status in ("MISMATCH", "MISSING") for p in pairs):
            overall_name_status = "MISMATCH"
        elif any(p.name.status == "REVIEW" for p in pairs):
            overall_name_status = "REVIEW"
        elif all(p.name.status == "MATCH" for p in pairs):
            overall_name_status = "MATCHED"
        else:
            overall_name_status = "MISMATCH"

        # 2. Overall DOB Status across all document pairs
        if any(p.date_of_birth.status in ("MISMATCH", "MISSING") for p in pairs):
            overall_dob_status = "MISMATCH"
        elif all(p.date_of_birth.status == "MATCH" for p in pairs):
            overall_dob_status = "MATCHED"
        else:
            overall_dob_status = "MISMATCH"

        # 3. Overall Identity Status
        if overall_name_status == "MISMATCH" or overall_dob_status == "MISMATCH":
            overall_status = "MISMATCH"
        elif overall_name_status == "REVIEW":
            overall_status = "REVIEW"
        elif overall_name_status == "MATCHED" and overall_dob_status == "MATCHED":
            overall_status = "MATCHED"
        else:
            overall_status = "MISMATCH"

        return DriverCrossValidationResult(
            driver_id=driver_id,
            aadhaar_vs_pan=aadhaar_vs_pan,
            aadhaar_vs_licence=aadhaar_vs_licence,
            pan_vs_licence=pan_vs_licence,
            overall_name_status=overall_name_status,
            overall_dob_status=overall_dob_status,
            overall_status=overall_status,
        )

    def validate_file(self, json_file_path: str, output_dir: str | None = None) -> DriverCrossValidationResult:
        """Read extraction JSON file from result/extr_result and save validation JSON to output_dir."""
        target_output_dir = output_dir or cross_validator_config.DEFAULT_VALIDATION_DIR
        path = Path(json_file_path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        result = self.validate_driver_json(data)
        result.save_json(target_output_dir)
        return result
