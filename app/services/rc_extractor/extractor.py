"""
RC (Registration Certificate) Extractor
========================================
Robust, field-aware, layout-reasoning extractor for Indian Vehicle Registration Certificates (RC).
Supports Smart Card RC, RC Booklet, Form 23 Parivahan printouts, tabular layouts, and multi-line values.

Features:
  1. Extracts 5 requested core fields (Registration No, Owner Name, Vehicle Type, Date of Registration, Registration Validity).
  2. Strict label blacklisting to prevent structural labels (e.g. "REG.NO.", "SR.NO.") from becoming Owner Name.
  3. Rejection of garbage/label combinations (e.g. "CYLINDER VALIDITY") for Vehicle Type.
  4. Field-level confidence scoring & uncertainty rating (HIGH, MEDIUM, LOW/UNCERTAIN).
  5. Overall extraction confidence calculation.
"""

import re
import json
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple, Dict

from rapidfuzz import fuzz

from app.models.ocr_models import OCRResult, OCRText, BoundingBox
from app.services.base_extractor import BaseExtractor
from app.services.rc_extractor.models import RCData
from app.services.rc_extractor.config import rc_config
from app.utils.normalizer import normalize_date, normalize_name, normalize_rc_number

logger = logging.getLogger(__name__)

# ── Load Configuration File (rc_config.json) ─────────────────────────────────
_CONFIG_PATH = rc_config.RC_CONFIG_PATH

def _load_rc_config() -> Tuple[Dict[str, str], Set[str]]:
    fuel_types = {}
    vehicle_classes = set()

    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                fuel_types = data.get("fuel_types", {})
                vehicle_classes = set(data.get("vehicle_classes", []))
        except Exception as e:
            logger.error(f"Error loading RC config from {_CONFIG_PATH}: {e}")

    return fuel_types, vehicle_classes

_FUEL_TYPES, _VEHICLE_CLASSES = _load_rc_config()

# ── All-India RC number pattern ──────────────────────────────────────────────
_RC_REGEX = re.compile(
    r"\b([A-Z]{2}[\s\-]?\d{1,2}[\s\-]?[A-Z]{1,3}[\s\-]?\d{4}|\d{2}[\s\-]?BH[\s\-]?\d{4}[\s\-]?[A-Z]{1,2})\b",
    re.IGNORECASE,
)

# Relation Markers for owner name truncation
_RELATION_PATTERNS = [
    re.compile(r"\bS/O\b[:\.\s]?", re.IGNORECASE),
    re.compile(r"\bD/O\b[:\.\s]?", re.IGNORECASE),
    re.compile(r"\bW/O\b[:\.\s]?", re.IGNORECASE),
    re.compile(r"\bC/O\b[:\.\s]?", re.IGNORECASE),
    re.compile(r"\bSON\s+OF\b[:\.\s]?", re.IGNORECASE),
    re.compile(r"\bDAUGHTER\s+OF\b[:\.\s]?", re.IGNORECASE),
    re.compile(r"\bWIFE\s+OF\b[:\.\s]?", re.IGNORECASE),
    re.compile(r"\bSON/DAUGHTER/WIFE\s+OF\b[:\.\s]?", re.IGNORECASE),
    re.compile(r"\bSON/WIFE/DAUGHTER\s+OF\b[:\.\s]?", re.IGNORECASE),
]

# Form 23 "valid from ... to ..." pattern
_VALIDITY_SPAN_REGEX = re.compile(
    r"valid\s+from\s+([0-9A-Z\-\./]+)\s+to\s+([0-9A-Z\-\./]+)",
    re.IGNORECASE,
)

# Clean Canonical Labels List (for RapidFuzz fuzzy matching)
_CANONICAL_RC_LABELS = [
    "REGISTRATION NO", "REGISTRATION NUMBER", "REGN NO", "REG NO", "VEH REG NO", "REG.NO.", "REG. NO.",
    "OWNER NAME", "NAME OF OWNER", "OWNER'S NAME", "REGISTERED OWNER", "VEHICLE OWNER",
    "SON/DAUGHTER/WIFE OF", "SON/WIFE/DAUGHTER OF", "S/O", "D/O", "W/O", "C/O",
    "ADDRESS", "PERMANENT ADDRESS", "PRESENT ADDRESS", "VEHICLE CLASS", "CLASS OF VEHICLE",
    "VEH CLASS", "CLASS", "DESCRIPTION OF VEHICLE", "BODY TYPE", "TYPE OF BODY", "VEHICLE TYPE",
    "MAKER'S NAME", "MAKER NAME", "MANUFACTURER NAME", "MANUFACTURER", "MAKE", "MFR NAME",
    "MODEL NAME", "MODE NAME", "VEHICLE MODEL", "MODEL", "MAKER'S CLASSIFICATION",
    "FUEL TYPE", "FUEL USED", "TYPE OF FUEL", "FUEL", "EMISSION NORMS", "NORMS", "BS4", "BS6",
    "BHARAT STAGE VI", "CHASSIS NO", "CHASSIS NUMBER", "VIN", "CHASIS NO", "CHASSIS/ENGINE NO",
    "ENGINE NO", "ENGINE NUMBER", "ENG NO", "ENGINE/MOTOR NO", "CYLINDER NO", "NO.OF CYLINDERS",
    "CC", "HP", "CUBIC CAPACITY", "SEATING CAPACITY", "STANDING CAPACITY",
    "SEATING/STANDING/SLEEPING CAPACITY", "COLOR", "COLOUR", "UNLADEN WEIGHT", "GROSS VEH WEIGHT",
    "WHEELBASE", "MONTH/YEAR OF MFG", "MFG DATE", "MONTH-YEAR OF MFG", "MONTH & YR. OF MFG.",
    "DATE OF REGISTRATION", "REGISTRATION DATE", "DATE OF REG", "REG DATE", "REGN DATE",
    "REGISTRATION UPTO", "REGN UPTO", "FITNESS UPTO", "FITNESS UP TO", "REGISTRATION VALIDITY",
    "REGN.VALIDITY", "FITNESS VALIDITY", "INSURANCE UPTO", "INSURANCE VALIDITY", "TAX UPTO",
    "TAX VALIDITY", "REGISTRATION AUTHORITY", "REGISTERING AUTHORITY", "ISSUING AUTHORITY", "RTO",
    "FINANCIER NAME", "FINANCER NAME", "HYPOTHECATION", "OWNERSHIP", "INDIVIDUAL",
    "ORGANISATION", "FIRM", "COMPANY", "CORPORATION", "SERIAL", "CARD ISSUE DATE",
    "FORM 23", "FORM 24", "CERTIFICATE OF REGISTRATION", "INDIAN UNION", "STATE",
    "GOVERNMENT OF", "TRANSPORT DEPARTMENT", "SR. NO.", "SR.NO.", "SR NO",
    "OWNER SR. NO.", "SERIAL NO", "OWNERSHIP TR. DATE", "OWNER'S SIGN", "SIGNATURE",
]

# Primary Expected Side per Field
_EXPECTED_FIELD_SIDE = {
    "registration_number": "front",
    "owner_name": "front",
    "vehicle_type": "back",
    "date_of_registration": "front",
    "registration_validity": "front",
}


@dataclass
class Candidate:
    """Evaluated candidate for a specific field."""
    text: str
    ocr_box: OCRText
    label_box: OCRText
    spatial_score: float
    format_score: float
    vocab_bonus: float
    side_score: float
    total_score: float
    relationship: str  # "inline", "right", "below"
    rejection_reason: Optional[str] = None


class RCExtractor(BaseExtractor):
    """Robust, field-aware extractor for Indian RC documents with Confidence Metrics."""

    def __init__(self, debug: bool = False):
        self.debug = debug

    def extract_rc(self, ocr_front: Optional[OCRResult], ocr_back: Optional[OCRResult]) -> RCData:
        """
        Processes front and back OCR results independently to avoid cross-side spatial contamination,
        then merges field extractions using side-priority rules.
        """
        data_front = self._extract_side(ocr_front, side="front") if ocr_front else None
        data_back = self._extract_side(ocr_back, side="back") if ocr_back else None

        if data_front is None and data_back is None:
            return RCData()
        if data_front is None:
            return data_back
        if data_back is None:
            return data_front

        merged = RCData()
        all_fields = (
            RCData.model_fields.keys()
            if hasattr(RCData, "model_fields")
            else RCData.__fields__.keys()
        )

        for field_name in all_fields:
            if field_name in ("confidence_scores", "overall_confidence", "field_diagnostics"):
                continue

            pref_side = _EXPECTED_FIELD_SIDE.get(field_name, "front")
            val_front = getattr(data_front, field_name, None)
            val_back = getattr(data_back, field_name, None)

            conf_front = data_front.confidence_scores.get(field_name, 0.0)
            conf_back = data_back.confidence_scores.get(field_name, 0.0)

            if pref_side == "front":
                if val_front is not None:
                    val = val_front
                    conf = conf_front
                else:
                    val = val_back
                    conf = conf_back
            else:
                if val_back is not None:
                    val = val_back
                    conf = conf_back
                else:
                    val = val_front
                    conf = conf_front

            setattr(merged, field_name, val)
            if val is not None and conf > 0.0:
                merged.confidence_scores[field_name] = conf

        combined_texts = []
        if ocr_front and ocr_front.texts:
            combined_texts.extend(ocr_front.texts)
        if ocr_back and ocr_back.texts:
            combined_texts.extend(ocr_back.texts)

        self._apply_form23_validity_spans(merged, combined_texts)
        self._apply_cross_field_sanity(merged)
        self._calculate_overall_confidence(merged)
        self._generate_rc_diagnostics(merged, combined_texts)
        return merged

    def extract(self, ocr_result: OCRResult) -> RCData:
        """Single OCR result entry point for backward compatibility."""
        data = self._extract_side(ocr_result, side="unknown")
        if ocr_result and ocr_result.texts:
            self._apply_form23_validity_spans(data, ocr_result.texts)
        self._apply_cross_field_sanity(data)
        self._calculate_overall_confidence(data)
        self._generate_rc_diagnostics(data, ocr_result.texts if ocr_result else [])
        return data

    def extract_registration_number(self, texts: List[OCRText]) -> Optional[str]:
        """Public helper method for registration number extraction."""
        val, _ = self._extract_registration_number_with_fallback(texts, side="unknown")
        return val

    # ── Side-Specific Extraction ──────────────────────────────────────────────

    def _extract_side(self, ocr_result: Optional[OCRResult], side: str = "unknown") -> RCData:
        if not ocr_result or not ocr_result.texts:
            return RCData()

        texts = ocr_result.texts
        data = RCData()

        fields_to_extract = ["registration_number", "owner_name", "vehicle_type", "date_of_registration", "registration_validity"]

        for f_name in fields_to_extract:
            val, conf = self._extract_field_with_confidence(texts, f_name, side)
            if val:
                setattr(data, f_name, val)
                data.confidence_scores[f_name] = conf

        self._calculate_overall_confidence(data)
        return data

    # ── Master Field Extractor with Confidence Calculation ────────────────────

    def _extract_field_with_confidence(self, texts: List[OCRText], field_name: str, side: str) -> Tuple[Optional[str], float]:

        if field_name == "registration_number":
            reg_val, reg_conf = self._extract_registration_number_with_fallback(texts, side)
            if reg_val:
                return reg_val, reg_conf

        keywords = self._get_keywords_for_field(field_name)
        if not keywords:
            return None, 0.0

        allow_multiline = field_name in ("owner_name", "vehicle_type")

        cand = self._get_best_candidate_for_keywords(
            texts=texts,
            keywords=keywords,
            field_type=field_name,
            side=side,
            allow_multiline=allow_multiline,
        )

        if not cand and field_name == "owner_name" and allow_multiline:
            cand = self._get_best_candidate_for_keywords(
                texts=texts,
                keywords=keywords,
                field_type=field_name,
                side=side,
                allow_multiline=False,
            )

        if not cand and field_name == "owner_name":
            relation_value, rel_conf = self._extract_owner_from_relation_context(texts)
            if relation_value:
                return relation_value.upper(), rel_conf

        if not cand:
            return None, 0.0

        val = cand.text.strip()
    
        ocr_conf = cand.ocr_box.confidence
        score_conf = min(1.0, max(0.5, cand.total_score / 140.0))
        field_conf = round(min(1.0, max(0.0, (0.55 * ocr_conf) + (0.45 * score_conf))), 2)

        if field_name == "registration_number":
            norm = normalize_rc_number(re.sub(r"[\s\-]", "", val.upper()))
            return norm, 0.98 if norm else field_conf
        elif field_name == "owner_name":
            truncated = self._truncate_relation_marker(val)
            return truncated.upper(), field_conf
        elif field_name in ("date_of_registration", "registration_validity"):
            norm_dt = normalize_date(val)
            return norm_dt, 0.96 if norm_dt else field_conf
        else:
            return val.upper(), field_conf

    # ── Candidate Generation & Scoring Engine ─────────────────────────────────

    def _get_best_candidate_for_keywords(
        self,
        texts: List[OCRText],
        keywords: List[str],
        field_type: str,
        side: str,
        allow_multiline: bool = False,
    ) -> Optional[Candidate]:
        label_boxes = self._find_all_matching_labels(texts, keywords)
        if not label_boxes:
            return None

        all_candidates: List[Candidate] = []

        for label_box in label_boxes:
            inline_val = self._extract_inline_value(label_box.text, keywords=keywords)
            if inline_val and not self._is_structural_label(inline_val):
                fmt_score, v_bonus = self._evaluate_candidate_format(inline_val, field_type)
                if fmt_score >= 0:
                    pref_side = _EXPECTED_FIELD_SIDE.get(field_type, "front")
                    side_score = 30.0 if (side == pref_side or side == "unknown") else 0.0
                    tot_score = 80.0 + fmt_score + v_bonus + side_score + (10.0 * label_box.confidence)
                    cand_obj = Candidate(
                        text=inline_val,
                        ocr_box=label_box,
                        label_box=label_box,
                        spatial_score=80.0,
                        format_score=fmt_score,
                        vocab_bonus=v_bonus,
                        side_score=side_score,
                        total_score=tot_score,
                        relationship="inline",
                    )
                    all_candidates.append(cand_obj)

            cand = self._evaluate_candidates_for_label(
                texts, label_box, field_type, side, allow_multiline=allow_multiline
            )
            if cand:
                all_candidates.append(cand)

        if not all_candidates:
            return None

        all_candidates.sort(key=lambda c: c.total_score, reverse=True)
        top = all_candidates[0]

        return top if top.total_score >= 20.0 else None

    def _evaluate_candidates_for_label(
        self,
        texts: List[OCRText],
        label_box: OCRText,
        field_type: str,
        side: str,
        allow_multiline: bool = False,
    ) -> Optional[Candidate]:
        candidates: List[Candidate] = []

        lx1, lx2 = label_box.bounding_box.min_x, label_box.bounding_box.max_x
        ly1, ly2 = label_box.bounding_box.min_y, label_box.bounding_box.max_y
        lcy = label_box.bounding_box.center_y
        l_height = max(15.0, label_box.bounding_box.height)
        label_center_x = (lx1 + lx2) / 2.0

        same_row_tolerance = max(20.0, l_height * 0.9)
        below_vertical_max = max(140.0, l_height * 4.5)

        is_date_field = field_type.startswith("date_") or field_type.endswith("_validity")
        below_x_tolerance = max(60.0, l_height * 2.5) if is_date_field else max(110.0, l_height * 5.0)

        for item in texts:
            if item is label_box:
                continue

            if item.bounding_box.max_x < lx1 - 30.0:
                continue

            text_clean = self._clean_inline_value(item.text.strip())
            if not text_clean or self._is_structural_label(text_clean):
                continue

            icx = item.bounding_box.center_x
            icy = item.bounding_box.center_y
            ix1 = item.bounding_box.min_x
            iy1 = item.bounding_box.min_y

            right_of_label = ix1 >= lx2 - max(8.0, l_height * 0.20)
            x_alignment = abs(icx - label_center_x)

            on_same_row = abs(icy - lcy) <= same_row_tolerance and right_of_label
            is_below = (
                iy1 >= ly2 - 5
                and (iy1 - ly2) <= below_vertical_max
                and x_alignment <= below_x_tolerance
            )

            if not on_same_row and not is_below:
                continue

            relationship = "right" if on_same_row else "below"

            merged_text = text_clean
            if allow_multiline:
                merged_text = self._merge_continuation_boxes(texts, item, relationship, field_type)

            if relationship == "right":
                dist = max(0.0, ix1 - lx2)
                spatial_score = max(0.0, 65.0 - (dist / 3.5))
            else:
                dist = max(0.0, iy1 - ly2)
                spatial_score = max(0.0, 55.0 - (dist / 3.0))

            if relationship == "below":
                col_align_bonus = max(0.0, 30.0 - (x_alignment / 3.0))
                spatial_score += col_align_bonus

            pref_side = _EXPECTED_FIELD_SIDE.get(field_type, "front")
            side_score = 30.0 if (side == pref_side or side == "unknown") else 0.0

            fmt_score, v_bonus = self._evaluate_candidate_format(merged_text, field_type)
            if fmt_score < 0:
                continue

            total_score = spatial_score + fmt_score + v_bonus + side_score + (10.0 * item.confidence)

            candidates.append(
                Candidate(
                    text=merged_text,
                    ocr_box=item,
                    label_box=label_box,
                    spatial_score=spatial_score,
                    format_score=fmt_score,
                    vocab_bonus=v_bonus,
                    side_score=side_score,
                    total_score=total_score,
                    relationship=relationship,
                )
            )

        if not candidates:
            return None

        candidates.sort(key=lambda c: c.total_score, reverse=True)
        return candidates[0]

    def _merge_continuation_boxes(
        self, texts: List[OCRText], start_item: OCRText, relationship: str, field_type: str
    ) -> str:
        start_text = self._clean_inline_value(start_item.text.strip())

        if field_type == "owner_name" and any(c.isdigit() for c in start_text):
            return start_text

        merged_tokens = [start_text]
        curr = start_item

        for other in texts:
            if other is start_item or other.text.strip() in merged_tokens:
                continue

            o_text = self._clean_inline_value(other.text.strip())
            if self._is_structural_label(o_text):
                continue

            h_tol = max(18.0, curr.bounding_box.height * 0.9)

            if abs(other.bounding_box.center_y - curr.bounding_box.center_y) <= h_tol:
                dist = other.bounding_box.min_x - curr.bounding_box.max_x
                if 0 <= dist <= 130.0:
                    if field_type == "owner_name" and any(c.isdigit() for c in o_text):
                        break
                    merged_tokens.append(o_text)
                    curr = other
                    continue

            v_dist = other.bounding_box.min_y - curr.bounding_box.max_y
            h_align = abs(other.bounding_box.min_x - curr.bounding_box.min_x)
            max_v = max(25.0, curr.bounding_box.height * 1.2)

            if 0 <= v_dist <= max_v and h_align <= 60.0:
                if field_type == "owner_name" and any(c.isdigit() for c in o_text):
                    break
                has_intervening_label = any(
                    lbl is not curr and lbl is not other and self._is_structural_label(lbl.text)
                    and (curr.bounding_box.min_y + 15.0 <= lbl.bounding_box.min_y <= other.bounding_box.max_y + 5.0)
                    and lbl.bounding_box.max_x >= min(curr.bounding_box.min_x, other.bounding_box.min_x) - 30.0
                    for lbl in texts
                )
                if not has_intervening_label:
                    merged_tokens.append(o_text)
                    curr = other
                    continue

        return " ".join(merged_tokens)

    # ── Hierarchical Label Matching Engine with RapidFuzz ──────────────────────

    def _find_all_matching_labels(self, texts: List[OCRText], keywords: List[str]) -> List[OCRText]:
        """Finds all matching label OCR boxes using exact, prefix, and RapidFuzz fuzzy matching (~85)."""
        matches: List[Tuple[float, OCRText]] = []

        for kw in keywords:
            kw_clean = kw.upper().rstrip(":").rstrip(".").strip()
            for item in texts:
                t_clean = item.text.upper().strip().rstrip(":").rstrip(".").strip()

                if any(w in kw_clean for w in ["VALIDITY", "VALID", "UPTO", "EXPIRY"]) and "DATE" in t_clean and not any(w in t_clean for w in ["VALIDITY", "VALID", "UPTO", "EXPIRY"]):
                    continue
                if "DATE" in kw_clean and any(w in t_clean for w in ["VALIDITY", "VALID", "UPTO", "EXPIRY"]) and "DATE" not in t_clean:
                    continue

                score = 0.0
                if t_clean == kw_clean:
                    score = 100.0
                elif t_clean.startswith(kw_clean) or kw_clean.startswith(t_clean):
                    if len(t_clean) == len(kw_clean) or t_clean[len(kw_clean):len(kw_clean)+1] in (" ", ":", "."):
                        score = 90.0

                if score == 0.0 and len(kw_clean) >= 4 and len(t_clean) >= 4:
                    fuzzy_threshold = rc_config.FUZZY_MATCH_THRESHOLD
                    ratio = fuzz.ratio(kw_clean, t_clean)
                    if ratio >= fuzzy_threshold:
                        score = ratio
                    else:
                        ts_ratio = fuzz.token_set_ratio(kw_clean, t_clean)
                        if ts_ratio >= fuzzy_threshold and abs(len(t_clean) - len(kw_clean)) <= 12:
                            score = ts_ratio

                if score > 0:
                    matches.append((score, item))

        matches.sort(key=lambda x: x[0], reverse=True)
        seen = set()
        unique = []
        for s, box in matches:
            b_id = id(box)
            if b_id not in seen:
                seen.add(b_id)
                unique.append(box)

        return unique

    def _is_structural_label(self, text: str) -> bool:
        """Determines if text matches a canonical RC label using RapidFuzz."""
        clean = text.upper().strip().rstrip(":").rstrip(".").strip()
        if not clean:
            return True

        if text.strip().endswith(":") and len(text.strip()) <= 35:
            return True

        fuzzy_threshold = rc_config.FUZZY_MATCH_THRESHOLD
        for lbl in _CANONICAL_RC_LABELS:
            lbl_clean = lbl.upper()
            if clean == lbl_clean or clean.startswith(lbl_clean + ":") or clean.startswith(lbl_clean + " "):
                return True
            if len(lbl_clean) >= 6 and len(clean) >= 4:
                if fuzz.token_set_ratio(lbl_clean, clean) >= fuzzy_threshold and abs(len(clean) - len(lbl_clean)) <= 15:
                    return True
                if fuzz.ratio(lbl_clean, clean) >= fuzzy_threshold:
                    return True

        return False

    # ── Inline Value Splitting Supporting Colons, Spaces, and Dots ─────────────

    def _extract_inline_value(self, text: str, keywords: Optional[List[str]] = None) -> Optional[str]:
        clean_text = text.strip()

        if ":" in clean_text:
            parts = clean_text.split(":", 1)
            val = parts[1].strip()
            if val and not self._is_structural_label(val):
                return val

        if keywords:
            text_up = clean_text.upper()
            for kw in keywords:
                kw_clean = kw.upper().rstrip(":").rstrip(".").strip()
                if text_up.startswith(kw_clean) and len(text_up) > len(kw_clean):
                    val = clean_text[len(kw_clean):].strip().lstrip(":").lstrip(".").strip()
                    if val and not self._is_structural_label(val):
                        return val

        return None

    def _clean_inline_value(self, text: str) -> str:
        if ":" in text:
            parts = text.split(":", 1)
            if self._is_structural_label(parts[0]):
                return parts[1].strip()
        return text

    # ── Field-Specific Format Validation & Soft Hint Vocabulary Scoring ───────

    def _evaluate_candidate_format(self, text: str, field_type: str) -> Tuple[float, float]:
        clean_up = text.upper().strip()
        cleaned_nodash = re.sub(r"[\s\-]", "", clean_up)

        if field_type in ("owner_name", "vehicle_type"):
            if normalize_date(text):
                return (-100.0, 0.0)

        if field_type in ("owner_name", "vehicle_type"):
            if 8 <= len(cleaned_nodash) <= 11 and normalize_rc_number(cleaned_nodash):
                return (-100.0, 0.0)

        if field_type == "registration_number":
            if normalize_rc_number(cleaned_nodash):
                return (60.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "owner_name":
            truncated = self._truncate_relation_marker(text)
            if self._is_plausible_owner_name(truncated):
                return (50.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "vehicle_type":
            if len(clean_up) <= 35 and not self._is_structural_label(clean_up):
                if not any(w in clean_up for w in ["VALIDITY", "CYLINDER", "REGISTRATION", "CERTIFICATE", "GOVERNMENT", "DEPARTMENT", "NAME"]):
                    return (40.0, 0.0)
            return (-100.0, 0.0)

        elif field_type in ("date_of_registration", "registration_validity"):
            if normalize_date(text):
                return (60.0, 0.0)
            return (-100.0, 0.0)

        return (10.0, 0.0)

    # ── Validation Helpers & Relation Marker Truncation ───────────────────────

    def _truncate_relation_marker(self, text: str) -> str:
        result = text.strip()
        for pat in _RELATION_PATTERNS:
            m = pat.search(result)
            if m:
                result = result[:m.start()].strip()
                break
        return result

    def _is_plausible_owner_name(self, text: str) -> bool:
        text = self._truncate_relation_marker(text.strip())
        if not text or any(c.isdigit() for c in text):
            return False

        text_up = text.upper()
        if text_up in _FUEL_TYPES or text_up in _VEHICLE_CLASSES:
            return False

        # Blacklist all registration number / serial / structural labels
        if any(lbl in text_up for lbl in [
            "REG.NO", "REG NO", "REGN", "REGD", "REGISTRATION",
            "SR.NO", "SR NO", "SERIAL", "SIGN", "SIGNATURE",
            "CHASSIS", "ENGINE", "MODEL", "MAKER", "FORM", "VALIDITY", "CYLINDER"
        ]):
            return False

        words = text.split()
        if len(words) < 1 or len(words) > 6:
            return False
        for w in words:
            if not w.replace(".", "").replace("'", "").replace("-", "").isalpha():
                return False
        return not self._is_structural_label(text)

    def _get_keywords_for_field(self, field_name: str) -> List[str]:
        mapping = {
            "registration_number": [
                "Registration No", "Registration Number", "Regn.No", "Regn.Number",
                "Reg.No", "Regn No", "Regd No", "Reg No", "Rexn.Number", "Veh Reg No",
            ],
            "owner_name": [
                "Name of Owner", "Owner Name", "Owner's Name", "Registered Owner",
                "Regn Owner", "Vehicle Owner", "Name of Registered Owner",
            ],
            "vehicle_type": [
                "Type of Body", "Body Type", "Description of Vehicle", "Vehicle Class",
                "Class of Vehicle", "Veh Class", "Vehicle Type", "Type of Vehicle",
                "Type of Veh", "Veh Type",
            ],
            "date_of_registration": [
                "Registration Date", "Date of Registration", "Date of Reg.", "Reg Date",
                "Regn Date", "Date of Regn.",
            ],
            "registration_validity": [
                "Registration Validity", "Regn.Validity", "Regn. Validity", "Registration Upto",
                "Fitness UpTo",
                "Registration Valid Upto", "Regn Valid Till", "Fitness Validity",
            ],
        }
        return mapping.get(field_name, [])

    def _extract_owner_from_relation_context(self, texts: List[OCRText]) -> Tuple[Optional[str], float]:
        relation_kw = ["Son/Daughter/Wife of", "Son/Wife/Daughter of", "Son/wife/daughter of", "S/O", "D/O", "W/O", "C/O"]
        cand = self._get_best_candidate_for_keywords(
            texts=texts,
            keywords=relation_kw,
            field_type="owner_name",
            side="front",
            allow_multiline=False,
        )
        if cand:
            truncated = self._truncate_relation_marker(cand.text)
            if self._is_plausible_owner_name(truncated):
                return truncated, 0.88
        return None, 0.0

    def _apply_form23_validity_spans(self, data: RCData, texts: List[OCRText]) -> None:
        if not texts:
            return

        full_text = " ".join(t.text for t in texts)
        m = _VALIDITY_SPAN_REGEX.search(full_text)
        if m:
            start_str, end_str = m.group(1), m.group(2)
            start_date = normalize_date(start_str)
            end_date = normalize_date(end_str)

            if start_date and not data.date_of_registration:
                data.date_of_registration = start_date
                data.confidence_scores["date_of_registration"] = 0.95

            if end_date and not data.registration_validity:
                data.registration_validity = end_date
                data.confidence_scores["registration_validity"] = 0.95

    def _extract_registration_number_with_fallback(
        self, texts: List[OCRText], side: str
    ) -> Tuple[Optional[str], float]:
        label_keywords = self._get_keywords_for_field("registration_number")
        cand = self._get_best_candidate_for_keywords(
            texts, label_keywords, field_type="registration_number", side=side
        )
        if cand:
            norm = normalize_rc_number(re.sub(r"[\s\-]", "", cand.text.upper()))
            if norm:
                return norm, 0.98

        for item in texts:
            m = _RC_REGEX.search(item.text)
            if m:
                norm = normalize_rc_number(m.group(1))
                if norm:
                    return norm, 0.95

        full = " ".join(t.text.upper() for t in texts)
        m = _RC_REGEX.search(full)
        if m:
            norm = normalize_rc_number(m.group(1))
            if norm:
                return norm, 0.90

        return None, 0.0

    def _apply_cross_field_sanity(self, data: RCData) -> None:
        if data.owner_name and self._is_structural_label(data.owner_name):
            data.owner_name = None
            data.confidence_scores.pop("owner_name", None)

    def _calculate_overall_confidence(self, data: RCData) -> None:
        scores = [v for k, v in data.confidence_scores.items() if getattr(data, k, None) is not None]
        if scores:
            data.overall_confidence = round(sum(scores) / len(scores), 2)
        else:
            data.overall_confidence = 0.0

    def _generate_rc_diagnostics(self, data: RCData, texts: List[OCRText]) -> None:
        """For every missing field, explain why OCR failed to extract it."""
        if not texts:
            for field in ["registration_number", "owner_name", "vehicle_type", "date_of_registration", "registration_validity"]:
                data.field_diagnostics[field] = "OCR returned no text from image"
            return

        avg_conf = sum(t.confidence for t in texts) / len(texts)
        low_quality_msg = ""
        if avg_conf < 0.5:
            low_quality_msg = f"Low OCR confidence ({avg_conf:.0%}); image may be blurry or low quality"

        if not data.registration_number:
            data.field_diagnostics["registration_number"] = low_quality_msg or "No RC number pattern (SS-RR-XX-NNNN) found in OCR text"

        if not data.owner_name:
            data.field_diagnostics["owner_name"] = low_quality_msg or "No plausible owner name found near 'Owner Name' label"

        if not data.vehicle_type:
            data.field_diagnostics["vehicle_type"] = low_quality_msg or "No vehicle type/body type found near relevant label"

        if not data.date_of_registration:
            data.field_diagnostics["date_of_registration"] = low_quality_msg or "No registration date found near 'Date of Registration' label"

        if not data.registration_validity:
            data.field_diagnostics["registration_validity"] = low_quality_msg or "No validity/fitness date found near relevant label"
