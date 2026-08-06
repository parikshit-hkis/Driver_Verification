"""
Aadhaar Card Extractor
======================
Extracts and normalizes:
  - Aadhaar number (12 digits, any format)
  - Full name + split (first/middle/last)
  - Date of birth
  - Gender
  - Address (when back side is provided)

Extraction Strategy (in priority order):
  1. Label-proximity  — most reliable; uses bounding-box positions
  2. Regex patterns   — fallback when label not detected cleanly

Aadhaar layouts handled:
  - Standard UIDAI English card (most common)
  - Bilingual English + Gujarati card (Gujarat)
  - Blue/white card design
  - e-Aadhaar PDF printout
  - mAadhaar app screenshot
"""

import re
from typing import List, Optional

from app.models.ocr_models import OCRResult, OCRText
from app.services.base_extractor import BaseExtractor
from app.services.aadhaar_extractor.models import AadhaarData
from app.utils.normalizer import normalize_dob, normalize_aadhaar_number, normalize_name


# Words that must NOT be the name (exact or contained)
_NAME_BLACKLIST = {
    "government", "india", "aadhaar", "uidai", "address", "authentication",
    "proof", "citizenship", "birth", "help", "xml", "qr", "male", "female",
    "transgender", "download", "date", "dob", "year", "permanent", "resident",
    "unique", "identification", "authority", "enrolment", "enrollment",
    "village", "post", "district", "state", "pin", "pincode", "s/o", "d/o",
    "w/o", "care", "of", "house", "near", "sector", "ward", "taluka",
    "tehsil", "nagar", "gujarat", "ahmedabad", "surat", "vadodara",
}


class AadhaarExtractor(BaseExtractor):
    """Extracts structured data from Aadhaar card OCR output."""

    def extract(self, ocr_result: OCRResult) -> AadhaarData:
        texts = ocr_result.texts
        data = AadhaarData()

        data.aadhaar_number = self.extract_aadhaar_number(texts)
        data.dob = self.extract_dob(texts)
        data.gender = self.extract_gender(texts)

        name_raw = self.extract_name_raw(texts)
        if name_raw:
            parsed = normalize_name(name_raw)
            data.full_name = parsed["full_name"]
            data.first_name = parsed["first_name"]
            data.middle_name = parsed["middle_name"]
            data.last_name = parsed["last_name"]

        data.address = self.extract_address(texts)

        return data

    # ── Aadhaar Number ────────────────────────────────────────────────────────

    def extract_aadhaar_number(self, texts: List[OCRText]) -> Optional[str]:
        """
        Find the 12-digit Aadhaar number.

        Handles all common formats:
          4341 3155 9547  (spaced)
          434131559547    (compact)
          4341-3155-9547  (hyphenated)
          XXXX XXXX 9547  (partially masked — skip these)
        """
        # Pattern 1: 4-4-4 with any separator (space, hyphen, nothing)
        pattern_444 = r"\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b"

        for item in texts:
            # Skip masked numbers (contain X)
            if "X" in item.text.upper() or "x" in item.text:
                continue

            m = re.search(pattern_444, item.text)
            if m:
                result = normalize_aadhaar_number(m.group(1))
                if result:
                    return result

        # Pattern 2: 12 consecutive digits anywhere in a text block
        for item in texts:
            digits_only = re.sub(r"\D", "", item.text)
            if len(digits_only) == 12:
                result = normalize_aadhaar_number(digits_only)
                if result:
                    return result

        return None

    # ── Date of Birth ─────────────────────────────────────────────────────────

    def extract_dob(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract DOB.

        Priority:
          1. Inline pattern — "DOB: DD/MM/YYYY" in a single text box (most common)
          2. Label-proximity — label and value in separate boxes
          3. Regex fallback — date near a DOB-like word
          4. Last resort — any date in plausible DOB year range (1930–2015)
        """
        date_patterns = [
            r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})",
            r"(\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})",
            r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        ]
        # Inline label keywords — includes OCR variants
        dob_inline_keywords = [
            "DOB", "D.O.B", "DATE OF BIRTH", "BIRTH", "जन्म", "YOB",
        ]

        # 1. Inline: same text box contains DOB keyword + date
        for item in texts:
            text_up = item.text.upper()
            if any(kw in text_up for kw in dob_inline_keywords):
                for pat in date_patterns:
                    m = re.search(pat, item.text)
                    if m:
                        parsed = normalize_dob(m.group(1))
                        if parsed and self._is_plausible_dob_year(parsed):
                            return parsed

        # 2. Label-proximity
        label_keywords = [
            "DOB", "Date of Birth", "D.O.B", "Year of Birth",
            "जन्म तिथि", "जन्म की तारीख", "YOB",
        ]
        raw = self.find_value_near_label(texts, label_keywords)
        if raw:
            parsed = normalize_dob(raw)
            if parsed and self._is_plausible_dob_year(parsed):
                return parsed

        # 3. Last resort — any date in plausible DOB year range
        for item in texts:
            for pat in date_patterns:
                m = re.search(pat, item.text)
                if m:
                    parsed = normalize_dob(m.group(1))
                    if parsed and self._is_plausible_dob_year(parsed):
                        return parsed

        return None

    @staticmethod
    def _is_plausible_dob_year(iso_date: str) -> bool:
        """Return True if the year is in a realistic DOB range."""
        try:
            year = int(iso_date[:4])
            return 1930 <= year <= 2026
        except (ValueError, IndexError):
            return False

    # ── Gender ────────────────────────────────────────────────────────────────

    def extract_gender(self, texts: List[OCRText]) -> Optional[str]:
        """
        Detect gender.
        Handles: MALE, FEMALE, TRANSGENDER, पुरुष, महिला (Hindi),
        and abbreviated forms.
        """
        gender_map = {
            "FEMALE": "FEMALE",
            "महिला": "FEMALE",     # Hindi
            "સ્ત્રી": "FEMALE",   # Gujarati
            "MALE": "MALE",
            "पुरुष": "MALE",      # Hindi
            "પુરુષ": "MALE",      # Gujarati
            "TRANSGENDER": "TRANSGENDER",
        }

        for item in texts:
            text_upper = item.text.upper().strip()
            for keyword, value in gender_map.items():
                if keyword in text_upper:
                    return value

        # Proximity to "Sex" or "Gender" label
        raw = self.find_value_near_label(texts, ["Gender", "Sex", "लिंग", "જાતિ"])
        if raw:
            raw_upper = raw.upper()
            for keyword, value in gender_map.items():
                if keyword in raw_upper:
                    return value

        return None

    # ── Name ─────────────────────────────────────────────────────────────────

    def extract_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract the person's name as a raw string.

        Priority:
          1. Text directly below / to the right of "Name:" label
          2. Heuristic: highest-confidence multi-word alphabetic text that
             passes the blacklist filter
        """
        # 1. Label-proximity
        label_keywords = [
            "Name", "NAME", "नाम", "નામ",
        ]
        candidate = self.find_value_near_label(
            texts, label_keywords, direction="auto", max_distance=500.0
        )
        if candidate and self._is_plausible_name(candidate):
            return candidate

        # 2. Heuristic: scan all texts
        # Sort by confidence descending
        sorted_texts = sorted(texts, key=lambda t: t.confidence, reverse=True)

        for item in sorted_texts:
            if self._is_plausible_name(item.text) and item.confidence >= 0.80:
                return item.text

        return None

    def _is_plausible_name(self, text: str) -> bool:
        """Return True if text could be an Indian person's name."""
        text = text.strip()
        if not text:
            return False

        # Must not contain digits
        if any(c.isdigit() for c in text):
            return False

        # Split into words
        words = text.split()

        # 2 to 5 words
        if len(words) < 2 or len(words) > 5:
            return False

        # Every word: letters only (allow dot/apostrophe inside)
        for w in words:
            cleaned = w.replace(".", "").replace("'", "")
            if not cleaned.isalpha():
                return False

        # Blacklist check
        lower_text = text.lower()
        for bl in _NAME_BLACKLIST:
            if bl in lower_text:
                return False

        return True

    # ── Address ───────────────────────────────────────────────────────────────

    def extract_address(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract address (usually on the back of the Aadhaar card).
        Looks for text near "Address" / "C/O" label, then collects
        the following lines until a non-address token appears.
        """
        label_keywords = ["Address", "S/O", "C/O", "W/O", "पता", "સરનામું"]

        label_box = self._find_label_box(texts, label_keywords)
        if label_box is None:
            return None

        label_y = label_box.bounding_box.max_y
        _SKIP_KEYWORDS = {
            "aadhaar", "uidai", "gender", "dob", "name", "sex",
            "details as on", "download", "qr", "xml", "authentication",
        }

        address_parts = []
        prev_y = label_y
        seen = set()  # for deduplication

        for item in sorted(texts, key=lambda t: t.bounding_box.min_y):
            iy = item.bounding_box.min_y
            if iy < label_y - 5:
                continue
            # Stop if gap between consecutive lines is too large
            if iy - prev_y > 55:
                break

            text_low = item.text.lower().strip()
            # Skip metadata/header lines
            if any(kw in text_low for kw in _SKIP_KEYWORDS):
                break

            # Deduplicate similar parts
            normalized = re.sub(r'\s+', ' ', text_low)
            if normalized not in seen:
                seen.add(normalized)
                address_parts.append(item.text.strip())

            prev_y = item.bounding_box.max_y

        if not address_parts:
            return None

        return ", ".join(p for p in address_parts if p)