"""
Aadhaar Card Domain Extractor
"""

import re
from typing import List, Optional

from microservices.shared.models import OCRResult, OCRText, AadhaarData
from microservices.shared.utils import normalize_dob, normalize_aadhaar_number, normalize_name
from microservices.aadhaar_service.config import aadhaar_config


class AadhaarExtractor:
    """Extracts structured fields from Aadhaar OCR outputs."""

    def extract_aadhaar(self, ocr_front: Optional[OCRResult], ocr_back: Optional[OCRResult]) -> AadhaarData:
        data_front = self.extract(ocr_front) if ocr_front else None
        data_back = self.extract(ocr_back) if ocr_back else None

        if data_front is None and data_back is None:
            return AadhaarData()
        if data_front is None:
            return data_back
        if data_back is None:
            return data_front

        merged = AadhaarData()
        merged.aadhaar_number = data_front.aadhaar_number or data_back.aadhaar_number
        merged.full_name = data_front.full_name or data_back.full_name
        merged.date_of_birth = data_front.date_of_birth or data_back.date_of_birth
        merged.gender = data_front.gender or data_back.gender
        merged.address = data_back.address or data_front.address

        for key, reason in data_front.field_diagnostics.items():
            if getattr(merged, key, None) is None:
                merged.field_diagnostics[key] = reason
        for key, reason in data_back.field_diagnostics.items():
            if getattr(merged, key, None) is None and key not in merged.field_diagnostics:
                merged.field_diagnostics[key] = reason

        return merged

    def extract(self, ocr_result: OCRResult) -> AadhaarData:
        texts = ocr_result.texts
        data = AadhaarData()

        data.aadhaar_number = self.extract_aadhaar_number(texts)
        data.date_of_birth = self.extract_dob(texts)
        data.gender = self.extract_gender(texts)
        data.address = self.extract_address(texts)

        name_raw = self.extract_name_raw(texts)
        if name_raw:
            parsed = normalize_name(name_raw)
            data.full_name = parsed["full_name"]

        self._generate_diagnostics(data, texts)
        return data

    def _generate_diagnostics(self, data: AadhaarData, texts: List[OCRText]) -> None:
        if not texts:
            for field in ["aadhaar_number", "full_name", "date_of_birth", "gender"]:
                data.field_diagnostics[field] = "OCR returned no text from image"
            return

        avg_conf = sum(t.confidence for t in texts) / len(texts) if texts else 0
        low_quality_msg = f"Low OCR confidence ({avg_conf:.0%})" if avg_conf < 0.5 else ""

        if not data.aadhaar_number:
            all_digits = "".join(re.findall(r"\d+", " ".join(t.text for t in texts)))
            data.field_diagnostics["aadhaar_number"] = (
                low_quality_msg or "No 12-digit number found in OCR text"
                if len(all_digits) < 10
                else "Digit sequences found but none match 12-digit Aadhaar format"
            )

        if not data.full_name:
            data.field_diagnostics["full_name"] = low_quality_msg or "No valid name candidate found in OCR text"

        if not data.date_of_birth:
            data.field_diagnostics["date_of_birth"] = low_quality_msg or "No valid DOB date pattern found in OCR text"

        if not data.gender:
            data.field_diagnostics["gender"] = low_quality_msg or "No gender keyword (MALE/FEMALE) found in OCR text"

    def extract_aadhaar_number(self, texts: List[OCRText]) -> Optional[str]:
        pattern_444 = r"\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b"
        for item in texts:
            if "X" in item.text.upper():
                continue
            m = re.search(pattern_444, item.text)
            if m:
                res = normalize_aadhaar_number(m.group(1))
                if res:
                    return res

        for item in texts:
            digits_only = re.sub(r"\D", "", item.text)
            if len(digits_only) == 12:
                res = normalize_aadhaar_number(digits_only)
                if res:
                    return res
        return None

    def extract_dob(self, texts: List[OCRText]) -> Optional[str]:
        date_patterns = [
            r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})",
            r"(\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})",
            r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        ]
        dob_keywords = ["DOB", "D.O.B", "D0B", "DATE OF BIRTH", "BIRTH", "YOB", "YEAR OF BIRTH"]

        # 1. DOB + date in the same OCR box
        for item in texts:
            text_up = item.text.upper()
            if any(kw in text_up for kw in dob_keywords):
                for pattern in date_patterns:
                    match = re.search(pattern, item.text)
                    if match:
                        parsed = normalize_dob(match.group(1))
                        if parsed and self._is_plausible_dob_year(parsed):
                            return parsed

        # 2. Find DOB label boxes
        dob_labels = [item for item in texts if any(kw in item.text.upper() for kw in dob_keywords)]
        
        # 3. Find all valid date candidates
        date_candidates = []
        for item in texts:
            for pattern in date_patterns:
                match = re.search(pattern, item.text)
                if match:
                    parsed = normalize_dob(match.group(1))
                    if parsed and self._is_plausible_dob_year(parsed):
                        date_candidates.append((item, parsed))
                        break
        
        # 4. Select the date nearest to DOB label
        best_candidate = None
        best_distance = float("inf")
        for label in dob_labels:
            for date_box, parsed_date in date_candidates:
                if date_box is label:
                    continue
                dx = abs(date_box.bounding_box.center_x - label.bounding_box.center_x)
                dy = abs(date_box.bounding_box.center_y - label.bounding_box.center_y)
                distance = dx if dy <= 25 else (dy + dx * 0.5 if date_box.bounding_box.min_y >= label.bounding_box.max_y - 10 else float("inf"))
                if distance < best_distance:
                    best_distance = distance
                    best_candidate = parsed_date

        if best_candidate:
            return best_candidate

        if date_candidates:
            return date_candidates[0][1]
        return None

    @staticmethod
    def _is_plausible_dob_year(iso_date: str) -> bool:
        try:
            year = int(iso_date[:4])
            return aadhaar_config.MIN_DOB_YEAR <= year <= aadhaar_config.MAX_DOB_YEAR
        except Exception:
            return False

    def extract_gender(self, texts: List[OCRText]) -> Optional[str]:
        gender_map = {"FEMALE": "FEMALE", "MALE": "MALE", "TRANSGENDER": "TRANSGENDER"}
        for item in texts:
            text_upper = item.text.upper().strip()
            for keyword, value in gender_map.items():
                if keyword in text_upper:
                    return value
        return None

    def extract_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        dob_keywords = ["DOB", "DATE OF BIRTH", "BIRTH", "MALE", "FEMALE"]
        dob_anchor = None
        for item in texts:
            if any(kw in item.text.upper() for kw in dob_keywords):
                dob_anchor = item
                break

        if dob_anchor:
            above_candidates = []
            for item in texts:
                if item is dob_anchor:
                    continue
                y_gap = dob_anchor.bounding_box.min_y - item.bounding_box.max_y
                if -10 <= y_gap <= 250 and self._is_plausible_name(item.text):
                    above_candidates.append((y_gap, item))
            if above_candidates:
                above_candidates.sort(key=lambda c: c[0])
                return above_candidates[0][1].text

        for item in sorted(texts, key=lambda t: t.confidence, reverse=True):
            if self._is_plausible_name(item.text) and item.confidence >= 0.70:
                return item.text
        return None

    def _is_plausible_name(self, text: str) -> bool:
        text = text.strip()
        if not text or any(c.isdigit() for c in text):
            return False
        words = text.split()
        for w in words:
            cleaned = w.replace(".", "").replace("'", "")
            if not cleaned.isalpha():
                return False
        lower_text = text.lower()
        if any(bl in lower_text for bl in aadhaar_config.NAME_BLACKLIST):
            return False
        return True

    def extract_address(self, texts: List[OCRText]) -> Optional[str]:
        label_keywords = ["address", "s/o", "c/o", "w/o", "पता", "સરનામું"]
        label_box = None
        for item in texts:
            if any(kw in item.text.lower() for kw in label_keywords):
                label_box = item
                break
        if label_box is None:
            return None

        label_y = label_box.bounding_box.max_y
        address_parts = []
        for item in sorted(texts, key=lambda t: t.bounding_box.min_y):
            if item.bounding_box.min_y < label_y - 5:
                continue
            if len(address_parts) > 5:
                break
            text_low = item.text.lower().strip()
            if any(kw in text_low for kw in ["aadhaar", "uidai", "gender", "dob"]):
                break
            address_parts.append(item.text.strip())

        return ", ".join(address_parts) if address_parts else None
