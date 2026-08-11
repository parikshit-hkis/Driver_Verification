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
  3. Comprehensive Validity & Expiry parsing: Supports "Validity (NT)", "Validity", "Valid Till", "Valid Upto", "Valid To", "Expiry Date", "EXP", "VAL", and tabular headers.
  4. Old DL support: Extracts vehicle classes from tables and upper-left back-side regions below licence numbers.
  5. Bounding box spatial reasoning and rejection of side margin noise.
"""

import re
from typing import List, Optional, Set, Tuple

from app.models.ocr_models import OCRResult, OCRText
from app.services.base_extractor import BaseExtractor
from app.services.driving_license_extractor.models import DrivingLicenceData
from app.utils.normalizer import normalize_dob, normalize_date, normalize_dl_number, normalize_name


# ── All-India DL number pattern ──────────────────────────────────────────────
_DL_REGEX = re.compile(
    r"\b([A-Z]{2}\s*[-]?\s*\d{2}[A-Z0-9]?\s*[-]?\s*\d{4}\s*[-]?\s*\d{7})\b",
    re.IGNORECASE,
)

# Known vehicle class codes on Indian DLs (COV removed as it is a header, not a vehicle class)
_VEHICLE_CLASSES: Set[str] = {
    "MCWG", "MCWOG", "LMV", "LMV-NT", "LMV-TR", "LMV-CAB", "LMVCAB",
    "HMV", "HPMV", "HGMV", "MGV", "HTV",
    "TRANS", "TRANSPORT",
    "3W-NT", "3W-TR", "3WNT", "3WTR", "3W-CAB", "3WCAB",
    "FVG", "ADAPTED", "INVCR", "PSV-BUS", "PSVBUS", "TRACTOR", "LDRXCV",
}

_VC_PATTERNS = [
    (re.compile(r"\bLMV\s*[\(\-]?\s*NT\b", re.IGNORECASE), "LMV-NT"),
    (re.compile(r"\bLMV\s*[\(\-]?\s*TR\b", re.IGNORECASE), "LMV-TR"),
    (re.compile(r"\bLMV\s*[\(\-]?\s*CAB\b", re.IGNORECASE), "LMV-CAB"),
    (re.compile(r"\b3W\s*[\(\-]?\s*CAB\b", re.IGNORECASE), "3W-CAB"),
    (re.compile(r"\b3W\s*[\(\-]?\s*NT\b", re.IGNORECASE), "3W-NT"),
    (re.compile(r"\b3W\s*[\(\-]?\s*TR\b", re.IGNORECASE), "3W-TR"),
    (re.compile(r"\bMCWG\b", re.IGNORECASE), "MCWG"),
    (re.compile(r"\bMCWOG\b|\bMCOG\b|\bM/CYC(?:LE)?\b", re.IGNORECASE), "MCWOG"),
    (re.compile(r"\bLMV\b", re.IGNORECASE), "LMV"),
    (re.compile(r"\bHMV\b", re.IGNORECASE), "HMV"),
    (re.compile(r"\bHPMV\b", re.IGNORECASE), "HPMV"),
    (re.compile(r"\bHGMV\b", re.IGNORECASE), "HGMV"),
    (re.compile(r"\bHTV\b", re.IGNORECASE), "HTV"),
    (re.compile(r"\bTRANS(?:PORT)?\b", re.IGNORECASE), "TRANS"),
    (re.compile(r"\bADAPTED\b|\bINVCR\b", re.IGNORECASE), "ADAPTED"),
    (re.compile(r"\bPSV[\-\s]?BUS\b", re.IGNORECASE), "PSV-BUS"),
    (re.compile(r"\bTRACTOR\b", re.IGNORECASE), "TRACTOR"),
]

_EXPIRY_KEYWORDS = [
    "VALIDITY(NT)", "VALIDITY (NT)", "VALIDITY NT", "VALIDITY-NT",
    "VALIDITY(TR)", "VALIDITY (TR)", "VALIDITY TR", "VALIDITY-TR",
    "VALIDITY", "VALID TILL", "VALID UPTO", "VALID TO", "VALID UNTIL",
    "EXPIRY DATE", "EXPIRY", "EXP DATE", "EXPIRES ON", "EXPIRES", "EXP",
    "VAL DATE", "VAL TILL", "VAL UPTO", "VAL", "VALID","NT","Valie",
]

_NAME_BLACKLIST = {
    "UNION", "INDIAN", "DRIVING", "LICENCE", "LICENSE", "GOVERNMENT", "GOVT",
    "STATE", "TRANSPORT", "DEPARTMENT", "AUTHORITY", "REGISTERING", "ISSUING",
    "DATE", "ISSUE", "VALIDITY", "EXPIRE", "EXPIRY", "BIRTH", "BLOOD", "GROUP",
    "ORGAN", "DONOR", "ADDRESS", "FORM", "RULE", "CLASS", "VEHICLE", "CATEGORY",
    "CODE", "BADGE", "NUMBER", "EMERGENCY", "CONTACT", "SIGNATURE", "HOLDER",
    "MVSD", "UP66", "UTTAR", "PRADESH", "GUJARAT", "MAHARASHTRA", "RAJASTHAN",
    "HOLDER'S SIGNATURE", "HOLDER SIGNATURE", "'S SIGNATURE",
}


class DrivingLicenceExtractor(BaseExtractor):
    """Extracts structured data from Driving Licence OCR output."""

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
        data.date_of_birth = self.extract_dob(texts)

        name_raw = self.extract_name_raw(texts)
        if name_raw:
            parsed = normalize_name(name_raw)
            data.full_name = parsed["full_name"]

        # Parse tabular issue & expiry/validity dates
        issue_dt, expiry_dt = self._extract_tabular_dates(texts, data.date_of_birth)
        data.issue_date = issue_dt or self.extract_issue_date(texts)
        data.expiry_date = expiry_dt or self.extract_expiry_date(texts)

        # Standalone date-pair fallback: find all dates and pick issue/expiry by chronological order
        if not data.issue_date or not data.expiry_date:
            self._fallback_date_pair(texts, data)

        data.vehicle_classes = self.extract_vehicle_classes(texts, side=side)

        # Generate diagnostics for missing fields
        self._generate_diagnostics(data, texts)

        return data

    def _fallback_date_pair(self, texts: List[OCRText], data: DrivingLicenceData) -> None:
        """Find all date-like text on the DL and assign issue/expiry by chronological order."""
        date_pat = r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})"
        all_dates = []
        for item in texts:
            for m in re.finditer(date_pat, item.text):
                parsed = normalize_date(m.group(1))
                if parsed and parsed != "0000-00-00" and parsed != data.date_of_birth:
                    all_dates.append((parsed, item.bounding_box.min_y))

        # Deduplicate and sort chronologically
        unique_dates = sorted(set(d[0] for d in all_dates))
        if len(unique_dates) >= 2 and not data.issue_date and not data.expiry_date:
            # Earliest = issue, Latest = expiry
            data.issue_date = unique_dates[0]
            data.expiry_date = unique_dates[-1]
        elif len(unique_dates) == 1:
            if not data.expiry_date:
                data.expiry_date = unique_dates[0]

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

    # ── Date of Birth ─────────────────────────────────────────────────────────

    def extract_dob(self, texts: List[OCRText]) -> Optional[str]:
        date_pat = r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})"

        # 1. Inline check e.g. "Date of Birth:01-12-2000"
        for item in texts:
            up = item.text.upper()
            if any(kw in up for kw in ["DOB", "BIRTH", "BIRT", "BRTH"]):
                m = re.search(date_pat, item.text)
                if m:
                    parsed = normalize_dob(m.group(1))
                    if parsed:
                        return parsed

        # 2. Label proximity search with tight horizontal row matching
        dob_label = None
        for t in texts:
            clean = t.text.upper().strip().rstrip(":").strip()
            if clean in ["DATE OF BIRTH", "DOB", "D.O.B", "BIRTH DATE", "DATE OF BIRT"]:
                dob_label = t
                break

        if dob_label:
            l_cy = dob_label.bounding_box.center_y
            l_x2 = dob_label.bounding_box.max_x
            cands = []
            for t in texts:
                if t is dob_label or t.bounding_box.min_x > 2500:
                    continue
                icy = t.bounding_box.center_y
                ix1 = t.bounding_box.min_x
                if abs(icy - l_cy) <= 45.0 and ix1 >= l_x2 - 20:
                    dt = normalize_dob(t.text)
                    if dt:
                        cands.append((max(0.0, ix1 - l_x2), dt))
            if cands:
                cands.sort(key=lambda c: c[0])
                return cands[0][1]

        # 3. Standard label proximity fallback
        label_keywords = [
            "DOB", "Date of Birth", "D.O.B", "Date Of Birth",
            "Birth Date", "Date Of Birt", "जन्म तिथि",
        ]
        raw = self.find_value_near_label(texts, label_keywords, direction="auto", max_distance=600.0, same_row_tolerance=50.0)
        if raw:
            parsed = normalize_dob(raw)
            if parsed:
                return parsed

        return None

    # ── Name ─────────────────────────────────────────────────────────────────

    def extract_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        # 1. Inline label check e.g. "Name:RAJAN KUMAR SAROJ"
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
            if clean in ["NAME", "MAME", "APPLICANT NAME", "HOLDER NAME"]:
                name_label = t
                break

        if name_label:
            l_cy = name_label.bounding_box.center_y
            l_x2 = name_label.bounding_box.max_x
            cands = []
            for t in texts:
                if t is name_label or t.bounding_box.min_x > 2500:
                    continue
                icy = t.bounding_box.center_y
                ix1 = t.bounding_box.min_x
                if abs(icy - l_cy) <= 45.0 and ix1 >= l_x2 - 20:
                    cleaned = self._strip_name_prefix(t.text)
                    if self._is_plausible_name(cleaned):
                        cands.append((max(0.0, ix1 - l_x2), cleaned))
            if cands:
                cands.sort(key=lambda c: c[0])
                return cands[0][1]

        # 3. Look for text box immediately ABOVE "S/O" / "D/O" / "W/O" label
        rel_label = self._find_label_box(texts, ["S/O", "D/O", "W/O", "S/W/D", "Son/Daughter", "Sor/Daughter", "Son/Daughter/Wife of", "SonDavghter"])
        if rel_label:
            rel_y = rel_label.bounding_box.min_y
            above_candidates = [
                t for t in texts
                if t.bounding_box.max_y < rel_y + 10
                and t.bounding_box.max_y > rel_y - 80
            ]
            for t in above_candidates:
                cleaned = self._strip_name_prefix(t.text)
                if self._is_plausible_name(cleaned):
                    return cleaned

        # 4. Fallback search across sorted text items requiring multi-word or long name strings
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

    # ── Tabular Issue & Expiry Dates ──────────────────────────────────────────

    def _extract_tabular_dates(self, texts: List[OCRText], dob_val: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        issue_date = None
        expiry_date = None

        header_box = None
        for t in texts:
            up = t.text.upper()
            if ("ISSUE" in up or "DOI" in up) and ("VALIDITY" in up or "VALID" in up or "EXPIRY" in up) and "GOVERNMENT" not in up:
                header_box = t
                break

        # Fallback: check if header box is just VALIDITY / EXPIRY / VALID TILL without ISSUE in same box
        if not header_box:
            for t in texts:
                up = t.text.upper()
                if any(kw in up for kw in ["VALIDITY", "VALID TILL", "VALID UPTO", "EXPIRY DATE"]) and "GOVERNMENT" not in up:
                    header_box = t
                    break

        if header_box:
            ly2 = header_box.bounding_box.max_y
            row_dates = []
            for t in texts:
                if t is header_box or t.bounding_box.min_x > 2500:
                    continue
                dt = normalize_date(t.text)
                if dt and dt != "0000-00-00" and dt != dob_val:
                    iy1 = t.bounding_box.min_y
                    if 0 <= iy1 - ly2 <= 200:
                        row_dates.append((t.bounding_box.min_x, dt))
            row_dates.sort(key=lambda d: d[0])
            if len(row_dates) >= 2:
                issue_date = row_dates[0][1]
                expiry_date = row_dates[1][1]
            elif len(row_dates) == 1:
                expiry_date = row_dates[0][1]

        return issue_date, expiry_date

    # ── Issue Date Fallback ───────────────────────────────────────────────────

    def extract_issue_date(self, texts: List[OCRText]) -> Optional[str]:
        date_pat = r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}|\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})"

        for item in texts:
            up = item.text.upper()
            if any(kw in up for kw in ["DOI", "ISSUE DATE", "DATE OF ISSUE"]) and "GOVERNMENT" not in up and "FIRST" not in up:
                m = re.search(date_pat, item.text)
                if m:
                    parsed = normalize_date(m.group(1))
                    if parsed:
                        return parsed

        label_keywords = ["Issue Date", "Date of Issue", "DOI", "Date of 1st Issue"]
        raw = self.find_value_near_label(texts, label_keywords, direction="auto", max_distance=500.0, same_row_tolerance=40.0)
        if raw:
            parsed = normalize_date(raw)
            if parsed:
                return parsed

        return None

    # ── Expiry / Validity Date Fallback ───────────────────────────────────────

    def extract_expiry_date(self, texts: List[OCRText]) -> Optional[str]:
        date_pat = r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}|\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})"

        # 1. Inline pattern check: OCR text box contains both validity/expiry label and a date
        for item in texts:
            up = item.text.upper()
            if "GOVERNMENT" in up or "AUTHORITY" in up:
                continue
            if any(kw in up for kw in _EXPIRY_KEYWORDS):
                m = re.search(date_pat, item.text)
                if m:
                    parsed = normalize_date(m.group(1))
                    if parsed and parsed != "0000-00-00":
                        return parsed

        # 2. Label proximity search with comprehensive validity & expiry keywords
        raw = self.find_value_near_label(texts, _EXPIRY_KEYWORDS, direction="auto", max_distance=500.0, same_row_tolerance=40.0)
        if raw:
            parsed = normalize_date(raw)
            if parsed and parsed != "0000-00-00":
                return parsed

        # 3. Spatial scan near label box matching any expiry/validity keyword
        exp_label = self._find_label_box(texts, _EXPIRY_KEYWORDS)
        if exp_label:
            l_y2 = exp_label.bounding_box.max_y
            l_cy = exp_label.bounding_box.center_y
            cands = []
            for item in texts:
                if item is exp_label or item.bounding_box.min_x > 2500:
                    continue
                parsed = normalize_date(item.text)
                if parsed and parsed != "0000-00-00":
                    dy = abs(item.bounding_box.center_y - l_cy)
                    dx = max(0.0, item.bounding_box.min_x - exp_label.bounding_box.max_x)
                    if dy <= 45.0 or (item.bounding_box.min_y >= l_y2 - 5 and item.bounding_box.min_y - l_y2 <= 150):
                        cands.append((dy + dx * 0.1, parsed))
            if cands:
                cands.sort(key=lambda c: c[0])
                return cands[0][1]

        return None

    # ── Vehicle Classes ───────────────────────────────────────────────────────

    def extract_vehicle_classes(self, texts: List[OCRText], side: str = "unknown") -> List[str]:
        found: Set[str] = set()

        # 1. Regex pattern search over all text items (handles compound strings like "LMV-NT", "3W-CAB", "COV: MCWG LMV")
        for item in texts:
            raw_up = item.text.upper().strip()
            if "GOVERNMENT" in raw_up or "AUTHORITY" in raw_up:
                continue

            for pattern, vc_code in _VC_PATTERNS:
                if pattern.search(raw_up):
                    found.add(vc_code)

            # Direct token match against known classes (ignoring COV)
            tokens = re.split(r"[\s,;/\\\-\.]+", raw_up)
            for token in tokens:
                token_clean = token.strip()
                if token_clean in _VEHICLE_CLASSES and token_clean != "COV":
                    found.add(self._canonical_vc(token_clean))

        # 2. Table and upper-left region check (especially for old DL back side under licence number)
        is_back = (side == "back")
        for item in texts:
            raw_up = item.text.upper().strip()
            # If item is in upper-left quadrant on back side (or anywhere in table rows)
            in_upper_left = is_back and item.bounding_box.min_x < 1600 and item.bounding_box.min_y < 1600
            if in_upper_left:
                for pattern, vc_code in _VC_PATTERNS:
                    if pattern.search(raw_up):
                        found.add(vc_code)

        return self._sort_vehicle_classes(list(found))

    @staticmethod
    def _canonical_vc(code: str) -> str:
        mapping = {
            "LMVNT": "LMV-NT",
            "LMVTR": "LMV-TR",
            "LMVCAB": "LMV-CAB",
            "3WNT": "3W-NT",
            "3WTR": "3W-TR",
            "3WCAB": "3W-CAB",
            "TRANSPORT": "TRANS",
            "PSVBUS": "PSV-BUS",
        }
        return mapping.get(code, code)

    @staticmethod
    def _sort_vehicle_classes(classes: List[str]) -> List[str]:
        order = ["MCWG", "MCWOG", "LMV", "LMV-NT", "LMV-TR", "LMV-CAB", "HMV", "HPMV", "HTV", "TRANS", "3W-NT", "3W-TR", "3W-CAB"]
        return sorted(
            list(set(classes)),
            key=lambda c: order.index(c) if c in order else 99
        )

    def _combine_vehicle_classes(self, vc_front: Optional[List[str]], vc_back: Optional[List[str]]) -> List[str]:
        combined = set(vc_front or []) | set(vc_back or [])
        return self._sort_vehicle_classes(list(combined))

    # ── Plausibility Helper ───────────────────────────────────────────────────

    def _is_plausible_name(self, text: str) -> bool:
        if not text:
            return False
        clean = text.upper().strip()
        if clean in _NAME_BLACKLIST or any(w in clean for w in ["LICENCE", "UNION", "INDIAN", "UTTAR", "PRADESH", "GUJARAT", "GOVERNMENT", "SIGNATURE", "HOLDER"]):
            return False
        words = clean.split()
        if len(words) < 1 or len(words) > 5:
            return False
        for w in words:
            if not w.replace(".", "").replace("'", "").replace("-", "").isalpha():
                return False
        return True
