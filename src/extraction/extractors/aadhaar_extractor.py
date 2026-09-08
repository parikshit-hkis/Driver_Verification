import re
from typing import Optional, List
from src.extraction.extractors.base_extractor import BaseExtractor
from src.schemas.document_schemas import AadhaarData, OCRResult

class AadhaarExtractor(BaseExtractor):
    """
    Extracts structured fields from Aadhaar OCR text:
    name, date_of_birth, aadhaar_number.
    """
    AADHAAR_REGEX = re.compile(r"\b(\d{4}\s?\d{4}\s?\d{4})\b")
    DOB_REGEX = re.compile(r"(?:DOB|Date of Birth|Year of Birth)[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4}|[0-9]{4})", re.IGNORECASE)

    HEADER_STOPWORDS = {
        "GOVERNMENT", "INDIA", "UNIQUE", "IDENTIFICATION", "AUTHORITY",
        "ENROLMENT", "HELP", "UIDAI", "MERA", "AADHAAR", "MERI", "PEHCHAN",
        "MALE", "FEMALE", "TRANSGENDER"
    }

    def extract(self, ocr_result: OCRResult) -> AadhaarData:
        raw_text = ocr_result.raw_text
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        aadhaar_number = self._extract_aadhaar_number(raw_text)
        dob = self._extract_dob(raw_text)
        name = self._extract_name(lines)

        return AadhaarData(
            name=name,
            date_of_birth=dob,
            aadhaar_number=aadhaar_number
        )

    def _extract_aadhaar_number(self, text: str) -> Optional[str]:
        match = self.AADHAAR_REGEX.search(text)
        if match:
            # Clean spaces
            return re.sub(r"\s+", "", match.group(1))
        return None

    def _extract_dob(self, text: str) -> Optional[str]:
        match = self.DOB_REGEX.search(text)
        if match:
            return match.group(1).replace("-", "/")
        return None

    def _extract_name(self, lines: List[str]) -> Optional[str]:
        """
        Heuristic: Name is typically the first clean alphabetic line
        appearing before the DOB line, or following the header lines.
        """
        dob_index = -1
        for idx, line in enumerate(lines):
            if re.search(r"DOB|Date of Birth|Year of Birth", line, re.IGNORECASE):
                dob_index = idx
                break

        # If DOB was found, look backwards for the name
        if dob_index > 0:
            for idx in range(dob_index - 1, -1, -1):
                candidate = lines[idx].strip()
                if self._is_valid_name_candidate(candidate):
                    return candidate

        # Fallback: scan lines from top
        for line in lines:
            if self._is_valid_name_candidate(line):
                return line

        return None

    def _is_valid_name_candidate(self, line: str) -> bool:
        # Must be mostly letters and spaces, at least 3 chars
        cleaned = re.sub(r"[^A-Za-z\s]", "", line).strip()
        if len(cleaned) < 3 or len(cleaned.split()) < 1:
            return False

        words = set(cleaned.upper().split())
        # Must not contain header stopwords
        if words.intersection(self.HEADER_STOPWORDS):
            return False

        # Should not contain numbers
        if any(c.isdigit() for c in line):
            return False

        return True
