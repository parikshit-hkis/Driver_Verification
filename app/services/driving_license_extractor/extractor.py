"""
Driving Licence Extractor
=========================
Extracts and normalizes:
  - Licence number (All-India DL formats: GJ, UP, MH, RJ, KA, DL, etc.)
  - Full name (Given Name + Surname)
  - Date of birth (ISO YYYY-MM-DD)
  - Issue date & expiry date / validity (ISO YYYY-MM-DD)
  - Vehicle classes (MCWG, LMV, HMV, HPMV, TRANS, 3W-CAB, LMV-CAB, LMV-NT, etc.)

Features:
  1. Side-isolated processing (extract_dl) preventing back-side OCR noise from overwriting front-side fields.
  2. Multi-side merging: Union of unique vehicle classes across front and back sides.
  3. Strict Semantic & Layout Date Resolution (DLDateResolver):
     - Extract DOB first; DOB candidate is excluded from issue/expiry search.
     - Label & Spatial & Table-aware matching using _ISSUE_KEYWORDS and _EXPIRY_KEYWORDS.
     - Semantic validation: Issue != Expiry, Expiry > Issue, Issue >= DOB, Issue <= Current Date, Expiry > DOB.
     - No unsafe chronological fallback: returns None when semantic evidence is missing.
  4. Name Protection: Blacklists structural labels ("DATE OF FIRST ISSUE", "AHMEDABAD RTO") from becoming full_name.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Set, Tuple, Dict

from app.models.ocr_models import OCRResult, OCRText
from app.services.base_extractor import BaseExtractor
from app.services.driving_license_extractor.models import DrivingLicenceData
from app.utils.normalizer import normalize_dob, normalize_date, normalize_dl_number, normalize_name, _DATE_PATTERNS


# ── All-India DL number pattern ──────────────────────────────────────────────
_DL_REGEX = re.compile(
    r"\b([A-Z]{2}\s*[-]?\s*\d{2}[A-Z0-9]?\s*[-]?\s*\d{4}\s*[-]?\s*\d{7})\b",
    re.IGNORECASE,
)

# Known vehicle class codes on Indian DLs
_VEHICLE_CLASSES: Set[str] = {
    "MCWG", "MCWO", "MCWOG", "LMV", "LMY", "LMV-NT", "LMV-TR", "LMV-CAB", "LMVCAB","HMV", "HPMV",
    "HGMV", "MGV", "HTV","TRANS", "TRANSPORT", "AGRTLR","3W-NT", "3W-TR", "3WNT", "3WTR", "3W-CAB",
    "3WCAB","FVG", "ADAPTED", "INVCR", "PSV-BUS", "PSVBUS", "TRACTOR", "TRCTOR", "LDRXCV",
    }

_ISSUE_KEYWORDS = [
    "DATE OF ISSUE","ISSUE DATE","DATE OF FIRST ISSUE","DATE OF 1ST ISSUE",
    "FIRST ISSUE DATE","FIRST ISSUE","DOI",
    ]

_EXPIRY_KEYWORDS = [
    "VALIDITY","VALIDITY UPTO","VALID UPTO","VALID TILL","VALID UNTIL",
    "VALID TO","EXPIRY DATE","EXPIRY","EXPIRATION DATE","Licence Validity","Issue DateValidity(NT)",
    ]

_DOB_KEYWORDS = ["DATE OF BIRTH","BIRTH DATE","DATE OF BIRT","DOB","D.O.B"]

_NAME_BLACKLIST = {
    "UNION", "INDIAN", "DRIVING", "LICENCE", "LICENSE", "GOVERNMENT", "GOVT",
    "STATE", "TRANSPORT", "DEPARTMENT", "AUTHORITY", "REGISTERING", "ISSUING",
    "DATE", "ISSUE", "VALIDITY", "EXPIRE", "EXPIRY", "BIRTH", "BLOOD", "GROUP",
    "ORGAN", "DONOR", "ADDRESS", "FORM", "RULE", "CLASS", "VEHICLE", "CATEGORY",
    "CODE", "BADGE", "NUMBER", "EMERGENCY", "CONTACT", "SIGNATURE", "HOLDER",
    "MVSD", "UP66", "UTTAR", "PRADESH", "GUJARAT", "MAHARASHTRA", "RAJASTHAN",
    "FIRST", "DATE OF FIRST ISSUE", "DATE OF ISSUE", "FIRST ISSUE", "ISSUE DATE",
    "OFFICER", "AHMEDABAD", "RTO", "AHMEDABAD RTO", "REGISTERING AUTHORITY",
    "ISSUING AUTHORITY", "HOLDER'S SIGNATURE", "HOLDER SIGNATURE", "'S SIGNATURE",
}


@dataclass
class DateCandidate:
    date: str               # ISO YYYY-MM-DD
    text: str               # Raw text string
    box: OCRText            # OCR text item
    confidence: float       # OCR confidence
    context: Optional[str] = None
    label_score: float = 0.0
    spatial_score: float = 0.0
    semantic_score: float = 0.0
    total_score: float = 0.0


class DrivingLicenceExtractor(BaseExtractor):
    """Extracts structured data from Driving Licence OCR output using layout & semantic validation."""

    def extract_dl(self, ocr_front: Optional[OCRResult], ocr_back: Optional[OCRResult]) -> DrivingLicenceData:
        """Process front and back sides independently to avoid cross-side contamination."""
        
        data_front = self._extract_side(ocr_front, side="front") if ocr_front else None
        data_back = self._extract_side(ocr_back, side="back") if ocr_back else None

        if data_front is None and data_back is None:
            return DrivingLicenceData()
        if data_front is None:
            return data_back
        if data_back is None:
            return data_front

        merged = DrivingLicenceData()
        merged.licence_number = data_front.licence_number or data_back.licence_number
        merged.full_name = data_front.full_name or data_back.full_name
        merged.date_of_birth = data_front.date_of_birth or data_back.date_of_birth
        merged.issue_date = data_front.issue_date or data_back.issue_date
        merged.expiry_date = data_front.expiry_date or data_back.expiry_date
        merged.vehicle_classes = self._combine_vehicle_classes(
            data_front.vehicle_classes, data_back.vehicle_classes
        )

        # Merge diagnostics from both sides — only keep diagnostics for fields still missing
        for key, reason in data_front.field_diagnostics.items():
            if getattr(merged, key, None) is None or (isinstance(getattr(merged, key, None), list) and not getattr(merged, key)):
                merged.field_diagnostics[key] = reason
        for key, reason in data_back.field_diagnostics.items():
            if getattr(merged, key, None) is None or (isinstance(getattr(merged, key, None), list) and not getattr(merged, key)):
                if key not in merged.field_diagnostics:
                    merged.field_diagnostics[key] = reason

        return merged

    def extract(self, ocr_result: OCRResult) -> DrivingLicenceData:
        """Single OCR result entry point for backward compatibility."""
        return self._extract_side(ocr_result, side="unknown")

    def _extract_side(self, ocr_result: Optional[OCRResult], side: str = "unknown") -> DrivingLicenceData:
        if not ocr_result or not ocr_result.texts:
            return DrivingLicenceData()

        # Filter out vertical side margin text boxes (x > 2550)
        filtered_texts = [t for t in ocr_result.texts if t.bounding_box.min_x <= 2550]
        texts = filtered_texts if filtered_texts else ocr_result.texts
        data = DrivingLicenceData()

        data.licence_number = self.extract_licence_number(texts)

        # 1. Extract DOB first
        data.date_of_birth = self.extract_dob(texts)

        # 2. Extract Full Name (protecting against structural labels)
        name_raw = self.extract_name_raw(texts)
        if name_raw:
            parsed = normalize_name(name_raw)
            data.full_name = parsed["full_name"]

        # 3. Resolve Issue Date & Expiry Date via Semantic & Layout Resolver
        self._resolve_issue_and_expiry_dates(texts, data)

        # 4. Extract Vehicle Classes
        data.vehicle_classes = self.extract_vehicle_classes(texts, side=side)

        # 5. Diagnostics for missing fields
        self._generate_diagnostics(data, texts)

        return data

    # ── Date Candidate Collection & Resolution Layer ─────────────────────────


    def _distance(self,box_a, box_b) -> float:
        """Euclidean distance between the centers of two OCR bounding boxes."""
        ax = (box_a.min_x + box_a.max_x) / 2
        ay = (box_a.min_y + box_a.max_y) / 2
        bx = (box_b.min_x + box_b.max_x) / 2
        by = (box_b.min_y + box_b.max_y) / 2
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


    def _collect_date_candidates(self, texts: List["OCRText"]) -> List["DateCandidate"]:
        """Collect all valid date candidates using the global pattern mapping."""
        candidates = []
        for item in texts:
            if item.bounding_box.min_x > 2550:
                continue
            for pattern, fmt in _DATE_PATTERNS:
                for m in re.finditer(pattern, item.text, re.IGNORECASE):
                    matched_text = m.group(0)
                    parsed = normalize_date(matched_text)
                    if parsed and parsed != "0000-00-00":
                        candidates.append(
                            DateCandidate(
                                date=parsed,
                                text=matched_text,
                                box=item,
                                confidence=item.confidence,
                                context=item.text,
                            )
                        )
        return candidates


    def _find_labels(self,texts: List["OCRText"], keywords: List[str]) -> List["OCRText"]:
        """Return OCR boxes whose text matches one of the given keywords (skip headers)."""
        kw_upper = [k.upper() for k in keywords]
        labels = []
        for t in texts:
            up = t.text.upper().strip().rstrip(":").strip()
            if "GOVERNMENT" in up or "AUTHORITY" in up:
                continue
            if any(kw in up for kw in kw_upper):
                labels.append(t)
        return labels


    def _closest_candidate(self,labels: List["OCRText"], candidates: List["DateCandidate"]) -> Optional["DateCandidate"]:
        """Return the date candidate whose box is nearest to any of the given labels."""
        best_cand, best_dist = None, float("inf")
        for label in labels:
            for cand in candidates:
                dist = self._distance(cand.box.bounding_box, label.bounding_box)
                if dist < best_dist:
                    best_dist, best_cand = dist, cand
        return best_cand


    def _resolve_issue_and_expiry_dates(self, texts: List["OCRText"], data: "DrivingLicenceData") -> None:
        """Pick issue/expiry dates as whichever date candidate sits closest to each label."""
        candidates = self._collect_date_candidates(texts)

        # Never reuse DOB as issue/expiry
        excluded_dates = {data.date_of_birth} if data.date_of_birth else set()
        available = [c for c in candidates if c.date not in excluded_dates]
        issue_label=self._find_labels(texts, _ISSUE_KEYWORDS)
        issue_candidate = self._closest_candidate(issue_label, available)

        # Don't let expiry reuse the same box picked for issue
        expiry_pool = [c for c in available if c is not issue_candidate]
        expiry_label=self._find_labels(texts, _EXPIRY_KEYWORDS)
        expiry_candidate = self._closest_candidate(expiry_label, expiry_pool)

        resolved_issue = issue_candidate.date if issue_candidate else None
        resolved_expiry = expiry_candidate.date if expiry_candidate else None

        current_date = datetime.now().strftime("%Y-%m-%d")

        # Sanity checks
        if resolved_issue and data.date_of_birth and resolved_issue < data.date_of_birth:
            resolved_issue = None
        if resolved_issue and resolved_issue > current_date:
            resolved_issue = None
        if resolved_expiry and data.date_of_birth and resolved_expiry < data.date_of_birth:
            resolved_expiry = None
        if resolved_issue and resolved_expiry and resolved_expiry <= resolved_issue:
            resolved_expiry = None

        data.issue_date = resolved_issue
        data.expiry_date = resolved_expiry

    # ── Licence Number ────────────────────────────────────────────────────────

    def extract_licence_number(self, texts: List[OCRText]) -> Optional[str]:
        label_keywords = [
            "Licence No", "License No", "DL No", "D/L No",
            "DL Number", "Licence Number", "License Number",
            "Driving Licence No", "DLNO", "DL NO", "DLNo",
        ]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=600.0, same_row_tolerance=40.0)
        if raw:
            norm = normalize_dl_number(raw)
            if norm:
                return norm

        for item in texts:
            m = _DL_REGEX.search(item.text)
            if m:
                norm = normalize_dl_number(m.group(1))
                if norm:
                    return norm

        full = " ".join(t.text for t in texts)
        m = _DL_REGEX.search(full)
        if m:
            norm = normalize_dl_number(m.group(1))
            if norm:
                return norm

        return None

    # ── Date of Birth (Phase 3: DOB First) ────────────────────────────────────

    def extract_dob(self, texts: List[OCRText]) -> Optional[str]:
        """Pick DOB as the date candidate closest to a DOB label, validated as a past date."""
        current_year = datetime.now().year

        candidates = self._collect_date_candidates(texts)
        labels = self._find_labels(texts, _DOB_KEYWORDS)

        dob_candidate = self._closest_candidate(labels, candidates)

        if dob_candidate:
            yr = int(dob_candidate.date.split("-")[0])
            if yr <= current_year - 16:
                return dob_candidate.date

        return None

    # ── Name (Phase 12: Structural Name Rejection) ────────────────────────────

    def extract_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        # 1. Inline label check
        for item in texts:
            up = item.text.upper().strip()
            m = re.match(r"^(?:NAME|HOLDER|APPLICANT|MAME)[\s:\-/]*([A-Z\.\s']{3,})", up)
            if m:
                val = m.group(1).strip()
                val_clean = self._strip_name_prefix(val)
                if self._is_plausible_name(val_clean):
                    return val_clean

       # 2. Strict label matching near "Name:", "MAME", "Holder"
        name_label = None
        for t in texts:
            clean = t.text.upper().strip().rstrip(":").strip()
            if clean in [
                "NAME", "MAME", "APPLICANT NAME", "HOLDER NAME",
                "DL NUMBER HOLDER NAME",          # ← was lowercase, never matched
            ]:
                name_label = t
                break

        if name_label:
            l_cy = name_label.bounding_box.center_y
            l_x2 = name_label.bounding_box.max_x
            l_x1 = name_label.bounding_box.min_x
            l_y2 = name_label.bounding_box.max_y

            cands = []
            for t in texts:
                if t is name_label or t.bounding_box.min_x > 2500:
                    continue
                icy = t.bounding_box.center_y
                ix1 = t.bounding_box.min_x

                # Same row, to the right (original case: "Name: RAJAN KUMAR")
                if abs(icy - l_cy) <= 45.0 and ix1 >= l_x2 - 20:
                    cleaned = self._strip_name_prefix(t.text)
                    if self._is_plausible_name(cleaned):
                        cands.append((max(0.0, ix1 - l_x2), cleaned))

            # NEW: value sits BELOW the label instead of beside it
            # (e.g. "DL Number Holder Name" header with the name on the next line)
            if not cands:
                below_cands = []
                for t in texts:
                    if t is name_label or t.bounding_box.min_x > 2500:
                        continue
                    t_min_y = t.bounding_box.min_y
                    # within ~120px directly below the label
                    if l_y2 - 5 <= t_min_y <= l_y2 + 120:
                        cleaned = self._strip_name_prefix(t.text)
                        if self._is_plausible_name(cleaned):
                            below_cands.append((t_min_y - l_y2, cleaned))
                if below_cands:
                    below_cands.sort(key=lambda c: c[0])
                    cands.append(below_cands[0])

            if cands:
                cands.sort(key=lambda c: c[0])
                return cands[0][1]

        # 3. Look for text box immediately ABOVE "S/O" / "D/O" / "W/O" label
        rel_label = self._find_label_box(texts, ["S/O", "D/O", "W/O", "S/W/D", "Son/Daughter", "Sor/Daughter", "Son/Daughter/Wife of", "SonDavghter"])
        if rel_label:
            rel_y = rel_label.bounding_box.min_y
            above_candidates = [
                t for t in texts
                if t.bounding_box.max_y < rel_y + 20
                and t.bounding_box.max_y > rel_y - 150
            ]
            for t in above_candidates:
                cleaned = self._strip_name_prefix(t.text)
                if self._is_plausible_name(cleaned):
                    return cleaned

        # 4. Fallback search across sorted text items requiring multi-word or lon   g name strings
        sorted_texts = sorted(texts, key=lambda t: t.confidence, reverse=True)
        for item in sorted_texts:
            cleaned = self._strip_name_prefix(item.text)
            if self._is_plausible_name(cleaned) and item.confidence >= 0.85:
                words = cleaned.split()
                if len(words) >= 2 and len(cleaned) >= 6:
                    return cleaned

        return None

    @staticmethod
    def _strip_name_prefix(text: str) -> str:
        stripped = re.sub(
            r'^(?:name|holder|applicant|mame)[\s:\-/]*',
            '',
            text,
            flags=re.IGNORECASE,
        ).strip()
        return stripped if stripped else text

    def _is_plausible_name(self, text: str) -> bool:
        """Phase 12: Structural phrases and document labels must be rejected as names."""
        if not text:
            return False
        clean = text.upper().strip()

        # Reject exact blacklist matches or phrases containing structural label terms
        if clean in _NAME_BLACKLIST:
            return False

        # Structural label keywords that can never be part of a person's name
        structural_terms = [
            "FIRST ISSUE", "DATE OF ISSUE", "DATE OF FIRST ISSUE", "ISSUE DATE",
            "VALIDITY", "VALID TILL", "VALID UPTO", "EXPIRY", "EXPIRY DATE",
            "DATE OF BIRTH", "REGISTERING", "AUTHORITY", "AHMEDABAD", "GUJARAT",
            "MAHARASHTRA", "RAJASTHAN", "STATE", "TRANSPORT", "GOVERNMENT",
            "SIGNATURE", "HOLDER", "LICENCE", "LICENSE", "UNION", "INDIAN", "RTO",
            "BLOOD", "BLOOD GROUP", "FORM", "RULE", "MVSD", "AUTHORISED",
        ]
        if any(term in clean for term in structural_terms):
            return False

        words = clean.split()
        if len(words) < 1 or len(words) > 5:
            return False
        for w in words:
            if not w.replace(".", "").replace("'", "").replace("-", "").isalpha():
                return False
        return True

    # ── Vehicle Classes ───────────────────────────────────────────────────────

    def extract_vehicle_classes(self,texts: List[OCRText],side: str = "unknown") -> List[str]:

        found = set()

        # Get OCR boxes containing valid dates
        date_boxes = [
            t for t in texts
            if normalize_date(t.text)
        ]

        for item in texts:
            text = item.text.upper().strip()

            for vc in _VEHICLE_CLASSES:
                if vc not in text:
                    continue

                # If the class and date are in the same OCR box,
                # accept the class directly.
                if normalize_date(item.text):
                    found.add(self._normalize_vehicle_class(vc))
                    continue

                # Otherwise, class must be near a date on the same row.
                class_cy = item.bounding_box.center_y
                class_x2 = item.bounding_box.max_x

                for date_box in date_boxes:

                    # Don't compare the box with itself
                    if date_box is item:
                        continue

                    date_cy = date_box.bounding_box.center_y
                    date_x1 = date_box.bounding_box.min_x

                    # Same-row requirement
                    same_row = abs(class_cy - date_cy) <= 45.0

                    if not same_row:
                        continue

                    # Date should be reasonably close to the class.
                    # Mainly supports:
                    #
                    # MCWG       28-Feb-2025
                    #
                    # or
                    #
                    # MCWG,LMV   28-Feb-2025
                    horizontal_distance = date_x1 - class_x2

                    if -50.0 <= horizontal_distance <= 500.0:
                        found.add(self._normalize_vehicle_class(vc))
                        break

        # ---------------------------------------------------------
        # SECOND PRIORITY / FALLBACK:
        # Vehicle class associated with "Vehicle Class" label
        # ---------------------------------------------------------

        vehicle_class_labels = [
            t for t in texts
            if "VEHICLE CLASS" in t.text.upper()
        ]

        for item in texts:
            text = item.text.upper().strip()

            for vc in _VEHICLE_CLASSES:
                if vc not in text:
                    continue

                class_cy = item.bounding_box.center_y
                class_x1 = item.bounding_box.min_x

                for label in vehicle_class_labels:

                    label_cy = label.bounding_box.center_y
                    label_x2 = label.bounding_box.max_x
                    label_y2 = label.bounding_box.max_y

                    # Same row and class is to the right
                    same_row = abs(class_cy - label_cy) <= 300.0

                    right_of_label = class_x1 >= label_x2 - 100.0

                    

                    if (same_row and right_of_label):
                        found.add(self._normalize_vehicle_class(vc))
                        break

        return self._sort_vehicle_classes(list(found))


    def _normalize_vehicle_class(self, value: str) -> str:
        return {
            "LMVCAB": "LMV-CAB",
            "LMY": "LMV",
            "3WNT": "3W-NT",
            "3WTR": "3W-TR",
            "3WCAB": "3W-CAB",
            "TRANSPORT": "TRANS",
            "PSVBUS": "PSV-BUS",
            "TRCTOR": "TRACTOR",
            "MCWO": "MCWOG",
        }.get(value, value)

    @staticmethod
    def _sort_vehicle_classes(classes: List[str]) -> List[str]:
        order = ["MCWG", "MCWOG", "LMV", "LMV-NT", "LMV-TR", "LMV-CAB", "HMV", "HPMV", "HTV", "TRANS", "3W-NT", "3W-TR", "3W-CAB","TRACTOR","TRCTOR"]
        return sorted(
            list(set(classes)),
            key=lambda c: order.index(c) if c in order else 99
        )

    def _combine_vehicle_classes(self, vc_front: Optional[List[str]], vc_back: Optional[List[str]]) -> List[str]:
        combined = set(vc_front or []) | set(vc_back or [])
        return self._sort_vehicle_classes(list(combined))

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def _generate_diagnostics(self, data: DrivingLicenceData, texts: List[OCRText]) -> None:
        """For every missing field, explain why OCR failed to extract it."""
        if not texts:
            for field in ["licence_number", "full_name", "date_of_birth", "issue_date", "expiry_date", "vehicle_classes"]:
                data.field_diagnostics[field] = "OCR returned no text from image"
            return

        avg_conf = sum(t.confidence for t in texts) / len(texts)
        low_quality_msg = ""
        if avg_conf < 0.5:
            low_quality_msg = f"Low OCR confidence ({avg_conf:.0%}); image may be blurry or low quality"

        if not data.licence_number:
            data.field_diagnostics["licence_number"] = low_quality_msg or "No DL number pattern (SS-RR-YYYY-NNNNNNN) found in OCR text"

        if not data.full_name:
            data.field_diagnostics["full_name"] = low_quality_msg or "No plausible name text found near 'Name' label"

        if not data.date_of_birth:
            data.field_diagnostics["date_of_birth"] = low_quality_msg or "No date found near DOB/Birth label"

        if not data.issue_date:
            data.field_diagnostics["issue_date"] = low_quality_msg or "No issue date found; tabular header or 'Date of Issue' label not detected"

        if not data.expiry_date:
            data.field_diagnostics["expiry_date"] = low_quality_msg or "No expiry/validity date found; validity label not detected in OCR text"

        if not data.vehicle_classes:
            data.field_diagnostics["vehicle_classes"] = low_quality_msg or "No vehicle class codes (MCWG, LMV, etc.) found in OCR text"
