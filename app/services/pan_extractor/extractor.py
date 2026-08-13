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

    def extract_pan(self, ocr_front: Optional[OCRResult], ocr_back: Optional[OCRResult]) -> PanData:
        """Process front side for PAN extraction (isolated from back side)."""
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

        # Merge diagnostics from both sides for remaining missing fields
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

        # ── Generate per-field diagnostics ────────────────────────────────
        self._generate_diagnostics(data, texts)

        return data

    # ── Diagnostics ──────────────────────────────────────────────────────

    def _generate_diagnostics(self, data: PanData, texts: List[OCRText]) -> None:
        """For every missing field, explain why OCR failed to extract it."""
        if not texts:
            for field in ["pan_number", "full_name", "father_name", "date_of_birth"]:
                data.field_diagnostics[field] = "OCR returned no text from image"
            return

        avg_conf = sum(t.confidence for t in texts) / len(texts)
        low_quality_msg = ""
        if avg_conf < 0.5:
            low_quality_msg = f"Low OCR confidence ({avg_conf:.0%}); image may be blurry or low quality"

        if not data.pan_number:
            all_text = " ".join(t.text.upper() for t in texts)
            alpha_num = re.findall(r"[A-Z]{3,}[0-9]+[A-Z]*", re.sub(r"\s", "", all_text))
            if not alpha_num:
                data.field_diagnostics["pan_number"] = low_quality_msg or "No alphanumeric PAN-like pattern found in OCR text"
            else:
                data.field_diagnostics["pan_number"] = f"Alphanumeric patterns found but none match PAN format (AAAAA9999A)"

        if not data.full_name:
            name_label = self._find_label_box(texts, ["Name", "NAME"])
            if not name_label:
                data.field_diagnostics["full_name"] = low_quality_msg or "OCR did not detect a 'Name' label on the card"
            else:
                data.field_diagnostics["full_name"] = "Name label found but nearby text rejected by plausibility filter"

        if not data.father_name:
            father_label = self._find_label_box(texts, ["Father", "FATHER", "Parent"])
            if not father_label:
                data.field_diagnostics["father_name"] = low_quality_msg or "OCR did not detect a 'Father's Name' label on the card"
            else:
                data.field_diagnostics["father_name"] = "Father's Name label found but nearby text rejected by plausibility filter"

        if not data.date_of_birth:
            date_like = re.findall(r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}", " ".join(t.text for t in texts))
            if not date_like:
                data.field_diagnostics["date_of_birth"] = low_quality_msg or "No date pattern found in OCR text"
            else:
                data.field_diagnostics["date_of_birth"] = f"Date(s) found ({', '.join(date_like[:3])}) but could not parse to valid DOB"

    # ── PAN Number ────────────────────────────────────────────────────────────

    def extract_pan_number(self, texts: List[OCRText]) -> Optional[str]:
        """
        Find the 10-character PAN number.
        Pattern: 5 uppercase letters + 4 digits + 1 uppercase letter.
        """
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

    # ── Date of Birth ─────────────────────────────────────────────────────────

    def extract_dob(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract DOB from PAN card.
        Labels: "Date of Birth", "DOB", "Birth Date", "जन्म तिथि"
        """
        label_keywords = [
            "Date of Birth", "DOB", "Birth Date",
            "Date Of Birth", "D.O.B", "जन्म तिथि",
            "D.O.B.", "D O B", "BIRTH",
        ]

        # 1. Check above DOB label (in case values are above labels)
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

        # 2. Label-proximity below/right
        raw = self.find_value_near_label(texts, label_keywords, max_distance=500.0)
        if raw:
            parsed = normalize_dob(raw)
            if parsed:
                return parsed

        # 3. Regex fallback — date near a DOB-like label
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

        # 4. Last resort — any date on the card
        for item in texts:
            for dp in date_patterns:
                m = re.search(dp, item.text)
                if m:
                    parsed = normalize_dob(m.group(1))
                    if parsed:
                        return parsed

        return None

    # ── Person Name ───────────────────────────────────────────────────────

    def extract_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract person's name from PAN card.
        Handles both layout types:
          Layout A: Label above Value (Name -> [Person Name])
          Layout B: Value above Label ([Person Name] -> Name)
        """

        # 0. PAN card special case: no literal "Name" label exists —
        #    name is the first plausible text block directly below "INCOME TAX" header
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

        # 1. Check if plausible name exists directly ABOVE the Name label (within 65px)
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

        # 2. Below the Name label with generous radius
        candidate = self.find_value_near_label(
            texts,
            label_keywords,
            direction="below",
            max_distance=200.0,
        )
        if candidate and self._is_plausible_name(candidate):
            return candidate

        # 3. Auto direction
        candidate = self.find_value_near_label(
            texts,
            label_keywords,
            direction="auto",
            max_distance=400.0,
        )
        if candidate and self._is_plausible_name(candidate):
            return candidate

        # 4. Positional fallback — scan texts between Name label and Father label
        father_box = self._find_label_box(texts, ["Father", "FATHER"])

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

        # 5. Last resort: highest confidence plausible name
        for item in sorted(texts, key=lambda x: x.confidence, reverse=True):
            if self._is_plausible_name(item.text) and item.confidence >= 0.75:
                return item.text

        return None

    # ── Father Name ───────────────────────────────────────────────────────

    def _x_overlap(self, box_a, box_b, min_ratio: float = 0.3) -> bool:
        """True if two boxes overlap horizontally by at least min_ratio of the narrower box's width."""
        a_min, a_max = box_a.bounding_box.min_x, box_a.bounding_box.max_x
        b_min, b_max = box_b.bounding_box.min_x, box_b.bounding_box.max_x
        overlap = min(a_max, b_max) - max(a_min, b_min)
        if overlap <= 0:
            return False
        narrower = min(a_max - a_min, b_max - b_min)
        return narrower > 0 and (overlap / narrower) >= min_ratio

    def _centroid_y(self, t) -> float:
        return (t.bounding_box.min_y + t.bounding_box.max_y) / 2.0

    def extract_father_name_raw(self, texts: List[OCRText], person_name: Optional[str] = None) -> Optional[str]:
        """
        Extract father's/parent's name from PAN card.
        """
        label_keywords = [
            "Father's Name", "Father Name", "FATHER'S NAME", "Parent's Name",
            "Father", "FATHER",
        ]
        father_box = self._find_label_box(texts, label_keywords)

        def is_valid_father(t_text: str) -> bool:
            if not self._is_plausible_name(t_text):
                return False
            if person_name:
                p_norm = person_name.strip().lower()
                f_norm = t_text.strip().lower()
                if p_norm == f_norm:
                    return False
            return True

        # New step 0 in extract_father_name_raw, before the generic label search:
        if not father_box:
            income_tax_box = self._find_label_box(texts, ["INCOME TAX", "INCOMETAX"])
            if income_tax_box:
                ref_y = self._centroid_y(income_tax_box)
                below_candidates = sorted(
                    [t for t in texts
                    if t is not income_tax_box
                    and self._centroid_y(t) > ref_y
                    and self._x_overlap(income_tax_box, t)],
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

        # 1. Check directly ABOVE the Father Name label (within 65px)
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

        # 2. Below the Father's Name label
        candidate = self.find_value_near_label(
            texts,
            label_keywords,
            direction="below",
            max_distance=200.0,
        )
        if candidate and is_valid_father(candidate):
            return candidate

        # 3. Auto direction
        candidate = self.find_value_near_label(
            texts,
            label_keywords,
            direction="auto",
            max_distance=400.0,
        )
        if candidate and is_valid_father(candidate):
            return candidate

        # 4. Positional fallback — text between Father's Name label and DOB label
        dob_box = self._find_label_box(texts, ["Date of Birth", "DOB", "D.O.B", "Birth"])
        name_box = self._find_label_box(texts, ["Name", "NAME"])

        start_y = father_box.bounding_box.max_y if father_box else (name_box.bounding_box.max_y if name_box else 0)
        end_y = dob_box.bounding_box.min_y if dob_box else start_y + 300

        between = [
            t for t in texts
            if start_y - 5 <= t.bounding_box.min_y <= end_y + 5
            and t is not father_box and t is not name_box and t is not dob_box
        ]
        for t in between:
            if is_valid_father(t.text):
                return t.text

        # 5. Last resort: highest confidence plausible name distinct from person_name
        for item in sorted(texts, key=lambda x: x.confidence, reverse=True):
            if is_valid_father(item.text) and item.confidence >= 0.70:
                return item.text

        return None

    # ── Helpers ───────────────────────────────────────────────────────────

    _NAME_BLACKLIST = {
        "income", "tax", "department", "government", "india", "permanent",
        "account", "number", "pan", "name", "father", "birth", "date",
        "signature",
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

        text_words = set(text.lower().split())
        for bl in self._NAME_BLACKLIST:
            if bl in text_words:
                return False

        return True
