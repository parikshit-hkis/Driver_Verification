import re
from typing import Optional, List
from src.extraction.extractors.base_extractor import BaseExtractor
from src.schemas.document_schemas import LicenceData, OCRResult

class LicenceExtractor(BaseExtractor):
    """
    Extracts structured fields from Indian Driving Licence OCR text:
    name, licence_number, vehicle_classes.
    """
    DL_NUMBER_REGEX = re.compile(r"\b([A-Z]{2}[-\s]?[0-9]{2}[-\s]?[0-9]{4,11})\b")
    NAME_PREFIX_REGEX = re.compile(r"(?:Name|Holder(?:'s)?\s*Name)[:\s]+([A-Za-z ]+)", re.IGNORECASE)

    KNOWN_COV_CLASSES = {
        "MCWG", "MCWOG", "M/CYCL", "MC", "LMV", "LMV-NT", "LMV-TR",
        "TRANS", "HGV", "HMV", "3W-CAB", "3W-NT", "E-RICKSHAW"
    }

    HEADER_STOPWORDS = {
        "DRIVING", "LICENCE", "LICENSE", "UNION", "INDIA", "TRANSPORT",
        "DEPARTMENT", "AUTHORITY", "FORM", "AUTHORISATION", "DRIVE", "VALIDITY"
    }

    ISSUE_DATE_REGEX = re.compile(r"(?:Issue\s*Date|Date\s*of\s*Issue|DOI|Issued\s*On|Issue\s*Dt|Iss\s*Dt)[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})", re.IGNORECASE)
    VALIDITY_REGEX = re.compile(r"(?:Valid(?:ity)?(?:\s*Upto|\s*To)?|Valid\s*Till|NT\s*Valid\s*Upto|TR\s*Valid\s*Upto|Val\s*Upto)[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})", re.IGNORECASE)

    def extract(self, ocr_result: OCRResult) -> LicenceData:
        raw_text = ocr_result.raw_text
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        dl_number = self._extract_dl_number(raw_text)
        name = self._extract_name(raw_text, lines)
        cov_classes = self._extract_vehicle_classes(raw_text)
        issue_date = self._extract_issue_date(raw_text)
        validity = self._extract_validity(raw_text)

        return LicenceData(
            name=name,
            issue_date=issue_date,
            validity=validity,
            licence_number=dl_number,
            vehicle_classes=cov_classes
        )

    def _extract_issue_date(self, text: str) -> Optional[str]:
        match = self.ISSUE_DATE_REGEX.search(text)
        if match:
            return match.group(1).replace("-", "/")
        return None

    def _extract_validity(self, text: str) -> Optional[str]:
        match = self.VALIDITY_REGEX.search(text)
        if match:
            return match.group(1).replace("-", "/")
        return None

    def _extract_dl_number(self, text: str) -> Optional[str]:
        match = self.DL_NUMBER_REGEX.search(text)
        if match:
            return re.sub(r"[\s-]+", "", match.group(1).upper())
        return None

    def _extract_name(self, raw_text: str, lines: List[str]) -> Optional[str]:
        # Try explicit prefix "Name: John Doe"
        match = self.NAME_PREFIX_REGEX.search(raw_text)
        if match:
            candidate = match.group(1).strip()
            if len(candidate) >= 3 and not any(c.isdigit() for c in candidate):
                return candidate

        # Fallback to scanning lines
        for line in lines:
            line_clean = re.sub(r"[^A-Za-z\s]", "", line).strip()
            if len(line_clean) < 3 or any(c.isdigit() for c in line):
                continue
            words = set(line_clean.upper().split())
            if not words or words.intersection(self.HEADER_STOPWORDS):
                continue
            return line_clean

        return None

    def _extract_vehicle_classes(self, text: str) -> List[str]:
        text_upper = text.upper()
        found_classes = set()
        for cov in self.KNOWN_COV_CLASSES:
            # Word boundary check
            if re.search(r"\b" + re.escape(cov) + r"\b", text_upper):
                found_classes.add(cov)
        return sorted(list(found_classes))
