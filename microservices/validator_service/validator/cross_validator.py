"""
Identity Cross-Validator Service Logic
"""

import re
import json
from pathlib import Path
from typing import Optional, Dict, Any
from rapidfuzz import fuzz

from microservices.shared.models import (
    NameMatchResult,
    DOBMatchResult,
    PairwiseValidationResult,
    CrossValidationResult,
)
from microservices.validator_service.config import validator_config


class IdentityCrossValidator:
    """Validates extracted identity details across Aadhaar, PAN, and Driving Licence."""

    def __init__(
        self,
        name_match_threshold: Optional[float] = None,
        name_review_threshold: Optional[float] = None,
    ):
        self.name_match_threshold = (
            name_match_threshold
            if name_match_threshold is not None
            else validator_config.NAME_MATCH_THRESHOLD
        )
        self.name_review_threshold = (
            name_review_threshold
            if name_review_threshold is not None
            else validator_config.NAME_REVIEW_THRESHOLD
        )

    @staticmethod
    def normalize_name(name: Optional[str]) -> str:
        if not name:
            return ""
        clean = name.upper()
        clean = re.sub(r"[^\w\s]", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def calculate_name_similarity(self, name1: str, name2: str) -> float:
        norm1 = self.normalize_name(name1)
        norm2 = self.normalize_name(name2)
        if not norm1 or not norm2:
            return 0.0
        if norm1 == norm2:
            return 100.0
        similarity = float(fuzz.token_sort_ratio(norm1, norm2))
        return round(similarity, 2)

    def validate_name_pair(
        self, doc1_key: str, doc2_key: str, name1: Optional[str], name2: Optional[str]
    ) -> NameMatchResult:
        norm1 = self.normalize_name(name1)
        norm2 = self.normalize_name(name2)

        if not norm1 or not norm2:
            status = "MISSING" if (not norm1 and not norm2) else "MISMATCH"
            return NameMatchResult(
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

        return NameMatchResult(
            doc1_key=doc1_key,
            doc2_key=doc2_key,
            doc1_name=norm1,
            doc2_name=norm2,
            similarity=similarity,
            status=status,
        )

    def validate_dob_pair(
        self, doc1_key: str, doc2_key: str, dob1: Optional[str], dob2: Optional[str]
    ) -> DOBMatchResult:
        d1 = dob1.strip() if dob1 else ""
        d2 = dob2.strip() if dob2 else ""

        if not d1 or not d2:
            status = "MISSING" if (not d1 and not d2) else "MISMATCH"
            return DOBMatchResult(
                doc1_key=doc1_key,
                doc2_key=doc2_key,
                doc1_dob=d1,
                doc2_dob=d2,
                status=status,
            )

        status = "MATCH" if d1 == d2 else "MISMATCH"
        return DOBMatchResult(
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
        name_res = self.validate_name_pair(doc1_key, doc2_key, name1, name2)
        dob_res = self.validate_dob_pair(doc1_key, doc2_key, dob1, dob2)

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

    def validate_driver_json(self, json_dict: Dict[str, Any]) -> CrossValidationResult:
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

        l_name = get_field("licence", "full_name") or get_field("driving_licence", "full_name")
        l_dob = get_field("licence", "date_of_birth") or get_field("driving_licence", "date_of_birth")

        aadhaar_vs_pan = self.validate_pair("aadhaar", "pan", a_name, a_dob, p_name, p_dob)
        aadhaar_vs_licence = self.validate_pair("aadhaar", "licence", a_name, a_dob, l_name, l_dob)
        pan_vs_licence = self.validate_pair("pan", "licence", p_name, p_dob, l_name, l_dob)

        pairs = [aadhaar_vs_pan, aadhaar_vs_licence, pan_vs_licence]

        if any(p.name.status in ("MISMATCH", "MISSING") for p in pairs):
            overall_name_status = "MISMATCH"
        elif any(p.name.status == "REVIEW" for p in pairs):
            overall_name_status = "REVIEW"
        elif all(p.name.status == "MATCH" for p in pairs):
            overall_name_status = "MATCHED"
        else:
            overall_name_status = "MISMATCH"

        if any(p.date_of_birth.status in ("MISMATCH", "MISSING") for p in pairs):
            overall_dob_status = "MISMATCH"
        elif all(p.date_of_birth.status == "MATCH" for p in pairs):
            overall_dob_status = "MATCHED"
        else:
            overall_dob_status = "MISMATCH"

        if overall_name_status == "MISMATCH" or overall_dob_status == "MISMATCH":
            overall_status = "MISMATCH"
        elif overall_name_status == "REVIEW":
            overall_status = "REVIEW"
        elif overall_name_status == "MATCHED" and overall_dob_status == "MATCHED":
            overall_status = "MATCHED"
        else:
            overall_status = "MISMATCH"

        return CrossValidationResult(
            driver_id=driver_id,
            aadhaar_vs_pan=aadhaar_vs_pan,
            aadhaar_vs_licence=aadhaar_vs_licence,
            pan_vs_licence=pan_vs_licence,
            overall_name_status=overall_name_status,
            overall_dob_status=overall_dob_status,
            overall_status=overall_status,
        )
