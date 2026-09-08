import re
from typing import Optional, List
from src.extraction.extractors.base_extractor import BaseExtractor
from src.schemas.document_schemas import RcData, OCRResult

class RcExtractor(BaseExtractor):
    """
    Extracts structured fields from Registration Certificate (RC) OCR text:
    owner_name, registration_number, vehicle_class.
    """
    REG_NUMBER_REGEX = re.compile(r"\b([A-Z]{2}[-\s]?[0-9]{1,2}[-\s]?[A-Z]{1,3}[-\s]?[0-9]{4})\b")
    CLASS_PREFIX_REGEX = re.compile(r"(?:Class\s*of\s*Vehicle|Veh(?:icle)?\s*Class|VCH\s*CLASS)[:\s]+([A-Za-z0-9 /-]+)", re.IGNORECASE)
    OWNER_PREFIX_REGEX = re.compile(r"(?:Owner(?:\s*Name)?|Name)[:\s]+([A-Za-z ]+)", re.IGNORECASE)

    COMMON_RC_CLASSES = [
        "MCWG", "MCWOG", "M-CYCLE", "MOTORCYCLE", "MOTOR CYCLE", "SCOOTER", "TWO WHEELER",
        "LMV", "LMV-NT", "MOTOR CAR", "CAR", "LIGHT MOTOR VEHICLE",
        "AUTO RICKSHAW", "3 WHEELER", "THREE WHEELER",
        "HGV", "LGV", "TRUCK", "HEAVY GOODS VEHICLE", "GOODS CARRIER", "GOOD CARRIER", "GOODS VEHICLE"
    ]

    REG_DATE_REGEX = re.compile(r"(?:Date\s*of\s*Reg(?:istratio)?n|Reg(?:istratio)?n\s*Date|Reg\s*Date|Regn\s*Dt|Reg\s*Dt|Date\s*of\s*Issue)[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})", re.IGNORECASE)
    REG_VALIDITY_REGEX = re.compile(r"(?:Fitness\s*Valid\s*Upto|Reg(?:istratio)?n\s*Valid\s*Upto|Valid\s*Upto|Valid\s*Till|Validity\s*Upto|Tax\s*Valid\s*Upto|Reg\s*Validity)[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})", re.IGNORECASE)

    HEADER_STOPWORDS = {
        "REGISTRATION", "CERTIFICATE", "TRANSPORT", "DEPARTMENT",
        "UNION", "INDIA", "REGISTERING", "AUTHORITY", "FORM", "CHASSIS"
    }

    def extract(self, ocr_result: OCRResult) -> RcData:
        raw_text = ocr_result.raw_text
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        reg_no = self._extract_reg_number(raw_text)
        v_class = self._extract_vehicle_class(raw_text, lines)
        owner_name = self._extract_owner_name(raw_text, lines)
        reg_date = self._extract_reg_date(raw_text)
        reg_validity = self._extract_reg_validity(raw_text)

        return RcData(
            owner_name=owner_name,
            registration_number=reg_no,
            vehicle_class=v_class,
            date_of_registration=reg_date,
            registration_validity=reg_validity
        )

    def _extract_reg_date(self, text: str) -> Optional[str]:
        match = self.REG_DATE_REGEX.search(text)
        if match:
            return match.group(1).replace("-", "/")
        return None

    def _extract_reg_validity(self, text: str) -> Optional[str]:
        match = self.REG_VALIDITY_REGEX.search(text)
        if match:
            return match.group(1).replace("-", "/")
        return None

    def _extract_reg_number(self, text: str) -> Optional[str]:
        match = self.REG_NUMBER_REGEX.search(text)
        if match:
            return re.sub(r"[\s-]+", "", match.group(1).upper())
        return None

    def _extract_vehicle_class(self, raw_text: str, lines: List[str]) -> Optional[str]:
        # 1. Try explicit prefix "Class of Vehicle: MCWG"
        match = self.CLASS_PREFIX_REGEX.search(raw_text)
        if match:
            candidate = match.group(1).strip()
            # Stop at line break or other field
            candidate_first_word = candidate.split("\n")[0].strip()
            if len(candidate_first_word) >= 2:
                return candidate_first_word

        # 2. Check for exact known keywords in text
        text_upper = raw_text.upper()
        for known_cls in self.COMMON_RC_CLASSES:
            if re.search(r"\b" + re.escape(known_cls) + r"\b", text_upper):
                return known_cls

        return None

    def _extract_owner_name(self, raw_text: str, lines: List[str]) -> Optional[str]:
        # Try explicit prefix "Owner Name: John Doe"
        match = self.OWNER_PREFIX_REGEX.search(raw_text)
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
