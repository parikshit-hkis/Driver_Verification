import re
from typing import Optional, List, Tuple
from src.extraction.extractors.base_extractor import BaseExtractor
from src.schemas.document_schemas import PanData, OCRResult

class PanExtractor(BaseExtractor):
    """
    Extracts structured fields from Indian PAN card OCR text:
    name, pan_number.
    """
    PAN_REGEX = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b")
    HEADER_STOPWORDS = {
        "INCOME", "TAX", "DEPARTMENT", "GOVT", "INDIA",
        "PERMANENT", "ACCOUNT", "NUMBER", "CARD", "FATHER", "NAME"
    }

    FATHER_PREFIX_REGEX = re.compile(r"(?:Father(?:'s)?\s*Name|Father\s*Name|Fathers\s*Name)[:\s]+([A-Za-z ]+)", re.IGNORECASE)
    NAME_PREFIX_REGEX = re.compile(r"(?:Name|Cardholder(?:\s*Name)?)[:\s]+([A-Za-z ]+)", re.IGNORECASE)
    DOB_REGEX = re.compile(r"(?:DOB|Date\s*of\s*Birth)[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})", re.IGNORECASE)
    DATE_FALLBACK_REGEX = re.compile(r"\b([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})\b")

    def extract(self, ocr_result: OCRResult) -> PanData:
        raw_text = ocr_result.raw_text
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        pan_number = self._extract_pan_number(raw_text)
        name, father_name = self._extract_names(raw_text, lines)
        dob = self._extract_dob(raw_text)

        return PanData(
            name=name,
            father_name=father_name,
            date_of_birth=dob,
            pan_number=pan_number
        )

    def _extract_pan_number(self, text: str) -> Optional[str]:
        match = self.PAN_REGEX.search(text.upper())
        if match:
            return match.group(1).upper()
        return None

    def _extract_dob(self, text: str) -> Optional[str]:
        match = self.DOB_REGEX.search(text)
        if match:
            return match.group(1).replace("-", "/")
        fallback = self.DATE_FALLBACK_REGEX.search(text)
        if fallback:
            return fallback.group(1).replace("-", "/")
        return None

    def _extract_names(self, raw_text: str, lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
        """
        Extracts cardholder name and father's name from PAN OCR lines.
        """
        # 1. Check explicit prefix for Father's Name
        father_name = None
        f_match = self.FATHER_PREFIX_REGEX.search(raw_text)
        if f_match:
            candidate = f_match.group(1).split("\n")[0].strip()
            if len(candidate) >= 3 and not any(c.isdigit() for c in candidate):
                father_name = candidate

        # 2. Check explicit prefix for Cardholder Name (ensuring not preceded by Father)
        name = None
        for line in lines:
            line_strip = line.strip()
            if re.search(r"Father", line_strip, re.IGNORECASE):
                continue
            m = re.search(r"(?:Name|Cardholder(?:\s*Name)?)\s*[:\-]\s*([A-Za-z ]+)", line_strip, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                if len(cand) >= 3 and not any(c.isdigit() for c in cand):
                    name = cand
                    break

        # 3. Positional heuristic on clean alphabetic lines:
        clean_lines = []
        for line in lines:
            line_upper = line.upper().strip()
            if self.PAN_REGEX.search(line_upper):
                continue
            if any(c.isdigit() for c in line):
                continue
            if re.search(r"Father", line_upper):
                continue
            words = set(re.sub(r"[^A-Za-z\s]", "", line_upper).split())
            if not words or words.intersection(self.HEADER_STOPWORDS):
                continue
            cleaned = re.sub(r"[^A-Za-z\s]", "", line).strip()
            if len(cleaned) >= 3 and len(cleaned.split()) >= 1:
                clean_lines.append(cleaned)

        if not name and clean_lines:
            name = clean_lines[0]

        if not father_name and len(clean_lines) >= 2:
            father_name = clean_lines[1]

        return name, father_name


