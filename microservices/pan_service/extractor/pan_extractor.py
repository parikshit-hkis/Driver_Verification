"""
PAN Card Domain Extractor
"""

import re
from typing import List, Optional

from microservices.shared.models import OCRResult, OCRText, PanData
from microservices.shared.utils import (
    BaseExtractor,
    normalize_dob,
    normalize_pan_number,
    normalize_name,
)
from microservices.pan_service.config import pan_config

_PAN_REGEX = pan_config.PAN_REGEX


class PanExtractor(BaseExtractor):
    """Extracts structured data from PAN card OCR output."""

    def extract_pan(self, ocr_front: Optional[OCRResult], ocr_back: Optional[OCRResult]) -> PanData:
        data_front = self.extract(ocr_front) if ocr_front else None
        data_back = self.extract(ocr_back) if ocr_back else None

        if data_front is None and data_back is None:
            return PanData()
        if data_front is None:
            return data_back
        if data_back is None:
            return data_front

        merged = PanData()
        merged.pan_number = data_front.pan_number or data_back.pan_number
        merged.full_name = data_front.full_name or data_back.full_name
        merged.father_name = data_front.father_name or data_back.father_name
        merged.date_of_birth = data_front.date_of_birth or data_back.date_of_birth

        for key, reason in data_front.field_diagnostics.items():
            if getattr(merged, key, None) is None:
                merged.field_diagnostics[key] = reason
        for key, reason in data_back.field_diagnostics.items():
            if getattr(merged, key, None) is None and key not in merged.field_diagnostics:
                merged.field_diagnostics[key] = reason

        return merged

    def extract(self, ocr_result: OCRResult) -> PanData:
        texts = ocr_result.texts
        data = PanData()

        data.pan_number = self.extract_pan_number(texts)
        data.date_of_birth = self.extract_dob(texts)

        name_raw = self.extract_name_raw(texts)
        if name_raw:
            parsed = normalize_name(name_raw)
            data.full_name = parsed["full_name"]

        father_raw = self.extract_father_name_raw(texts, person_name=data.full_name)
        if father_raw:
            parsed = normalize_name(father_raw)
            data.father_name = parsed["full_name"]

        self._generate_diagnostics(data, texts)
        return data

    def _generate_diagnostics(self, data: PanData, texts: List[OCRText]) -> None:
        if not texts:
            for field in ["pan_number", "full_name", "father_name", "date_of_birth"]:
                data.field_diagnostics[field] = "OCR returned no text from image"
            return

        avg_conf = sum(t.confidence for t in texts) / len(texts)
        low_quality_msg = f"Low OCR confidence ({avg_conf:.0%})" if avg_conf < 0.5 else ""

        if not data.pan_number:
            data.field_diagnostics["pan_number"] = low_quality_msg or "No valid 10-digit PAN pattern found in OCR text"
        if not data.full_name:
            data.field_diagnostics["full_name"] = low_quality_msg or "No valid cardholder name found"
        if not data.father_name:
            data.field_diagnostics["father_name"] = low_quality_msg or "No valid father's name found"
        if not data.date_of_birth:
            data.field_diagnostics["date_of_birth"] = low_quality_msg or "No date of birth pattern found"

    def extract_pan_number(self, texts: List[OCRText]) -> Optional[str]:
        for item in texts:
            cleaned = re.sub(r"\s+", "", item.text.upper())
            m = _PAN_REGEX.search(cleaned)
            if m:
                return normalize_pan_number(m.group(1))

        full = " ".join(t.text.upper() for t in texts)
        full_clean = re.sub(r"\s+", "", full)
        m = _PAN_REGEX.search(full_clean)
        if m:
            return normalize_pan_number(m.group(1))
        return None

    def extract_dob(self, texts: List[OCRText]) -> Optional[str]:
        label_keywords = [
            "Date of Birth", "DOB", "Birth Date",
            "Date Of Birth", "D.O.B", "जन्म तिथि", "BIRTH",
        ]

        dob_box = self._find_label_box(texts, label_keywords)
        if dob_box:
            l_y1 = dob_box.bounding_box.min_y
            above_cands = [
                t for t in texts
                if t is not dob_box
                and t.bounding_box.max_y <= l_y1 + 5
                and t.bounding_box.min_y >= l_y1 - 65
            ]
            for t in above_cands:
                dt = normalize_dob(t.text)
                if dt:
                    return dt

        raw = self.find_value_near_label(texts, label_keywords, max_distance=500.0)
        if raw:
            parsed = normalize_dob(raw)
            if parsed:
                return parsed

        date_patterns = [
            r"\b(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})\b",
            r"\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})\b",
            r"\b(\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})\b",
            r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b",
        ]
        for item in texts:
            text_up = item.text.upper()
            if "DOB" in text_up or "BIRTH" in text_up or "DATE" in text_up:
                for dp in date_patterns:
                    m = re.search(dp, item.text)
                    if m:
                        parsed = normalize_dob(m.group(1))
                        if parsed:
                            return parsed

        for item in texts:
            for dp in date_patterns:
                m = re.search(dp, item.text)
                if m:
                    parsed = normalize_dob(m.group(1))
                    if parsed:
                        return parsed
        return None

    def _centroid_y(self, t: OCRText) -> float:
        return (t.bounding_box.min_y + t.bounding_box.max_y) / 2.0

    def _x_overlap(self, box_a: OCRText, box_b: OCRText, min_ratio: float = 0.3) -> bool:
        a_min, a_max = box_a.bounding_box.min_x, box_a.bounding_box.max_x
        b_min, b_max = box_b.bounding_box.min_x, box_b.bounding_box.max_x
        overlap = min(a_max, b_max) - max(a_min, b_min)
        if overlap <= 0:
            return False
        narrower = min(a_max - a_min, b_max - b_min)
        return narrower > 0 and (overlap / narrower) >= min_ratio

    def extract_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        income_tax_box = self._find_label_box(texts, ["INCOME TAX", "INCOMETAX"])
        if income_tax_box:
            ref_y = income_tax_box.bounding_box.max_y
            below_candidates = sorted(
                [t for t in texts if t is not income_tax_box and self._centroid_y(t) > ref_y and self._x_overlap(income_tax_box, t)],
                key=lambda t: t.bounding_box.min_y,
            )
            for t in below_candidates:
                txt = t.text.strip()
                if re.search(r"govt|india|government|income\s*tax", txt, re.IGNORECASE):
                    continue
                if self._is_plausible_name(txt):
                    return txt

        label_keywords = ["Name", "NAME"]
        name_box = self._find_label_box(texts, label_keywords)

        if name_box:
            l_y1 = name_box.bounding_box.min_y
            above_cands = [
                t for t in texts
                if t is not name_box
                and t.bounding_box.max_y <= l_y1 + 5
                and t.bounding_box.min_y >= l_y1 - 65
            ]
            for t in above_cands:
                if self._is_plausible_name(t.text):
                    return t.text

        candidate = self.find_value_near_label(texts, label_keywords, direction="below", max_distance=200.0)
        if candidate and self._is_plausible_name(candidate):
            return candidate

        candidate = self.find_value_near_label(texts, label_keywords, direction="auto", max_distance=400.0)
        if candidate and self._is_plausible_name(candidate):
            return candidate

        for item in sorted(texts, key=lambda x: x.confidence, reverse=True):
            if self._is_plausible_name(item.text) and item.confidence >= 0.75:
                return item.text
        return None

    def extract_father_name_raw(self, texts: List[OCRText], person_name: Optional[str] = None) -> Optional[str]:
        label_keywords = [
            "Father's Name", "Father Name", "FATHER'S NAME", "Parent's Name",
            "Father", "FATHER",
        ]
        father_box = self._find_label_box(texts, label_keywords)

        def is_valid_father(t_text: str) -> bool:
            if not self._is_plausible_name(t_text):
                return False
            if person_name and person_name.strip().lower() == t_text.strip().lower():
                return False
            return True

        if not father_box:
            income_tax_box = self._find_label_box(texts, ["INCOME TAX", "INCOMETAX"])
            if income_tax_box:
                ref_y = self._centroid_y(income_tax_box)
                below_candidates = sorted(
                    [t for t in texts if t is not income_tax_box and self._centroid_y(t) > ref_y and self._x_overlap(income_tax_box, t)],
                    key=lambda t: self._centroid_y(t),
                )
                seen_person_name = False
                for t in below_candidates:
                    txt = t.text.strip()
                    if re.search(r"govt|india|government|income\s*tax", txt, re.IGNORECASE):
                        continue
                    if not self._is_plausible_name(txt):
                        continue
                    if person_name and txt.strip().lower() == person_name.strip().lower():
                        seen_person_name = True
                        continue
                    if seen_person_name or not person_name:
                        return txt

        if father_box:
            l_y1 = father_box.bounding_box.min_y
            above_cands = [
                t for t in texts
                if t is not father_box
                and t.bounding_box.max_y <= l_y1 + 5
                and t.bounding_box.min_y >= l_y1 - 65
            ]
            for t in above_cands:
                if is_valid_father(t.text):
                    return t.text

        candidate = self.find_value_near_label(texts, label_keywords, direction="below", max_distance=200.0)
        if candidate and is_valid_father(candidate):
            return candidate

        candidate = self.find_value_near_label(texts, label_keywords, direction="auto", max_distance=400.0)
        if candidate and is_valid_father(candidate):
            return candidate

        for item in sorted(texts, key=lambda x: x.confidence, reverse=True):
            if is_valid_father(item.text) and item.confidence >= 0.70:
                return item.text
        return None

    def _is_plausible_name(self, text: str) -> bool:
        text = text.strip()
        if not text or any(c.isdigit() for c in text):
            return False

        words = text.split()
        if len(words) < 1 or len(words) > 5:
            return False

        for w in words:
            cleaned = w.replace(".", "").replace("'", "")
            if not cleaned.isalpha():
                return False

        text_words = set(text.lower().split())
        for bl in pan_config.NAME_BLACKLIST:
            if bl in text_words:
                return False
        return True
