"""
Identity Cross-Validator Service Logic
"""

import re
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple
from rapidfuzz import fuzz

from microservices.shared.models import (
    NameMatchResult,
    DOBMatchResult,
    PairwiseValidationResult,
    VehicleClassMatchResult,
    CrossValidationResult,
)
from microservices.validator_service.config import validator_config


class IdentityCrossValidator:
    """
    Validates extracted identity details across Aadhaar, PAN, and Driving Licence.
    Uses a multi-tier Indian name matching algorithm:
    - Order-invariant token matching (handles First+Middle+Last vs Surname+First)
    - Initial & abbreviation alignment (e.g. 'TRIVENI S JAYSWAL' vs 'TRIVENI SOHANLAL JAYSWAL')
    - Token subset matching (handles missing middle/father names)
    - Typo tolerance & phonetic fuzzy ratios
    """

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

    @staticmethod
    def _initial_aware_similarity(n1: str, n2: str) -> float:
        """
        Matches names where one document uses initials/abbreviations while another uses full names.
        Example: 'TRIVENI S JAYSWAL' vs 'TRIVENI SOHANLAL JAYSWAL' -> 98.3%
        """
        t1 = n1.split()
        t2 = n2.split()
        if not t1 or not t2:
            return 0.0

        # Ensure t1 is the shorter or equal token list
        if len(t1) > len(t2):
            t1, t2 = t2, t1

        matched_t2: Set[int] = set()
        matched_score = 0.0
        total = len(t1)

        for word1 in t1:
            best_idx = None
            best_type = 0  # 2: full/fuzzy match, 1: initial match

            for idx, word2 in enumerate(t2):
                if idx in matched_t2:
                    continue

                # 1. Exact or close fuzzy match on word
                if word1 == word2 or fuzz.ratio(word1, word2) >= 85.0:
                    best_idx = idx
                    best_type = 2
                    break

                # 2. Initial match (single letter matching start of full word)
                if (len(word1) == 1 and word2.startswith(word1)) or (
                    len(word2) == 1 and word1.startswith(word2)
                ):
                    if best_type < 1:
                        best_idx = idx
                        best_type = 1

            if best_idx is not None:
                matched_t2.add(best_idx)
                if best_type == 2:
                    matched_score += 1.0
                elif best_type == 1:
                    matched_score += 0.95

        coverage = matched_score / total
        # Apply slight penalty if lengths differ significantly (e.g. 1 word vs 4 words)
        len_diff = abs(len(t2) - len(t1))
        penalty = max(0.0, (len_diff - 1) * 0.05) if len_diff > 1 else 0.0
        final_score = max(0.0, (coverage - penalty) * 100.0)
        return final_score

    def calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        Computes composite name similarity using an ensemble of:
        1. Token Sort Ratio (word-order invariant)
        2. Token Set Ratio (handles missing middle/father name)
        3. Initial-Aware Alignment (handles single-letter abbreviations)
        4. Partial Ratio (substring matching for composite names)
        """
        norm1 = self.normalize_name(name1)
        norm2 = self.normalize_name(name2)
        if not norm1 or not norm2:
            return 0.0
        if norm1 == norm2:
            return 100.0

        # 1. Token Sort Ratio (e.g. 'SHAIKH SADIK' vs 'SADIK SHAIKH')
        ts_ratio = float(fuzz.token_sort_ratio(norm1, norm2))

        # 2. Token Set Ratio (e.g. 'HARSHIT TRIPATHI' vs 'HARSHIT RAMESH TRIPATHI')
        tset_ratio = float(fuzz.token_set_ratio(norm1, norm2))
        len_diff = abs(len(norm1.split()) - len(norm2.split()))
        tset_weighted = tset_ratio * (0.95 if len_diff <= 1 else 0.85)

        # 3. Initial & Abbreviation Aware Alignment (e.g. 'TRIVENI S' vs 'TRIVENI SOHANLAL')
        initial_score = self._initial_aware_similarity(norm1, norm2)

        # 4. Standard Ratio for minor spelling typos (e.g. 'PRAMODBHAI' vs 'PRAMOD')
        base_ratio = float(fuzz.ratio(norm1, norm2))

        # Choose the strongest matching strategy
        best_score = max(ts_ratio, tset_weighted, initial_score, base_ratio)
        return round(min(100.0, best_score), 2)

    def validate_name_pair(
        self, doc1_key: str, doc2_key: str, name1: Optional[str], name2: Optional[str]
    ) -> NameMatchResult:
        norm1 = self.normalize_name(name1)
        norm2 = self.normalize_name(name2)

        if not norm1 or not norm2:
            return NameMatchResult(
                doc1_key=doc1_key,
                doc2_key=doc2_key,
                doc1_name=norm1,
                doc2_name=norm2,
                similarity=0.0,
                status="MISSING",
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
            return DOBMatchResult(
                doc1_key=doc1_key,
                doc2_key=doc2_key,
                doc1_dob=d1,
                doc2_dob=d2,
                status="MISSING",
            )

        # If both are full ISO dates (e.g. "YYYY-MM-DD" and "YYYY-MM-DD")
        if len(d1) >= 10 and len(d2) >= 10:
            status = "MATCH" if d1 == d2 else "MISMATCH"
        else:
            # If at least one document only provides Year of Birth (e.g. "1992" vs "1992-05-14")
            # Compare the 4-digit birth years
            y1 = d1[:4]
            y2 = d2[:4]
            status = "MATCH" if (y1.isdigit() and y2.isdigit() and y1 == y2) else "MISMATCH"

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

    @staticmethod
    def normalize_vehicle_category(category: Optional[str]) -> Optional[str]:
        """Normalizes user-requested vehicle class string into one of the standard categories using configured aliases."""
        if not category or not str(category).strip():
            return None
        c = str(category).strip().lower().replace("_", " ").replace("-", " ")
        c = re.sub(r"\s+", " ", c)

        # Check configured category aliases
        for canonical_cat, aliases in validator_config.VEHICLE_CATEGORY_ALIASES.items():
            if c in aliases or c == canonical_cat:
                return canonical_cat
        return c

    @classmethod
    def map_extracted_class_to_category(cls, extracted_class: Optional[str]) -> Optional[str]:
        """Maps an RC extracted vehicle class string to one of the canonical categories using validator_config."""
        if not extracted_class or not str(extracted_class).strip():
            return None
        raw_up = str(extracted_class).strip().upper()
        norm_up = re.sub(r"[^\w\(\)\+\s]", "", raw_up).strip()

        # 1. Match against configured canonical classes
        for cat, class_set in validator_config.CANONICAL_VEHICLE_CLASSES.items():
            if raw_up in class_set or norm_up in class_set:
                return cat

        # 2. Heuristic keyword matching from config
        for cat, keywords in validator_config.VEHICLE_HEURISTIC_KEYWORDS.items():
            if any(k in raw_up for k in keywords):
                return cat

        return None

    def validate_vehicle_class(
        self, expected_category: Optional[str], extracted_rc_class: Optional[str]
    ) -> VehicleClassMatchResult:
        """Validates expected vehicle category against RC extracted vehicle class."""
        norm_expected = self.normalize_vehicle_category(expected_category)
        matched_cat = self.map_extracted_class_to_category(extracted_rc_class)

        if not norm_expected:
            return VehicleClassMatchResult(
                expected_category=None,
                extracted_rc_class=extracted_rc_class,
                matched_category=matched_cat,
                status="MISSING",
            )

        if not extracted_rc_class or not str(extracted_rc_class).strip():
            return VehicleClassMatchResult(
                expected_category=norm_expected,
                extracted_rc_class=None,
                matched_category=None,
                status="MISSING",
            )

        if matched_cat and matched_cat == norm_expected:
            status = "MATCH"
        else:
            status = "MISMATCH"

        return VehicleClassMatchResult(
            expected_category=norm_expected,
            extracted_rc_class=extracted_rc_class,
            matched_category=matched_cat,
            status=status,
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
        active_name_pairs = [p.name for p in pairs if p.name.status != "MISSING"]
        active_dob_pairs = [p.date_of_birth for p in pairs if p.date_of_birth.status != "MISSING"]

        if not active_name_pairs:
            overall_name_status = "MISSING"
        elif any(p.status == "MISMATCH" for p in active_name_pairs):
            overall_name_status = "MISMATCH"
        elif any(p.status == "REVIEW" for p in active_name_pairs):
            overall_name_status = "REVIEW"
        elif all(p.status == "MATCH" for p in active_name_pairs):
            overall_name_status = "MATCHED"
        else:
            overall_name_status = "MISMATCH"

        if not active_dob_pairs:
            overall_dob_status = "MISSING"
        elif any(p.status == "MISMATCH" for p in active_dob_pairs):
            overall_dob_status = "MISMATCH"
        elif all(p.status == "MATCH" for p in active_dob_pairs):
            overall_dob_status = "MATCHED"
        else:
            overall_dob_status = "MISMATCH"

        # Vehicle Class Cross-Validation (mandatory for overall approval)
        expected_vc = json_dict.get("vehicle_class") or json_dict.get("expected_vehicle_class")
        rc_vc = get_field("rc", "vehicle_class")
        vc_res = self.validate_vehicle_class(expected_vc, rc_vc)

        if vc_res.status == "MATCH":
            overall_vc_status = "MATCHED"
        else:
            overall_vc_status = "MISMATCH"

        # Composite Overall Status Decision: Name, DOB, and Vehicle Class MUST match
        if overall_name_status == "MISMATCH" or overall_dob_status == "MISMATCH" or overall_vc_status == "MISMATCH":
            overall_status = "MISMATCH"
        elif overall_name_status == "REVIEW":
            overall_status = "REVIEW"
        elif overall_name_status == "MATCHED" and (overall_dob_status in ("MATCHED", "MISSING")) and overall_vc_status == "MATCHED":
            overall_status = "MATCHED"
        elif overall_name_status == "MISSING" and overall_dob_status == "MISSING":
            overall_status = "UNKNOWN"
        else:
            overall_status = "MISMATCH"

        return CrossValidationResult(
            driver_id=driver_id,
            aadhaar_vs_pan=aadhaar_vs_pan,
            aadhaar_vs_licence=aadhaar_vs_licence,
            pan_vs_licence=pan_vs_licence,
            vehicle_class=vc_res,
            overall_name_status=overall_name_status,
            overall_dob_status=overall_dob_status,
            overall_vehicle_class_status=overall_vc_status,
            overall_status=overall_status,
        )
