import re
import logging
from typing import List, Optional

from microservices.shared.models import OCRResult, OCRText, AadhaarData
from microservices.shared.utils import normalize_dob, normalize_aadhaar_number, normalize_name
from microservices.aadhaar_service.config import aadhaar_config

logger = logging.getLogger(__name__)


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
        
        dob = self.extract_dob(texts)
        if dob:
            data.date_of_birth = dob
            logger.debug(f"Full DOB found: {data.date_of_birth}")
        else:
            yob = self.extract_yob(texts)
            if yob:
                data.date_of_birth = yob
                logger.debug(f"Only Year of Birth (YOB) found, set date_of_birth: {data.date_of_birth}")
            else:
                logger.debug("Neither full DOB nor YOB found in Aadhaar document")

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
            data.field_diagnostics["date_of_birth"] = low_quality_msg or "No valid DOB date pattern or YOB found in OCR text"

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
            r"([0-9SOIlZB]{1,2}[/\-\.][0-9SOIlZB]{1,2}[/\-\.][0-9SOIlZB]{2,4})",
        ]
        dob_keywords = ["DOB","DB", "D.O.B", "D0B", "DATE OF BIRTH", "BIRTH", "YOB", "YEAR OF BIRTH"]

        # 1. DOB + date in the same OCR box
        for item in texts:
            text_up = item.text.upper()
            if any(kw in text_up for kw in dob_keywords):
                # Try direct full box normalization first
                parsed_direct = normalize_dob(item.text)
                if parsed_direct and self._is_plausible_dob_year(parsed_direct):
                    return parsed_direct

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
            parsed_direct = normalize_dob(item.text)
            if parsed_direct and self._is_plausible_dob_year(parsed_direct):
                date_candidates.append((item, parsed_direct))
                continue

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

    def extract_yob(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extracts 4-digit Year of Birth (YOB) when only year is present on Aadhaar card.
        Supports: 'Year of Birth1992', 'Year of Birth: 1992', 'YOB 1992', 'Y.O.B: 1992', 'YEAROFBIRTH:1992', etc.
        """
        yob_regex = re.compile(
            r"(?:year\s*of\s*birth|yearofbirth|y\.?o\.?b\.?)\s*[:\-\s/]*([12]\d{3})\b",
            re.IGNORECASE,
        )

        # 1. Search within the same OCR text box
        for item in texts:
            m = yob_regex.search(item.text)
            if m:
                yr = m.group(1)
                if self._is_plausible_yob(yr):
                    return yr

        # 2. Search for 4-digit year near YOB label boxes
        yob_keywords = ["YEAR OF BIRTH", "YEAROFBIRTH", "YOB", "Y.O.B", "YEAR OF BIRT", "Y.O.B."]
        yob_labels = [item for item in texts if any(kw in item.text.upper() for kw in yob_keywords)]
        if yob_labels:
            candidates = []
            for item in texts:
                for m in re.finditer(r"\b([12]\d{3})\b", item.text):
                    yr = m.group(1)
                    if self._is_plausible_yob(yr):
                        candidates.append((item, yr))

            best_yr = None
            best_dist = float("inf")
            for label in yob_labels:
                for yr_box, yr_val in candidates:
                    if yr_box is label:
                        continue
                    dx = abs(yr_box.bounding_box.center_x - label.bounding_box.center_x)
                    dy = abs(yr_box.bounding_box.center_y - label.bounding_box.center_y)
                    if dy <= 35 and dx <= 350:
                        dist = dx + dy
                        if dist < best_dist:
                            best_dist = dist
                            best_yr = yr_val

            if best_yr:
                return best_yr

        return None

    @staticmethod
    def _is_plausible_yob(year_str: str) -> bool:
        try:
            year = int(year_str)
            return aadhaar_config.MIN_DOB_YEAR <= year <= aadhaar_config.MAX_DOB_YEAR
        except Exception:
            return False

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
        dob_keywords = [
            "DOB", "DATE OF BIRTH", "BIRTH", "MALE", "FEMALE",
            "YEAR OF BIRTH", "YOB", "YEAROFBIRTH", "Y.O.B",
        ]
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
