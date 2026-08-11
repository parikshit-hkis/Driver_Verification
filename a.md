i have to make automation of checking details from image for platform like rapido,ola,uber's driver documents :
driver licence,
aadhar card,
rc book and other details filled by that driver like name,date of birth(dob),mobile number,email id in form while registering 
so help me to make full plan to make that type of automation for me,i have to cover all the details which is using in real world for that type of application 
so each document will be in image format which can have both front and back side of the document.

# so i have to extract corresponding detail from that documents and save it. after that make an automation like using that information it can check all the details. 

## details to extract from images:

1. aadhar card: full_name(with extractable format of first,last and middle name),aadhar_no,dob
2. driver licence: full_name(with extractable format of first,last and middle name),dob,license_no,issue_date,expiry_date,all Class of Vehicle(like in how many types of vehicles that person is eligible to drive after getting license)
3. rc book: owner_name,registration_number,vehicle_type,issue_date,expiry_date
and these comes from api and other details are like full_name,dob,mobile number,

### automation details:

1. after extracting all the details, check all details are correct or not by comparing and matching all three documents data with each other 
    if all are correct then save it as "verification complete", else flag it as pending, and create report/file which conatins all the missing or wrong details

2. all service should be independent.


# pipeline should be:
Driver Registration
        │
        ▼
Upload Images
(Aadhaar, DL, RC, Selfie, etc.)
        │
        ▼
Image Validation
        │
        ▼
OCR & Data Extraction
        │
        ▼
Normalization(regex,Key-Value Anchor Mapping,)
        │
        ▼
Document Validation
        │
        ▼
Cross Document Matching
        │
        ▼
Business Rule Validation
        │
        ▼
Verification Report
        │
        ▼
Approve / Manual Review / Reject



## phase 1: Input
    1.driver licence,
    2.aadhar card,
    3.rc book,
    4. other details(like name,dob,mobile number,email id in form while registering).

## Phase 2 — Image Quality Check
    validate image quality.
    if image  blury then reject and flag as documation is readable.

## Phase 3 — Document Type Detection
    Automatically determine which document is this.

## Phase 4 — OCR(Optical Character Recognition) - can use Celery with redis broker for async distributed workers
### like FastAPI + Celery + Redis (or RabbitMQ) + Postgres for job status
    1. PaddleOCR
    2. Tesseract OCR
    3. EasyOCR
    4. Google Cloud Vision API(paid - gives 300$ credits on new user)
    5. AWS Textract 
    6. Microsoft Azure AI Document Intelligence
    extract text from documents

## Phase 5 — Structured Extraction
    1. aadhar card:{
        "document_type": "AADHAAR",
        "aadhaar_number": "",
        "full_name": "",
        "dob": "",
        "gender": ""
    }

    2. driver licence:{
        "document_type": "driver licence",
        "license_number": "",
        "full_name": "",
        "dob": "",
        "issue_date": "",
        "expiry_date": "",
        "issuing_state": "",
        "vehicle_classes": [
            "MCWG",
            "LMV"
        ]
    }

    3. RC:{
        "document_type": "RC",
        "registration_number": "",
        "owner_name": "",
        "vehicle_type": "",
        "fuel_type": "",
        "manufacturer": "",
        "model": "",
        "issue_date": "",
        "expiry_date","fitness_validity","registration_Validity": ""
    }

## Phase 6 — Normalization
    for full_name: first_name,middle_name,_last_name or we can do Fuzzy Matching algorithm 
    for dob: if 12-04-2000 -> 2000-04-12 
    for licence number: GJ-01-2021-0012345 -> GJ0120210012345


## Phase 7 — Validation
    Aadhaar :   Aadhaar number format
                DOB exists
                Name exists
                Gender exists

    Driving Licence :   license format
                        expiry > today
                        issue < expiry
                        DOB present
                        name present
                        vehicle classes exist

    RC :    registration number format
            owner name
            issue date
            expiry
            vehicle type

## Phase 8 — Cross Document Matching
    Name Matching - 
        Normalize Name -> like fuzzy matching -> Similarity Score
        A name extracted at 60% confidence should route to manual review even if it "matches" --> confidence thresholding
        token_sort_ratio (RapidFuzz / RapidFuzz PyPI),
        token_set_ratio (RapidFuzz / RapidFuzz PyPI),
        Jaro-Winkler (TextDistance)
        
    DOB Matching
    License Expiry
    Vehicle Eligibility with uploaded RC of vehicle
    RC Owner name 



# new updateed pipeline :


Driver Registration
     │
     ▼
Upload Images  ── [Section 2]
     │
     ▼
Create Job (status=queued) → Return job_id immediately ── [Section 1: async]
     │
     ▼
[Celery Worker picks up job]
     │
     ▼
Image Quality Check (blur, brightness, resolution — no rotation check) ── [Section 3]
     │
     ▼
Document Type Detection
     │
     ▼
OCR (PaddleOCR, with bounding boxes) ── [Section 6]
     │
     ▼
Structured Extraction (label-proximity + Gujarat regex) ── [Section 5,6]
     │
     ▼
Normalization
     │
     ▼
Validation (format + RTO code lookup + expiry)
     │
     ▼
Cross-Document Matching (fuzzy name, exact DOB)
     │
     ▼
Decision: Approve / Pending / Reject
     │
     ▼
Update job status + save report → = notified/polls status
     │
     ▼
[If Pending] → Manual Review → Human Approve/Reject
[If Rejected] → Driver can reapply with new documents





i have some changes:
1. i have documents only for gujarat's driver
2. i'll have data image format and other data into json so don't worry about api i'll habdle that.


aadhar number of 4341 3155 9547,
name: patel jay dhansukhbhai,
dob: 18/05/1999,
address: vastral, nehru nagar,ahmedabad,gujarat,380058,
gender: male,
aadhar no. issued: 10/10/2016 ,
in english and gujarati language for gujarat state 


aadhar number of 9658 3155 6851,
name: sutariya daksh hiteshbhai,
dob: 05/02/2002,
address: bopal, dhanlaxmi society,ahmedabad,gujarat,380058,
gender: male,
aadhar no. issued: 18/02/2016,
in english and gujarati language for gujarat state 


aadhar number of 6596 4578 1352,
name: gorasiya vivek hirenbhai,
dob: 28/08/2005,
address: shivalay society,katargam,surat,gujarat,384720,
gender: male,
aadhar no. issued: 28/05/2017,
in english and gujarati language for gujarat state 

aadhar number of 8956 5623 4512,
name: parikh keval rameshbbhai,
dob: 28/07/2006,
address: maninagar,ahmedabad,gujarat,380008,
gender: male,
aadhar no. issued: 10/06/2018,
in english and gujarati language for gujarat state and diferent face 


aadhar number of 4576 8956 4562,
name: lakhani riya pankajbhai,
dob: 28/09/2000,
address: bopal,near by kalpur chokdi,ahmedabad,gujarat,380008,
gender: female,
aadhar no. issued: 10/06/2018,
in english and gujarati language for gujarat state and diferent face 





"""
RC (Registration Certificate) Extractor
========================================
Robust, field-aware, layout-reasoning extractor for Indian Vehicle Registration Certificates (RC).
Supports Smart Card RC, RC Booklet, tabular layouts, multi-line values, and open-set fields.

Features:
  1. Config-backed enums (rc_config.json) & DB-backed ManufacturerRepository.
  2. RapidFuzz fuzzy label matching (threshold ~85) eliminating hardcoded OCR-typo entries.
  3. Owner name relation marker truncation ("S/O", "D/O", "W/O", "C/O").
  4. Digit-based multiline continuation stopping for owner_name.
  5. Automatic fallback to single-line (allow_multiline=False) if multiline candidate fails validation.
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
from app.services.rc_extractor.manufacturer_repository import ManufacturerRepository
from app.utils.normalizer import normalize_date, normalize_name, normalize_rc_number

logger = logging.getLogger(__name__)

# ── Load Configuration File (rc_config.json) ─────────────────────────────────
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "rc_config.json"

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
_MANUFACTURER_REPO = ManufacturerRepository()

# ── All-India RC number pattern ──────────────────────────────────────────────
_RC_REGEX = re.compile(
    r"\b([A-Z]{2}[\s\-]?\d{1,2}[\s\-]?[A-Z]{1,3}[\s\-]?\d{4}|\d{2}[\s\-]?BH[\s\-]?\d{4}[\s\-]?[A-Z]{1,2})\b",
    re.IGNORECASE,
)

_VIN_17_REGEX = re.compile(r"^[A-Z0-9]{17}$", re.IGNORECASE)
_CHASSIS_LOOSE_REGEX = re.compile(r"^[A-Z0-9]{8,17}$", re.IGNORECASE)
_ENGINE_REGEX = re.compile(r"^[A-Z0-9]{5,16}$", re.IGNORECASE)

_BLACKLISTED_CHASSIS_WORDS = {
    "MANUFACTURER", "REGISTRATION", "MODELNAME", "VEHICLE", "CHASSIS",
    "ENGINE", "CERTIFICATE", "AUTHORITY", "GOVERNMENT", "TRANSPORT",
}

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

# Clean Canonical Labels List (for RapidFuzz fuzzy matching)
_CANONICAL_RC_LABELS = [
    "REGISTRATION NO", "REGISTRATION NUMBER", "REGN NO", "REG NO", "VEH REG NO",
    "OWNER NAME", "NAME OF OWNER", "OWNER'S NAME", "REGISTERED OWNER", "VEHICLE OWNER",
    "SON/DAUGHTER/WIFE OF", "SON/WIFE/DAUGHTER OF", "S/O", "D/O", "W/O", "C/O",
    "ADDRESS", "PERMANENT ADDRESS", "PRESENT ADDRESS", "VEHICLE CLASS", "CLASS OF VEHICLE",
    "VEH CLASS", "CLASS", "BODY TYPE", "VEHICLE TYPE", "MAKER'S NAME", "MAKER NAME",
    "MANUFACTURER NAME", "MANUFACTURER", "MAKE", "MFR NAME", "MODEL NAME", "MODE NAME",
    "VEHICLE MODEL", "MODEL", "FUEL TYPE", "FUEL USED", "TYPE OF FUEL", "FUEL",
    "EMISSION NORMS", "NORMS", "BS4", "BS6", "BHARAT STAGE VI", "CHASSIS NO", "CHASSIS NUMBER",
    "VIN", "CHASIS NO", "CHASSIS/ENGINE NO", "ENGINE NO", "ENGINE NUMBER", "ENG NO",
    "ENGINE/MOTOR NO", "CYLINDER NO", "NO.OF CYLINDERS", "CC", "HP", "CUBIC CAPACITY",
    "SEATING CAPACITY", "STANDING CAPACITY", "SEATING/STANDING/SLEEPING CAPACITY",
    "COLOR", "COLOUR", "UNLADEN WEIGHT", "GROSS VEH WEIGHT", "WHEELBASE", "MONTH/YEAR OF MFG",
    "MFG DATE", "MONTH-YEAR OF MFG", "MONTH & YR. OF MFG.", "DATE OF REGISTRATION",
    "DATE OF REG", "REGISTRATION DATE", "REGISTRATION UPTO", "REGN UPTO",
    "REGISTRATION VALIDITY", "REGN.VALIDITY", "FITNESS UPTO", "FITNESS VALIDITY",
    "INSURANCE UPTO", "INSURANCE VALIDITY", "TAX UPTO", "TAX VALIDITY",
    "REGISTRATION AUTHORITY", "REGISTERING AUTHORITY", "ISSUING AUTHORITY", "RTO",
    "FINANCIER NAME", "FINANCER NAME", "HYPOTHECATION", "OWNERSHIP", "INDIVIDUAL",
    "ORGANISATION", "FIRM", "COMPANY", "CORPORATION", "SERIAL", "CARD ISSUE DATE",
    "FORM 23", "FORM 24", "CERTIFICATE OF REGISTRATION", "INDIAN UNION", "STATE",
    "GOVERNMENT OF", "TRANSPORT DEPARTMENT",
]

# Primary Expected Side per Field
_EXPECTED_FIELD_SIDE = {
    "registration_number": "front",
    "owner_name": "front",
    "vehicle_class": "front",
    "fuel_type": "front",
    "chassis_number": "front",
    "engine_number": "front",
    "date_of_registration": "front",
    "registration_validity": "front",
    "manufacturer": "back",
    "model": "back",
    "vehicle_type": "back",
    "issuing_rto": "back",
    "fitness_validity": "back",
    "insurance_validity": "back",
    "tax_validity": "back",
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
    """Robust, field-aware extractor for Indian RC documents."""

    def __init__(self, debug: bool = False, mfr_repo: Optional[ManufacturerRepository] = None):
        self.debug = debug
        self.mfr_repo = mfr_repo or _MANUFACTURER_REPO

    def extract_rc(self, ocr_front: Optional[OCRResult], ocr_back: Optional[OCRResult]) -> RCData:
        """
        Processes front and back OCR results independently to avoid cross-side spatial contamination,
        then merges field extractions using side-priority rules.
        """
        data_front = self._extract_side(ocr_front, side="front") if ocr_front else None
        data_back = self._extract_side(ocr_back, side="back") if ocr_back else None

        if not data_front and not data_back:
            return RCData()
        if not data_front:
            return data_back
        if not data_back:
            return data_front

        merged = RCData()
        all_fields = RCData.__fields__.keys()

        for field_name in all_fields:
            pref_side = _EXPECTED_FIELD_SIDE.get(field_name, "front")
            val_front = getattr(data_front, field_name, None)
            val_back = getattr(data_back, field_name, None)

            if pref_side == "front":
                val = val_front if val_front is not None else val_back
            else:
                val = val_back if val_back is not None else val_front

            setattr(merged, field_name, val)

        self._apply_cross_field_sanity(merged)
        return merged

    def extract(self, ocr_result: OCRResult) -> RCData:
        """Single OCR result entry point for backward compatibility."""
        data = self._extract_side(ocr_result, side="unknown")
        self._apply_cross_field_sanity(data)
        return data

    def extract_registration_number(self, texts: List[OCRText]) -> Optional[str]:
        """Public helper method for registration number extraction."""
        return self._extract_registration_number_with_fallback(texts, side="unknown")

    # ── Side-Specific Extraction ──────────────────────────────────────────────

    def _extract_side(self, ocr_result: Optional[OCRResult], side: str = "unknown") -> RCData:
        if not ocr_result or not ocr_result.texts:
            return RCData()

        texts = ocr_result.texts
        data = RCData()

        data.registration_number = self._extract_field(texts, "registration_number", side)
        data.owner_name = self._extract_field(texts, "owner_name", side)
        data.vehicle_class = self._extract_field(texts, "vehicle_class", side)
        data.vehicle_type = self._extract_field(texts, "vehicle_type", side)
        data.fuel_type = self._extract_field(texts, "fuel_type", side)
        data.manufacturer = self._extract_field(texts, "manufacturer", side)
        data.model = self._extract_field(texts, "model", side)
        data.chassis_number = self._extract_field(texts, "chassis_number", side)
        data.engine_number = self._extract_field(texts, "engine_number", side)
        data.date_of_registration = self._extract_field(texts, "date_of_registration", side)
        data.registration_validity = self._extract_field(texts, "registration_validity", side)
        data.fitness_validity = self._extract_field(texts, "fitness_validity", side)
        data.insurance_validity = self._extract_field(texts, "insurance_validity", side)
        data.tax_validity = self._extract_field(texts, "tax_validity", side)
        data.issuing_rto = self._extract_field(texts, "issuing_rto", side)

        return data

    # ── Master Field Extractor ────────────────────────────────────────────────

    def _extract_field(self, texts: List[OCRText], field_name: str, side: str) -> Optional[str]:
        if field_name == "registration_number":
            reg_val = self._extract_registration_number_with_fallback(texts, side)
            if reg_val:
                return reg_val

        keywords = self._get_keywords_for_field(field_name)
        if not keywords:
            return None

        allow_multiline = field_name in ("owner_name", "manufacturer", "model", "vehicle_type", "issuing_rto")

        # First Attempt (with multiline if allowed)
        cand = self._get_best_candidate_for_keywords(
            texts=texts,
            keywords=keywords,
            field_type=field_name,
            side=side,
            allow_multiline=allow_multiline,
        )

        # Fallback for owner_name: Retry with allow_multiline=False if multiline failed validation
        if not cand and field_name == "owner_name" and allow_multiline:
            cand = self._get_best_candidate_for_keywords(
                texts=texts,
                keywords=keywords,
                field_type=field_name,
                side=side,
                allow_multiline=False,
            )

        if not cand:
            if self.debug:
                logger.info(f"[RC] SIDE={side.upper()} FIELD={field_name} -> None (no valid candidates)")
            return None

        val = cand.text.strip()

        if field_name == "registration_number":
            return normalize_rc_number(re.sub(r"[\s\-]", "", val.upper()))
        elif field_name == "owner_name":
            truncated = self._truncate_relation_marker(val)
            return truncated.upper()
        elif field_name in ("date_of_registration", "registration_validity", "fitness_validity", "insurance_validity", "tax_validity"):
            return normalize_date(val)
        elif field_name == "fuel_type":
            val_up = val.upper()
            for k, v in _FUEL_TYPES.items():
                if k in val_up:
                    return v
            return val_up
        elif field_name == "vehicle_class":
            val_up = val.upper()
            for vc in _VEHICLE_CLASSES:
                if vc in val_up:
                    return vc
            return val_up
        else:
            return val.upper()

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
            inline_val = self._extract_inline_value(label_box.text)
            if inline_val and not self._is_structural_label(inline_val):
                fmt_score, v_bonus = self._evaluate_candidate_format(inline_val, field_type)
                if fmt_score >= 0:
                    pref_side = _EXPECTED_FIELD_SIDE.get(field_type, "front")
                    side_score = 30.0 if (side == pref_side or side == "unknown") else 0.0
                    tot_score = 70.0 + fmt_score + v_bonus + side_score + (10.0 * label_box.confidence)
                    cand_obj = Candidate(
                        text=inline_val,
                        ocr_box=label_box,
                        label_box=label_box,
                        spatial_score=70.0,
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

        if self.debug:
            logger.info(
                f"[RC] SIDE={side.upper()} FIELD={field_type} FINAL SELECTED: {top.text!r} "
                f"(score={top.total_score:.1f}, rel={top.relationship})"
            )

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

        same_row_tolerance = max(20.0, l_height * 0.9)
        below_vertical_max = max(140.0, l_height * 4.5)

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

            on_same_row = abs(icy - lcy) <= same_row_tolerance and ix1 >= lx1 - 20
            is_below = iy1 >= ly2 - 5 and (iy1 - ly2) <= below_vertical_max and abs(icx - lx1) <= 250.0

            if not on_same_row and not is_below:
                continue

            relationship = "right" if on_same_row else "below"

            merged_text = text_clean
            if allow_multiline:
                merged_text = self._merge_continuation_boxes(texts, item, relationship, field_type)

            if relationship == "right":
                dist = max(0.0, ix1 - lx2)
                spatial_score = max(0.0, 60.0 - (dist / 4.0))
            else:
                dist = max(0.0, iy1 - ly2)
                spatial_score = max(0.0, 50.0 - (dist / 3.0))

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
        """
        Merges adjacent or vertically aligned multi-line OCR boxes belonging to the same value.
        For owner_name: STOPS MERGING at the first line containing digits (e.g. house number / address).
        """
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

            # Check horizontal continuation on same row
            if abs(other.bounding_box.center_y - curr.bounding_box.center_y) <= h_tol:
                dist = other.bounding_box.min_x - curr.bounding_box.max_x
                if 0 <= dist <= 130.0:
                    if field_type == "owner_name" and any(c.isdigit() for c in o_text):
                        break
                    merged_tokens.append(o_text)
                    curr = other
                    continue

            # Check vertical continuation on line below aligned
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

                score = 0.0
                if t_clean == kw_clean:
                    score = 100.0
                elif t_clean.startswith(kw_clean) or kw_clean.startswith(t_clean):
                    if len(t_clean) == len(kw_clean) or t_clean[len(kw_clean):len(kw_clean)+1] in (" ", ":", "."):
                        score = 90.0

                if score == 0.0 and len(kw_clean) >= 4 and len(t_clean) >= 4:
                    ratio = fuzz.ratio(kw_clean, t_clean)
                    if ratio >= 85.0:
                        score = ratio
                    else:
                        ts_ratio = fuzz.token_set_ratio(kw_clean, t_clean)
                        if ts_ratio >= 85.0 and abs(len(t_clean) - len(kw_clean)) <= 12:
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
        """Determines if text matches a canonical RC label using RapidFuzz (threshold ~85)."""
        clean = text.upper().strip().rstrip(":").rstrip(".").strip()
        if not clean:
            return True

        if text.strip().endswith(":") and len(text.strip()) <= 35:
            return True

        for lbl in _CANONICAL_RC_LABELS:
            lbl_clean = lbl.upper()
            if clean == lbl_clean or clean.startswith(lbl_clean + ":") or clean.startswith(lbl_clean + " "):
                return True
            if len(lbl_clean) >= 6 and len(clean) >= 4:
                if fuzz.token_set_ratio(lbl_clean, clean) >= 85.0 and abs(len(clean) - len(lbl_clean)) <= 15:
                    return True
                if fuzz.ratio(lbl_clean, clean) >= 85.0:
                    return True

        return False

    # ── Field-Specific Format Validation & Soft Hint Vocabulary Scoring ───────

    def _evaluate_candidate_format(self, text: str, field_type: str) -> Tuple[float, float]:
        clean_up = text.upper().strip()

        if field_type in ("owner_name", "model", "manufacturer", "chassis_number", "engine_number", "vehicle_class", "vehicle_type", "issuing_rto"):
            if normalize_date(text):
                return (-100.0, 0.0)

        if field_type in ("owner_name", "model", "manufacturer", "chassis_number", "engine_number", "issuing_rto"):
            if len(clean_up) != 17 and normalize_rc_number(re.sub(r"[\s\-]", "", clean_up)):
                return (-100.0, 0.0)

        if field_type == "registration_number":
            cleaned = re.sub(r"[\s\-]", "", clean_up)
            if normalize_rc_number(cleaned):
                return (60.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "owner_name":
            truncated = self._truncate_relation_marker(text)
            if self._is_plausible_owner_name(truncated):
                return (50.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "chassis_number":
            cleaned = re.sub(r"[\s\-]", "", clean_up)
            if _VIN_17_REGEX.match(cleaned) and self._is_valid_chassis(cleaned):
                return (100.0, 0.0)
            elif _CHASSIS_LOOSE_REGEX.match(cleaned) and self._is_valid_chassis(cleaned):
                return (40.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "engine_number":
            cleaned = re.sub(r"[\s\-]", "", clean_up)
            if _ENGINE_REGEX.match(cleaned) and self._is_valid_engine(cleaned):
                return (40.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "fuel_type":
            if "BS6" in clean_up or "BS4" in clean_up or "BHARAT" in clean_up:
                return (-100.0, 0.0)
            for k in _FUEL_TYPES:
                if k in clean_up:
                    return (40.0, 50.0)
            if len(clean_up) <= 25 and not self._is_structural_label(clean_up):
                return (20.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "vehicle_class":
            for vc in _VEHICLE_CLASSES:
                if vc in clean_up:
                    return (40.0, 50.0)
            if len(clean_up) <= 30 and not self._is_structural_label(clean_up):
                return (20.0, 0.0)
            return (0.0, 0.0)

        elif field_type == "vehicle_type":
            if len(clean_up) <= 35 and not self._is_structural_label(clean_up):
                return (40.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "manufacturer":
            if self.mfr_repo.is_known(clean_up):
                return (50.0, 60.0)
            if len(clean_up) <= 40 and not self._is_structural_label(clean_up):
                if not any(hdr in clean_up for hdr in ["CERTIFICATE", "UNION", "GOVERNMENT", "DEPARTMENT", "INDIAN"]):
                    return (30.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "model":
            if len(clean_up) <= 35 and not self._is_structural_label(clean_up):
                return (35.0, 0.0)
            return (-100.0, 0.0)

        elif field_type in ("date_of_registration", "registration_validity", "fitness_validity", "insurance_validity", "tax_validity"):
            if normalize_date(text):
                return (60.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "issuing_rto":
            if len(clean_up) <= 40 and not self._is_structural_label(clean_up):
                return (40.0, 0.0)
            return (-100.0, 0.0)

        return (10.0, 0.0)

    # ── Validation Helpers & Relation Marker Truncation ───────────────────────

    def _truncate_relation_marker(self, text: str) -> str:
        """Truncate owner name text before relation markers e.g. S/O, D/O, W/O, C/O."""
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
        words = text.split()
        if len(words) < 1 or len(words) > 6:
            return False
        for w in words:
            if not w.replace(".", "").replace("'", "").replace("-", "").isalpha():
                return False
        return not self._is_structural_label(text)

    def _is_valid_chassis(self, cleaned: str) -> bool:
        if not cleaned or len(cleaned) < 8 or len(cleaned) > 17:
            return False
        if any(w in cleaned for w in _BLACKLISTED_CHASSIS_WORDS):
            return False
        if not cleaned.isalnum() or cleaned.isalpha() or cleaned.isdigit():
            return False
        return True

    def _is_valid_engine(self, cleaned: str) -> bool:
        if not cleaned or len(cleaned) < 5 or len(cleaned) > 16:
            return False
        if self._is_structural_label(cleaned):
            return False
        if _RC_REGEX.search(cleaned) or normalize_date(cleaned):
            return False
        return cleaned.isalnum()

    def _extract_inline_value(self, text: str) -> Optional[str]:
        if ":" in text:
            parts = text.split(":", 1)
            val = parts[1].strip()
            return val if val and not self._is_structural_label(val) else None
        return None

    def _clean_inline_value(self, text: str) -> str:
        if ":" in text:
            parts = text.split(":", 1)
            if self._is_structural_label(parts[0]):
                return parts[1].strip()
        return text

    def _get_keywords_for_field(self, field_name: str) -> List[str]:
        mapping = {
            "registration_number": [
                "Regn.No", "Regn.Number", "Reg.No", "Registration No", "Registration Number",
                "Regn No", "Regd No", "Reg No", "Rexn.Number", "Veh Reg No",
            ],
            "owner_name": [
                "Name of Owner", "Owner Name", "Owner's Name", "Registered Owner",
                "Regn Owner", "Vehicle Owner", "Owner",
            ],
            "vehicle_class": [
                "Vehicle Class", "Class of Vehicle", "Veh Class", "VehidoCasS", "Class",
            ],
            "vehicle_type": [
                "Vehicle Type", "Type of Vehicle", "Type of Veh", "Body Type", "Veh Type",
            ],
            "fuel_type": [
                "Fuel Type", "Fuel Used", "Type of Fuel", "Fuel",
            ],
            "manufacturer": [
                "Maker's Name", "Maker Name", "Manufacturer Name", "Maker",
                "Manufacturer", "Make", "Mfr Name",
            ],
            "model": [
                "Model Name", "Mode Name", "Vehicle Model", "Veh Model", "Model",
            ],
            "chassis_number": [
                "Chassis No", "Chassis Number", "VIN", "Chasis No",
            ],
            "engine_number": [
                "Engine/Motor No", "Engine No", "Engine Number", "Eng No", "Engine",
            ],
            "date_of_registration": [
                "Date of Reg", "Date of Registration", "Reg Date", "Regn Date",
                "Registration Date", "Date of Regn", "Date of Reg.",
            ],
            "registration_validity": [
                "Regn.Validity", "Reg. Validity", "Regn Upto", "Registration Upto",
                "Reg Upto", "Registration Valid Upto", "Regn Valid Till", "Registration Validity",
            ],
            "fitness_validity": [
                "Fitness Upto", "Fitness Valid Upto", "Fitness Valid Till",
                "Fitness Validity", "FC Upto", "Fit Upto",
            ],
            "insurance_validity": [
                "Insurance Upto", "Insurance Valid Upto", "Ins Upto",
                "Insurance Validity", "Insurance Expiry",
            ],
            "tax_validity": [
                "Tax Upto", "Tax Valid Upto", "Tax Validity", "Road Tax Upto",
            ],
            "issuing_rto": [
                "Registration Authority", "Registering Authority", "RegistratcnAutroxityd",
                "Issuing Authority", "RTO", "Issued At", "Office",
            ],
        }
        return mapping.get(field_name, [])

    def _extract_registration_number_with_fallback(
        self, texts: List[OCRText], side: str
    ) -> Optional[str]:
        label_keywords = self._get_keywords_for_field("registration_number")
        cand = self._get_best_candidate_for_keywords(
            texts, label_keywords, field_type="registration_number", side=side
        )
        if cand:
            norm = normalize_rc_number(re.sub(r"[\s\-]", "", cand.text.upper()))
            if norm:
                return norm

        for item in texts:
            m = _RC_REGEX.search(item.text)
            if m:
                norm = normalize_rc_number(m.group(1))
                if norm:
                    return norm

        full = " ".join(t.text.upper() for t in texts)
        m = _RC_REGEX.search(full)
        if m:
            norm = normalize_rc_number(m.group(1))
            if norm:
                return norm

        return None

    def _apply_cross_field_sanity(self, data: RCData) -> None:
        """Cross-field consistency and sanity checks."""
        if data.manufacturer and data.model and data.manufacturer.strip().upper() == data.model.strip().upper():
            data.model = None

        if data.chassis_number and data.engine_number and data.chassis_number.strip().upper() == data.engine_number.strip().upper():
            data.engine_number = None

        if data.owner_name and self._is_structural_label(data.owner_name):
            data.owner_name = None
