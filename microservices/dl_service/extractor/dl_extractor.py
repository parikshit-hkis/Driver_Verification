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
from microservices.shared.utils.normalizer import _DATE_PATTERNS, parse_all_dates
from microservices.dl_service.config import dl_config

_DL_REGEX = dl_config.DL_REGEX
_VEHICLE_CLASSES = dl_config.VEHICLE_CLASSES
_ISSUE_KEYWORDS = dl_config.ISSUE_KEYWORDS
_EXPIRY_KEYWORDS = dl_config.EXPIRY_KEYWORDS
_DOB_KEYWORDS = dl_config.DOB_KEYWORDS
_NAME_KEYWORDS = dl_config.NAME_KEYWORDS
_RELATION_KEYWORDS = dl_config.RELATION_KEYWORDS
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

    def _collect_date_candidates(self, texts: List[OCRText]) -> List[Tuple[str, OCRText]]:
        candidates = []
        for item in texts:
            if item.bounding_box.min_x > 2550:
                continue
            dates = parse_all_dates(item.text)
            for d in dates:
                candidates.append((d, item))
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

    def _resolve_issue_and_expiry_dates(self, texts: List[OCRText], data: DrivingLicenceData) -> None:
        candidates = self._collect_date_candidates(texts)
        excluded_dates = {data.date_of_birth} if data.date_of_birth else set()
        available = [c for c in candidates if c[0] not in excluded_dates]
        current_date = datetime.now().strftime("%Y-%m-%d")

        issue_labels = self._find_labels(texts, _ISSUE_KEYWORDS)
        expiry_labels = self._find_labels(texts, _EXPIRY_KEYWORDS)

        resolved_issue = None
        resolved_expiry = None

        # Resolve issue date near issue label
        if issue_labels and available:
            best_dist, best_d = float("inf"), None
            for lbl in issue_labels:
                for d, box in available:
                    if d <= current_date:
                        dist = self._distance(lbl.bounding_box, box.bounding_box)
                        if dist < best_dist:
                            best_dist, best_d = dist, d
            if best_dist < 600.0:
                resolved_issue = best_d

        # Resolve expiry date near expiry label
        expiry_pool = [c for c in available if c[0] != resolved_issue]
        if resolved_issue:
            valid_expiry_cands = [c for c in expiry_pool if c[0] > resolved_issue]
        else:
            valid_expiry_cands = expiry_pool

        if expiry_labels and valid_expiry_cands:
            best_dist, best_d = float("inf"), None
            for lbl in expiry_labels:
                for d, box in valid_expiry_cands:
                    dist = self._distance(lbl.bounding_box, box.bounding_box)
                    if dist < best_dist:
                        best_dist, best_d = dist, d
            if best_dist < 600.0:
                resolved_expiry = best_d

        # Fallback for expiry date if not found: look for future dates
        if not resolved_expiry and valid_expiry_cands:
            future_cands = [c[0] for c in valid_expiry_cands if c[0] >= current_date]
            if future_cands:
                future_cands.sort(reverse=True)
                resolved_expiry = future_cands[0]

        # Fallback for issue date if not found: look for past dates
        if not resolved_issue and expiry_pool:
            past_cands = [c[0] for c in expiry_pool if c[0] <= current_date and c[0] != resolved_expiry]
            if past_cands:
                past_cands.sort()
                resolved_issue = past_cands[0]

        if resolved_issue and data.date_of_birth and resolved_issue < data.date_of_birth:
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
            "Driving Licence No", "DLNO", "DL NO", "DLNo", "LN0",
        ]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=600.0, same_row_tolerance=40.0)
        if raw:
            norm = normalize_dl_number(raw)
            if norm:
                return norm

        for item in texts:
            norm = normalize_dl_number(item.text)
            if norm:
                return norm

        full = " ".join(t.text for t in texts)
        norm = normalize_dl_number(full)
        if norm:
            return norm

        return None

    def extract_dob(self, texts: List[OCRText]) -> Optional[str]:
        current_year = datetime.now().year

        # 1. Inline regex search
        dob_inline_pattern = re.compile(
            r"(?:date\s*(?:of|0f|ot|o|or|birth|d\.?o\.?b\.?|dateb)?|dateof|date0f|dateot|dateor|dote\s*(?:of|0f)?|doteof|birth\s*date|d\.?o\.?b\.?|dob|dateb|000)\s*(?:birth|birt|bitth|b)?\s*[:\-\s]*([0-9SOIlZB]{1,2}[-/\.][0-9SOIlZB]{1,2}[-/\.][0-9SOIlZB]{2,4}|\d{4}[/\-]\d{4})",
            re.IGNORECASE,
        )
        for t in texts:
            m = dob_inline_pattern.search(t.text)
            if m:
                dates = parse_all_dates(m.group(0))
                for d in dates:
                    yr = int(d.split("-")[0])
                    if yr <= current_year - dl_config.MIN_DRIVER_AGE:
                        return d

        # 2. DOB Labels search
        labels = self._find_labels(texts, _DOB_KEYWORDS)
        candidates = self._collect_date_candidates(texts)
        if labels and candidates:
            best_dist, best_d = float("inf"), None
            for lbl in labels:
                for d, box in candidates:
                    yr = int(d.split("-")[0])
                    if yr <= current_year - dl_config.MIN_DRIVER_AGE:
                        dist = self._distance(lbl.bounding_box, box.bounding_box)
                        if dist < best_dist:
                            best_dist, best_d = dist, d
            if best_dist < 600.0:
                return best_d

        return None

    def extract_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        # 1. Inline pattern
        inline_pattern = re.compile(
            r"^(?:4/)?\s*(?:name|namie|mame|applicant\s*name|holder\s*name)\b[\s:\-/]*([A-Za-z\.\s']{3,})",
            re.IGNORECASE,
        )
        for item in texts:
            m = inline_pattern.match(item.text.strip())
            if m:
                val = self._strip_name_prefix(m.group(1).strip())
                if self._is_plausible_name(val):
                    return val

        # 2. Name label box
        name_label = None
        for t in texts:
            clean = t.text.upper().strip().rstrip(":").strip()
            if re.match(r"^(?:4/)?\s*(?:NAME|NAMIE|MAME|APPLICANT\s*NAME|(?:DL\s*(?:NUMBER\s*)?)?HOLDER\s*NAME|NAM)$", clean):
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
                if abs(icy - l_cy) <= 50.0 and ix1 >= l_x2 - 30:
                    cleaned = self._strip_name_prefix(t.text)
                    if self._is_plausible_name(cleaned):
                        cands.append((max(0.0, ix1 - l_x2), cleaned))

            if not cands:
                below_cands = []
                for t in texts:
                    if t is name_label or t.bounding_box.min_x > 2500:
                        continue
                    if l_y2 - 10 <= t.bounding_box.min_y <= l_y2 + 140:
                        cleaned = self._strip_name_prefix(t.text)
                        if self._is_plausible_name(cleaned):
                            below_cands.append((t.bounding_box.min_y - l_y2, cleaned))
                if below_cands:
                    below_cands.sort(key=lambda c: c[0])
                    cands.append(below_cands[0])

            if cands:
                cands.sort(key=lambda c: c[0])
                return cands[0][1]

        # 3. Relationship label proximity (Above Son/Daughter/Wife of)
        rel_label = None
        for t in texts:
            up = t.text.upper().strip()
            if any(kw in up for kw in ["S/O", "D/O", "W/O", "S/W/D", "SON/DAUGHTER", "O/DAUGHTER", "AUGHTER", "WIFE OF", "S/DM", "SOW PURA"]):
                rel_label = t
                break

        if rel_label:
            rel_y = rel_label.bounding_box.min_y
            above_candidates = [
                t for t in texts
                if rel_y - 180 <= t.bounding_box.min_y < rel_y + 15
                and t is not rel_label
                and t.bounding_box.min_x <= 2500
            ]
            above_candidates.sort(key=lambda t: abs(rel_y - t.bounding_box.max_y))
            for t in above_candidates:
                cleaned = self._strip_name_prefix(t.text)
                if self._is_plausible_name(cleaned):
                    return cleaned

        # 4. Proximity between DL Number and DOB / Blood Group
        for t in texts:
            up = t.text.upper().strip()
            if "NAM" in up and len(up) >= 6:
                cleaned = self._strip_name_prefix(t.text)
                if self._is_plausible_name(cleaned):
                    return cleaned

        # 5. Position above Address (for cards without Name label, e.g. Gujarat DL format)
        address_label = None
        for t in texts:
            up = t.text.upper().strip()
            if "ADDRESS" in up or "ADORESS" in up or "PERMANENT" in up:
                address_label = t
                break
        if address_label:
            addr_y = address_label.bounding_box.min_y
            above_addr = [
                t for t in texts
                if addr_y - 200 <= t.bounding_box.min_y < addr_y - 10
                and t.bounding_box.min_x <= 2500
            ]
            above_addr.sort(key=lambda t: t.bounding_box.min_y)
            for t in above_addr:
                cleaned = self._strip_name_prefix(t.text)
                if self._is_plausible_name(cleaned):
                    return cleaned

        return None

    @staticmethod
    def _strip_name_prefix(text: str) -> str:
        return re.sub(r'^(?:4/)?\s*(?:name|namie|mame|applicant\s*name|holder\s*name|applicant|holder|namc|nam)[\s:\-/]*', '', text, flags=re.IGNORECASE).strip()

    def _is_plausible_name(self, text: str) -> bool:
        if not text:
            return False
        clean = text.upper().strip()
        if len(clean) < 3 or len(clean) > 45:
            return False

        boilerplate_phrases = [
            "BLOOD GROUP", "EMERGENCY CONTACT", "HOLDER SIGNATURE", "HOLDER'S SIGNATURE",
            "HOKER'S SIGNATURE", "HOLDER SIGHATURE", "'S SIGNATURE", "'S SIGHATURE",
            "SIGNATURE OF HOLDER", "DRIVING LICENCE", "DRIVING LICENSE",
            "UNION OF INDIA", "GOVERNMENT OF", "STATE TRANSPORT", "FORM 7", "RULE 16",
            "DATE OF BIRTH", "DATE OF ISSUE", "VALID TILL", "VALID UPTO", "ORGAN DONOR",
            "INDIAN UNION", "AUTHORISATION TO DRIVE", "FOLLOWING CLASS", "ISSUED BY",
            "PERMANENT ADDRESS", "MOBILE NUMBER", "LICENCING AUTHORITY", "LICENSING AUTHORITY",
            "PORT AND TRANSPORT", "CHOKSI", "PORTS AND TRANSPORT", "AHMEDABAD", "SURAT",
            "VADODARA", "MAHARASHTRA", "GUJARAT", "RAJASTHAN", "MADHYA PRADESH",
        ]
        for phrase in boilerplate_phrases:
            if phrase in clean:
                return False

        words = [w.strip(".,'-") for w in clean.split() if w.strip(".,'-")]
        if len(words) < 1 or len(words) > 5:
            return False

        for w in words:
            if w in _NAME_BLACKLIST:
                return False
            if not w.isalpha():
                return False

        if len(words) == 1 and len(words[0]) < 3:
            return False

        return True

    def extract_vehicle_classes(self, texts: List[OCRText], side: str = "unknown") -> List[str]:
        found = set()
        date_boxes = [t for t in texts if parse_all_dates(t.text)]
        has_legend = any("LEGEND FOR" in t.text.upper() or "LEGEND" in t.text.upper() for t in texts)

        for item in texts:
            text_up = item.text.upper().strip()

            for vc in _VEHICLE_CLASSES:
                if not re.search(rf"(?<![A-Z0-9]){re.escape(vc)}(?![A-Z0-9])", text_up):
                    continue

                norm_vc = self._normalize_vehicle_class(vc)

                # Pattern A: Inline date
                if parse_all_dates(item.text):
                    found.add(norm_vc)
                    continue

                class_cx = item.bounding_box.center_x
                class_cy = item.bounding_box.center_y
                class_x2 = item.bounding_box.max_x
                matched = False

                for date_box in date_boxes:
                    if date_box is item: continue
                    date_cx = date_box.bounding_box.center_x
                    date_cy = date_box.bounding_box.center_y
                    date_x1 = date_box.bounding_box.min_x

                    # Horizontal proximity
                    if abs(class_cy - date_cy) <= 50.0 and -50.0 <= (date_x1 - class_x2) <= 600.0:
                        found.add(norm_vc)
                        matched = True
                        break

                    # Vertical proximity
                    if 0.0 <= (date_cy - class_cy) <= 180.0 and abs(class_cx - date_cx) <= 180.0:
                        found.add(norm_vc)
                        matched = True
                        break

                if matched:
                    continue

                # Pattern D: Under header (if not legend)
                if not has_legend:
                    header_labels = [
                        t for t in texts
                        if any(h in t.text.upper() for h in ["COV", "CLASS OF", "VEHICLE CATEGORY", "VEHICLE CLASS", "CODE", "AUTHORISATION"])
                    ]
                    for header in header_labels:
                        h_cx = header.bounding_box.center_x
                        h_y2 = header.bounding_box.max_y
                        if abs(class_cx - h_cx) <= 120.0 and 0.0 <= (item.bounding_box.min_y - h_y2) <= 350.0:
                            found.add(norm_vc)
                            matched = True
                            break

                if matched:
                    continue

                # Pattern E: Standalone box matching vehicle class exactly (if not in a 20-row legend)
                if not has_legend:
                    cleaned_token = re.sub(r"[^A-Z0-9\-]", "", text_up)
                    if cleaned_token in _VEHICLE_CLASSES:
                        found.add(norm_vc)
                        continue

                # Pattern F: Box contains Authorization / COV / Class label alongside class
                if any(p in text_up for p in ["AUTHORIZATION", "AUTHORISATION", "AUTH", "COV", "CLASS", "CATEGORY"]):
                    found.add(norm_vc)
                    continue

        return self._sort_vehicle_classes(list(found))

    def _normalize_vehicle_class(self, value: str) -> str:
        return {
            "SCWG": "MCWG", "MOWG": "MCWG", "HCWG": "MCWG", "MCWO": "MCWOG", "HCWOG": "MCWOG",
            "LMY": "LMV", "LBY": "LMV", "LN": "LMV",
            "LMVCAB": "LMV-CAB", "3WNT": "3W-NT", "3WTR": "3W-TR", "3WCAB": "3W-CAB",
            "TRANSPORT": "TRANS", "TRN": "TRANS", "TRV": "TRANS", "PSVBUS": "PSV-BUS",
            "TRCTOR": "TRACTOR", "TRCT0H": "TRACTOR", "INVCRG": "INVCR",
        }.get(value, value)

    @staticmethod
    def _sort_vehicle_classes(classes: List[str]) -> List[str]:
        order = [
            "MCWG", "MCWOG", "LMV", "LMV-NT", "LMV-TR", "LMV-CAB", "HMV",
            "HPMV", "HTV", "TRANS", "3W-NT", "3W-TR", "3W-CAB", "TRACTOR", "AGRTLR"
        ]
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
