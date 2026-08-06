"""
PAN Card Extractor
==================
Extracts and normalizes:
  - PAN number (AAAAA9999A format)
  - Full name + split (first/middle/last)
  - Father's / parent's name
  - Date of birth

PAN Card Layout (standard NSDL/UTI card):
  Line 1: INCOME TAX DEPARTMENT, GOVT. OF INDIA
  Line 2: PERMANENT ACCOUNT NUMBER   (or "INCOME TAX DEPARTMENT")
  Line 3: [PAN number]               e.g. ABCDE1234F
  Line 4: Name                       (label)
  Line 5: [Person's name]
  Line 6: Father's Name              (label)
  Line 7: [Father's name]
  Line 8: Date of Birth              (label)
  Line 9: [DD/MM/YYYY]

Handled variants:
  - Standard blue card (NSDL)
  - Orange card (UTI)
  - e-PAN PDF
  - Scanned / photographed card
  - Partially visible card
"""

import re
from typing import List, Optional

from app.models.ocr_models import OCRResult, OCRText
from app.services.base_extractor import BaseExtractor
from app.services.pan_extractor.models import PanData
from app.utils.normalizer import normalize_dob, normalize_pan_number, normalize_name


_PAN_REGEX = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b")


class PanExtractor(BaseExtractor):
    """Extracts structured data from PAN card OCR output."""

    def extract(self, ocr_result: OCRResult) -> PanData:
        texts = ocr_result.texts
        data = PanData()

        data.pan_number = self.extract_pan_number(texts)
        data.dob = self.extract_dob(texts)

        name_raw = self.extract_name_raw(texts)
        if name_raw:
            parsed = normalize_name(name_raw)
            data.full_name = parsed["full_name"]
            data.first_name = parsed["first_name"]
            data.middle_name = parsed["middle_name"]
            data.last_name = parsed["last_name"]

        father_raw = self.extract_father_name_raw(texts)
        if father_raw:
            parsed = normalize_name(father_raw)
            data.father_name = parsed["full_name"]

        return data

    # ── PAN Number ────────────────────────────────────────────────────────────

    def extract_pan_number(self, texts: List[OCRText]) -> Optional[str]:
        """
        Find the 10-character PAN number.
        Pattern: 5 uppercase letters + 4 digits + 1 uppercase letter.

        Handles OCR errors like:
          - 'O' vs '0' (unlikely but handled by trying both)
          - spaces inserted in the number
          - mixed case output from OCR
        """
        for item in texts:
            # Normalize: remove spaces, uppercase
            cleaned = re.sub(r"\s+", "", item.text.upper())

            m = _PAN_REGEX.search(cleaned)
            if m:
                return normalize_pan_number(m.group(1))

        # Fallback: look across joined text (handles split across two boxes)
        full = " ".join(t.text.upper() for t in texts)
        full_clean = re.sub(r"\s+", "", full)
        m = _PAN_REGEX.search(full_clean)
        if m:
            return normalize_pan_number(m.group(1))

        return None

    # ── Date of Birth ─────────────────────────────────────────────────────────

    def extract_dob(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract DOB from PAN card.
        Labels: "Date of Birth", "DOB", "Birth Date", "जन्म तिथि"
        """
        label_keywords = [
            "Date of Birth", "DOB", "Birth Date",
            "Date Of Birth", "D.O.B", "जन्म तिथि",
        ]

        # 1. Label-proximity
        raw = self.find_value_near_label(texts, label_keywords)
        if raw:
            parsed = normalize_dob(raw)
            if parsed:
                return parsed

        # 2. Regex fallback — date near a DOB-like label
        date_pattern = r"\b(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})\b"

        for item in texts:
            text_up = item.text.upper()
            if "DOB" in text_up or "BIRTH" in text_up or "DATE" in text_up:
                m = re.search(date_pattern, item.text)
                if m:
                    return normalize_dob(m.group(1))

        # 3. Last resort — any date on the card
        for item in texts:
            m = re.search(date_pattern, item.text)
            if m:
                return normalize_dob(m.group(1))

        return None

    # ── Person Name ───────────────────────────────────────────────────────────

    def extract_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract person's name from PAN card.

        On a PAN card, the layout is:
          ...
          "Name"
          [PERSON NAME]
          "Father's Name"
          [FATHER NAME]
          ...

        Strategy:
          1. Find "Name" label, get text directly BELOW it (200px radius).
          2. Scan texts between Name label and Father's Name label.
          3. High-confidence heuristic fallback.
        """
        label_keywords = ["Name", "NAME", "नाम"]

        # 1. Below the Name label with generous radius
        candidate = self.find_value_near_label(
            texts,
            label_keywords,
            direction="below",
            max_distance=200.0,
        )
        if candidate and self._is_plausible_name(candidate):
            return candidate

        # 2. Auto direction with generous radius
        candidate = self.find_value_near_label(
            texts,
            label_keywords,
            direction="auto",
            max_distance=400.0,
        )
        if candidate and self._is_plausible_name(candidate):
            return candidate

        # 3. Positional fallback — scan texts between Name label and Father label
        name_box = self._find_label_box(texts, label_keywords)
        father_box = self._find_label_box(texts, ["Father", "FATHER", "पिता"])

        if name_box:
            start_y = name_box.bounding_box.max_y
            end_y = father_box.bounding_box.min_y if father_box else start_y + 300

            between = [
                t for t in texts
                if start_y - 5 <= t.bounding_box.min_y <= end_y + 5
                and t is not name_box
            ]
            for t in between:
                if self._is_plausible_name(t.text):
                    return t.text

        # 4. Last resort: highest confidence plausible name
        for item in sorted(texts, key=lambda x: x.confidence, reverse=True):
            if self._is_plausible_name(item.text) and item.confidence >= 0.75:
                return item.text

        return None

    # ── Father Name ───────────────────────────────────────────────────────────

    def extract_father_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract father's/parent's name from PAN card.
        Labels: "Father's Name", "Father Name", "पिता का नाम"
        """
        label_keywords = [
            "Father's Name", "Father Name", "FATHER'S NAME",
            "पिता का नाम", "पिता", "Parent's Name",
        ]

        candidate = self.find_value_near_label(
            texts,
            label_keywords,
            direction="below",
            max_distance=80.0,
        )
        if candidate and self._is_plausible_name(candidate):
            return candidate

        candidate = self.find_value_near_label(
            texts,
            label_keywords,
            direction="auto",
            max_distance=300.0,
        )
        if candidate and self._is_plausible_name(candidate):
            return candidate

        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    _NAME_BLACKLIST = {
        "income", "tax", "department", "government", "india", "permanent",
        "account", "number", "pan", "name", "father", "birth", "date",
        "signature", "नाम", "तिथि",
    }

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

        # Use WORD-LEVEL matching (not substring) to avoid:
        # 'pan' matching inside 'PANCHAL', 'name' inside 'namaste', etc.
        text_words = set(text.lower().split())
        for bl in self._NAME_BLACKLIST:
            if bl in text_words:
                return False

        return True
