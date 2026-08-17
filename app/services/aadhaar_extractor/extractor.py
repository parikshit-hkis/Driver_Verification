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
from app.services.aadhaar_extractor.config import aadhaar_config
from app.utils.normalizer import normalize_dob, normalize_aadhaar_number, normalize_name

# Words that must NOT be the name (exact or contained)
_NAME_BLACKLIST = aadhaar_config.NAME_BLACKLIST


class AadhaarExtractor(BaseExtractor):
    """Extracts structured data from Aadhaar card OCR output."""

    def extract_aadhaar(self, ocr_front: Optional[OCRResult], ocr_back: Optional[OCRResult]) -> AadhaarData:
        """Process front and back sides independently to avoid cross-side contamination."""
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

        # Merge diagnostics from both sides for remaining missing fields
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

        name_raw = self.extract_name_raw(texts)
        if name_raw:
            parsed = normalize_name(name_raw)
            data.full_name = parsed["full_name"]

        # ── Generate per-field diagnostics ────────────────────────────────
        self._generate_diagnostics(data, texts)

        return data

    # ── Diagnostics ──────────────────────────────────────────────────────

    def _generate_diagnostics(self, data: AadhaarData, texts: List[OCRText]) -> None:
        """For every missing field, explain why OCR failed to extract it."""
        if not texts:
            for field in ["aadhaar_number", "full_name", "date_of_birth", "gender"]:
                data.field_diagnostics[field] = "OCR returned no text from image"
            return

        # Check if OCR output is mostly garbage / very low confidence
        avg_conf = sum(t.confidence for t in texts) / len(texts) if texts else 0
        low_quality_msg = ""
        if avg_conf < 0.5:
            low_quality_msg = f"Low OCR confidence ({avg_conf:.0%}); image may be blurry or low quality"

        if not data.aadhaar_number:
            # Check if any digit sequences exist
            all_digits = "".join(re.findall(r"\d+", " ".join(t.text for t in texts)))
            if len(all_digits) < 10:
                data.field_diagnostics["aadhaar_number"] = low_quality_msg or "No 12-digit number found in OCR text; image may be unclear or cropped"
            else:
                data.field_diagnostics["aadhaar_number"] = "Digit sequences found but none match 12-digit Aadhaar format"

        if not data.full_name:
            alpha_texts = [t.text for t in texts if re.match(r'^[A-Za-z\s\.]+$', t.text.strip()) and len(t.text.strip()) >= 3]
            if not alpha_texts:
                data.field_diagnostics["full_name"] = low_quality_msg or "No alphabetic name-like text found in OCR output"
            else:
                data.field_diagnostics["full_name"] = "Name candidates found but rejected by plausibility filter (may match blacklisted words)"

        if not data.date_of_birth:
            # Check what date-like content exists
            date_like = re.findall(r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}", " ".join(t.text for t in texts))
            yob_like = re.findall(r"\b(19\d{2}|20[0-2]\d)\b", " ".join(t.text for t in texts))
            if not date_like and not yob_like:
                data.field_diagnostics["date_of_birth"] = low_quality_msg or "No date or year found in OCR text; DOB label may be in non-English script"
            elif date_like:
                data.field_diagnostics["date_of_birth"] = f"Date pattern(s) found ({', '.join(date_like[:3])}) but could not parse to valid DOB"
            else:
                data.field_diagnostics["date_of_birth"] = f"Year(s) found ({', '.join(yob_like[:3])}) but could not associate with DOB label"

        if not data.gender:
            gender_words = [t.text for t in texts if any(g in t.text.upper() for g in ["MALE", "FEMALE", "TRANSGENDER"])]
            if not gender_words:
                data.field_diagnostics["gender"] = low_quality_msg or "No gender keyword (MALE/FEMALE) found in OCR text"
            else:
                data.field_diagnostics["gender"] = f"Gender word found ({gender_words[0]}) but extraction failed"

    # ── Aadhaar Number ────────────────────────────────────────────────────────

    def extract_aadhaar_number(self, texts: List[OCRText]) -> Optional[str]:
        """Find the 12-digit Aadhaar number."""

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

        date_patterns = [
            r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})",
            r"(\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})",
            r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        ]

        dob_keywords = [
            "DOB",
            "D.O.B",
            "D0B",
            "DB",
            "DATE OF BIRTH",
            "BIRTH",
            "YOB",
            "YEAR OF BIRTH",
            "BIRT",
            "BRTH",
        ]

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
        dob_labels = []

        for item in texts:
            text_up = item.text.upper().strip()

            if any(kw in text_up for kw in dob_keywords):
                dob_labels.append(item)

        # 3. Find all valid date candidates
        date_candidates = []

        for item in texts:
            for pattern in date_patterns:
                match = re.search(pattern, item.text)

                if not match:
                    continue

                parsed = normalize_dob(match.group(1))

                if parsed and self._is_plausible_dob_year(parsed):
                    date_candidates.append((item, parsed))
                    break

        # 4. Select the date nearest to DOB label
        best_candidate = None
        best_distance = float("inf")

        for label in dob_labels:

            label_cx = label.bounding_box.center_x
            label_cy = label.bounding_box.center_y

            for date_box, parsed_date in date_candidates:

                if date_box is label:
                    continue

                date_cx = date_box.bounding_box.center_x
                date_cy = date_box.bounding_box.center_y

                dx = abs(date_cx - label_cx)
                dy = abs(date_cy - label_cy)

                # Same row
                if dy <= 25:
                    distance = dx

                # Directly below
                elif date_box.bounding_box.min_y >= label.bounding_box.max_y - 10:
                    distance = dy + dx * 0.5

                else:
                    continue

                if distance < best_distance:
                    best_distance = distance
                    best_candidate = parsed_date

        if best_candidate:
            return best_candidate

        # 5. YOB fallback
        for label in dob_labels:

            label_cy = label.bounding_box.center_y
            label_x2 = label.bounding_box.max_x

            for item in texts:

                if item is label:
                    continue

                match = re.search(r"\b(19\d{2}|20[0-2]\d)\b", item.text)

                if not match:
                    continue

                year = int(match.group(1))

                if not aadhaar_config.MIN_DOB_YEAR <= year <= 2015:
                    continue

                dy = abs(item.bounding_box.center_y - label_cy)
                dx = item.bounding_box.min_x - label_x2

                if dy <= 50 and -20 <= dx <= 500:
                    return f"{year}-01-01"

                if (
                    item.bounding_box.min_y >= label.bounding_box.max_y - 10
                    and item.bounding_box.min_y - label.bounding_box.max_y <= 120
                ):
                    return f"{year}-01-01"

        # 6. Last resort
        for item, parsed in date_candidates:
            return parsed

        return None

    @staticmethod
    def _is_plausible_dob_year(iso_date: str) -> bool:
        """Return True if the year is in a realistic DOB range."""
        try:
            year = int(iso_date[:4])
            return aadhaar_config.MIN_DOB_YEAR <= year <= aadhaar_config.MAX_DOB_YEAR
        except (ValueError, IndexError):
            return False

    # ── Gender ────────────────────────────────────────────────────────────

    def extract_gender(self, texts: List[OCRText]) -> Optional[str]:
      
        gender_map = {
            "FEMALE": "FEMALE", 
            "MALE": "MALE",
            "TRANSGENDER": "TRANSGENDER",
        }

        for item in texts:
            text_upper = item.text.upper().strip()
            for keyword, value in gender_map.items():
                if keyword in text_upper:
                    return value

        # Proximity to "Sex" or "Gender" label
        raw = self.find_value_near_label(texts, ["Gender", "Sex",])
        if raw:
            raw_upper = raw.upper().strip()
            for keyword, value in gender_map.items():
                if keyword in raw_upper:
                    return value

        

        # 2. Search OCR text for English gender values
         # ---------------------------------------------------------
        for item in texts:
            text_upper = item.text.upper().strip()

            # Exact match is preferable to substring matching
            if text_upper in gender_map:
                return gender_map[text_upper]
        return None

    def _find_dob_or_gender_anchor(self, texts: List[OCRText]) -> Optional[OCRText]:
        """Find the OCRText box containing DOB or Gender label/value to use as a layout anchor."""
        
        anchor_keywords = ["DOB", "DATE OF BIRTH", "BIRTH", "YOB", "YEAR OF BIRTH","MALE", "FEMALE", "TRANSGENDER"]
        for item in texts:
            up = item.text.upper()
            if any(kw in up for kw in anchor_keywords):
                return item
        return None

    def extract_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract the person's name as a raw string.

        Priority:
          1. Text directly below / to the right of "Name:" label (if explicitly present)
          2. Spatial Anchor: Text line situated directly ABOVE the DOB or Gender line
          3. Heuristic: highest-confidence alphabetic text that passes the blacklist filter
        """
        # 1. Inline or Label-proximity (if "Name:" label is explicitly present)
        for item in texts:
            up = item.text.upper()
            if "NAME" in up or "Name" in up or "name" in up:
                cleaned = re.sub(r"^(name|Name)[\s\:\-]*", "", item.text, flags=re.IGNORECASE).strip()
                if cleaned and self._is_plausible_name(cleaned):
                    return cleaned

        label_keywords = ["Name", "NAME"]
        candidate = self.find_value_near_label(texts, label_keywords, direction="auto", max_distance=500.0)

        if candidate and self._is_plausible_name(candidate):
            return candidate

        # 2. Spatial Anchor: Search for English text line directly ABOVE DOB or Gender
        dob_anchor = self._find_dob_or_gender_anchor(texts)
        if dob_anchor:
            anchor_min_y = dob_anchor.bounding_box.min_y
            above_candidates = []
            for item in texts:
                if item is dob_anchor:
                    continue
                # Line must be situated vertically ABOVE DOB/Gender anchor (within 150px)
                y_gap = anchor_min_y - item.bounding_box.max_y
                if -10 <= y_gap <= 250:
                    if self._is_plausible_name(item.text):
                        above_candidates.append((y_gap, item))

            if above_candidates:
                # Sort by vertical distance ascending (closest above DOB first)
                above_candidates.sort(key=lambda c: c[0])
                return above_candidates[0][1].text

        # 3. Heuristic: scan all texts
        sorted_texts = sorted(texts, key=lambda t: t.confidence, reverse=True)
        for item in sorted_texts:
            if self._is_plausible_name(item.text) and item.confidence >= 0.70:
                return item.text

        return None

    def _is_plausible_name(self, text: str) -> bool:
        """Return True if text could be an Indian person's name (1 to 5 words)."""
        text = text.strip()
        if not text:
            return False

        # Must not contain digits
        if any(c.isdigit() for c in text):
            return False

        # Split into words
        words = text.split()

        # 1 to 5 words (allows single-word names like 'Sunil' as well as full names)
        # if len(words) < 1 or len(words) > 5:
        #     return False

        # Every word: letters only (allow dot/apostrophe inside)
        for w in words:
            cleaned = w.replace(".", "").replace("'", "")
            if not cleaned.isalpha():
                return False

        # If single word, length must be at least 3 letters
        # if len(words) == 1:
        #     cleaned_single = words[0].replace(".", "").replace("'", "")
        #     if len(cleaned_single) < 3:
        #         return False

        # Blacklist check
        lower_text = text.lower()
        for bl in _NAME_BLACKLIST:
            if bl in lower_text:
                return False

        return True

    # ── Address ───────────────────────────────────────────────────────────

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