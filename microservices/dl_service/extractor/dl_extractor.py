"""
Driving Licence Domain Extractor
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Set, Tuple

from microservices.shared.models import OCRResult, OCRText, DrivingLicenceData
from microservices.shared.utils import (
    BaseExtractor,
    normalize_dob,
    normalize_date,
    normalize_dl_number,
    normalize_name,
)
from microservices.shared.utils.normalizer import _DATE_PATTERNS
from microservices.dl_service.config import dl_config

_DL_REGEX = dl_config.DL_REGEX
_VEHICLE_CLASSES = dl_config.VEHICLE_CLASSES
_ISSUE_KEYWORDS = dl_config.ISSUE_KEYWORDS
_EXPIRY_KEYWORDS = dl_config.EXPIRY_KEYWORDS
_DOB_KEYWORDS = dl_config.DOB_KEYWORDS
_NAME_BLACKLIST = dl_config.NAME_BLACKLIST


@dataclass
class DateCandidate:
    date: str
    text: str
    box: OCRText
    confidence: float
    context: Optional[str] = None


class DrivingLicenceExtractor(BaseExtractor):
    """Extracts structured data from Driving Licence OCR output."""

    def extract_dl(self, ocr_front: Optional[OCRResult], ocr_back: Optional[OCRResult]) -> DrivingLicenceData:
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
        merged.vehicle_classes = self._combine_vehicle_classes(data_front.vehicle_classes, data_back.vehicle_classes)

        for key, reason in data_front.field_diagnostics.items():
            if not getattr(merged, key, None):
                merged.field_diagnostics[key] = reason
        for key, reason in data_back.field_diagnostics.items():
            if not getattr(merged, key, None) and key not in merged.field_diagnostics:
                merged.field_diagnostics[key] = reason

        return merged

    def extract(self, ocr_result: OCRResult) -> DrivingLicenceData:
        return self._extract_side(ocr_result, side="unknown")

    def _extract_side(self, ocr_result: Optional[OCRResult], side: str = "unknown") -> DrivingLicenceData:
        if not ocr_result or not ocr_result.texts:
            return DrivingLicenceData()

        filtered_texts = [t for t in ocr_result.texts if t.bounding_box.min_x <= 2550]
        texts = filtered_texts if filtered_texts else ocr_result.texts
        data = DrivingLicenceData()

        data.licence_number = self.extract_licence_number(texts)
        data.date_of_birth = self.extract_dob(texts)

        name_raw = self.extract_name_raw(texts)
        if name_raw:
            parsed = normalize_name(name_raw)
            data.full_name = parsed["full_name"]

        self._resolve_issue_and_expiry_dates(texts, data)
        data.vehicle_classes = self.extract_vehicle_classes(texts, side=side)
        self._generate_diagnostics(data, texts)
        return data

    def _distance(self, box_a, box_b) -> float:
        ax = (box_a.min_x + box_a.max_x) / 2
        ay = (box_a.min_y + box_a.max_y) / 2
        bx = (box_b.min_x + box_b.max_x) / 2
        by = (box_b.min_y + box_b.max_y) / 2
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

    def _collect_date_candidates(self, texts: List[OCRText]) -> List[DateCandidate]:
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

    def _find_labels(self, texts: List[OCRText], keywords: List[str]) -> List[OCRText]:
        kw_upper = [k.upper() for k in keywords]
        labels = []
        for t in texts:
            up = t.text.upper().strip().rstrip(":").strip()
            if "GOVERNMENT" in up or "AUTHORITY" in up:
                continue
            if any(kw in up for kw in kw_upper):
                labels.append(t)
        return labels

    def _closest_candidate(self, labels: List[OCRText], candidates: List[DateCandidate]) -> Optional[DateCandidate]:
        best_cand, best_dist = None, float("inf")
        for label in labels:
            for cand in candidates:
                dist = self._distance(cand.box.bounding_box, label.bounding_box)
                if dist < best_dist:
                    best_dist, best_cand = dist, cand
        return best_cand

    def _resolve_issue_and_expiry_dates(self, texts: List[OCRText], data: DrivingLicenceData) -> None:
        candidates = self._collect_date_candidates(texts)
        excluded_dates = {data.date_of_birth} if data.date_of_birth else set()
        available = [c for c in candidates if c.date not in excluded_dates]

        issue_label = self._find_labels(texts, _ISSUE_KEYWORDS)
        issue_candidate = self._closest_candidate(issue_label, available)

        expiry_pool = [c for c in available if c is not issue_candidate]
        expiry_label = self._find_labels(texts, _EXPIRY_KEYWORDS)
        expiry_candidate = self._closest_candidate(expiry_label, expiry_pool)

        resolved_issue = issue_candidate.date if issue_candidate else None
        resolved_expiry = expiry_candidate.date if expiry_candidate else None
        current_date = datetime.now().strftime("%Y-%m-%d")

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

    def extract_dob(self, texts: List[OCRText]) -> Optional[str]:
        current_year = datetime.now().year
        candidates = self._collect_date_candidates(texts)
        labels = self._find_labels(texts, _DOB_KEYWORDS)
        dob_candidate = self._closest_candidate(labels, candidates)

        if dob_candidate:
            yr = int(dob_candidate.date.split("-")[0])
            if yr <= current_year - 16:
                return dob_candidate.date
        return None

    def extract_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        for item in texts:
            up = item.text.upper().strip()
            m = re.match(r"^(?:NAME|HOLDER|APPLICANT|MAME)[\s:\-/]*([A-Z\.\s']{3,})", up)
            if m:
                val = self._strip_name_prefix(m.group(1).strip())
                if self._is_plausible_name(val):
                    return val

        name_label = None
        for t in texts:
            clean = t.text.upper().strip().rstrip(":").strip()
            if clean in ["NAME", "MAME", "APPLICANT NAME", "HOLDER NAME", "DL NUMBER HOLDER NAME"]:
                name_label = t
                break

        if name_label:
            l_cy = name_label.bounding_box.center_y
            l_x2 = name_label.bounding_box.max_x
            l_y2 = name_label.bounding_box.max_y
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

            if not cands:
                below_cands = []
                for t in texts:
                    if t is name_label or t.bounding_box.min_x > 2500:
                        continue
                    if l_y2 - 5 <= t.bounding_box.min_y <= l_y2 + 120:
                        cleaned = self._strip_name_prefix(t.text)
                        if self._is_plausible_name(cleaned):
                            below_cands.append((t.bounding_box.min_y - l_y2, cleaned))
                if below_cands:
                    below_cands.sort(key=lambda c: c[0])
                    cands.append(below_cands[0])

            if cands:
                cands.sort(key=lambda c: c[0])
                return cands[0][1]

        rel_label = self._find_label_box(texts, ["S/O", "D/O", "W/O", "S/W/D", "Son/Daughter"])
        if rel_label:
            rel_y = rel_label.bounding_box.min_y
            above_candidates = [t for t in texts if rel_y - 150 < t.bounding_box.max_y < rel_y + 20]
            for t in above_candidates:
                cleaned = self._strip_name_prefix(t.text)
                if self._is_plausible_name(cleaned):
                    return cleaned

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
        return re.sub(r'^(?:name|holder|applicant|mame)[\s:\-/]*', '', text, flags=re.IGNORECASE).strip()

    def _is_plausible_name(self, text: str) -> bool:
        if not text:
            return False
        clean = text.upper().strip()
        if clean in _NAME_BLACKLIST:
            return False

        structural_terms = [
            "FIRST ISSUE", "DATE OF ISSUE", "DATE OF FIRST ISSUE", "ISSUE DATE",
            "VALIDITY", "VALID TILL", "VALID UPTO", "EXPIRY", "EXPIRY DATE",
            "DATE OF BIRTH", "REGISTERING", "AUTHORITY", "AHMEDABAD", "GUJARAT",
            "MAHARASHTRA", "RAJASTHAN", "STATE", "TRANSPORT", "GOVERNMENT",
            "SIGNATURE", "HOLDER", "LICENCE", "LICENSE", "UNION", "INDIAN", "RTO",
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

    def extract_vehicle_classes(self, texts: List[OCRText], side: str = "unknown") -> List[str]:
        found = set()
        date_boxes = [t for t in texts if normalize_date(t.text)]

        for item in texts:
            text = item.text.upper().strip()
            for vc in _VEHICLE_CLASSES:
                if not re.search(rf"(?<![A-Z0-9]){re.escape(vc)}(?![A-Z0-9])", text):
                    continue

                if normalize_date(item.text):
                    found.add(self._normalize_vehicle_class(vc))
                    continue

                class_cy = item.bounding_box.center_y
                class_x2 = item.bounding_box.max_x

                for date_box in date_boxes:
                    if date_box is item:
                        continue
                    date_cy = date_box.bounding_box.center_y
                    date_x1 = date_box.bounding_box.min_x
                    if abs(class_cy - date_cy) <= 45.0 and -50.0 <= (date_x1 - class_x2) <= 500.0:
                        found.add(self._normalize_vehicle_class(vc))
                        break

        vehicle_class_labels = [t for t in texts if "VEHICLE CLASS" in t.text.upper()]
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
                    if abs(class_cy - label_cy) <= 45.0 and class_x1 >= label_x2 - 20.0:
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
        order = ["MCWG", "MCWOG", "LMV", "LMV-NT", "LMV-TR", "LMV-CAB", "HMV", "HPMV", "HTV", "TRANS", "3W-NT", "3W-TR", "3W-CAB", "TRACTOR"]
        return sorted(list(set(classes)), key=lambda c: order.index(c) if c in order else 99)

    def _combine_vehicle_classes(self, vc_front: Optional[List[str]], vc_back: Optional[List[str]]) -> List[str]:
        combined = set(vc_front or []) | set(vc_back or [])
        return self._sort_vehicle_classes(list(combined))

    def _generate_diagnostics(self, data: DrivingLicenceData, texts: List[OCRText]) -> None:
        if not texts:
            for field in ["licence_number", "full_name", "date_of_birth", "issue_date", "expiry_date", "vehicle_classes"]:
                data.field_diagnostics[field] = "OCR returned no text from image"
            return

        if not data.licence_number:
            data.field_diagnostics["licence_number"] = "No DL number pattern found in OCR text"
        if not data.full_name:
            data.field_diagnostics["full_name"] = "No plausible name text found near 'Name' label"
        if not data.date_of_birth:
            data.field_diagnostics["date_of_birth"] = "No date found near DOB/Birth label"
        if not data.issue_date:
            data.field_diagnostics["issue_date"] = "No valid issue date detected"
        if not data.expiry_date:
            data.field_diagnostics["expiry_date"] = "No valid expiry/validity date detected"
