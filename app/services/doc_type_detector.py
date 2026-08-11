"""
Document Type Detector
======================
Classifies an image as AADHAAR / PAN / DRIVING_LICENCE / RC / UNKNOWN
using keyword heuristics on raw OCR text.

This is intentionally fast — it runs before extraction to route the image
to the correct extractor. No regex needed; simple substring matching is
sufficient because the key header words are highly distinctive.
"""

from enum import Enum
from typing import List, Dict

from app.models.ocr_models import OCRText


class DocumentType(str, Enum):
    AADHAAR = "AADHAAR"
    PAN = "PAN"
    DRIVING_LICENCE = "DRIVING_LICENCE"
    RC = "RC"
    UNKNOWN = "UNKNOWN"


# Keywords that strongly identify each document type
# Put the most distinctive first; each match scores +1
_KEYWORDS: Dict[DocumentType, List[str]] = {
    DocumentType.AADHAAR: [
        "aadhaar",
        "uidai",
        "unique identification authority",
        "enrolment no",
        "uid",
        "आधार",       # Hindi
        "આધાર",       # Gujarati
        "भारत सरकार",  # Government of India in Hindi — appears on Aadhaar back
    ],
    DocumentType.PAN: [
        "income tax department",
        "permanent account number",
        "govt. of india",
        "income tax",
        # PAN number pattern alone isn't enough — rely on surrounding text
    ],
    DocumentType.DRIVING_LICENCE: [
        "driving licence",
        "driving license",
        "d/l no",
        "dl no",
        "dl no.",
        "licence no",
        "license no",
        "licence",
        "license",
        "transport department",
        "motor vehicle",
        "form 7",
        "rule 16",
        "mcwg",
        "lmv",
        "hmv",
        "hpmv",
        "non-transport",
        "3w-cab",
        "lmvcab",
    ],
    DocumentType.RC: [
        "registration certificate",
        "regn no",
        "reg. no",
        "chassis no",
        "engine no",
        "fitness upto",
        "fuel type",
        "rc book",
        "registration no",
        "insurance",
    ],
}


class DocTypeDetector:
    """Detects document type from OCR text using keyword scoring."""

    def detect(self, texts: List[OCRText]) -> DocumentType:
        full_text = " ".join(item.text.lower() for item in texts)

        scores: Dict[DocumentType, int] = {dt: 0 for dt in _KEYWORDS}

        for doc_type, keywords in _KEYWORDS.items():
            for kw in keywords:
                if kw in full_text:
                    scores[doc_type] += 1

        best = max(scores, key=lambda dt: scores[dt])

        if scores[best] == 0:
            return DocumentType.UNKNOWN

        return best

    def detect_from_text(self, text: str) -> DocumentType:
        """Convenience overload that accepts a raw string."""
        text_lower = text.lower()

        scores: Dict[DocumentType, int] = {dt: 0 for dt in _KEYWORDS}

        for doc_type, keywords in _KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[doc_type] += 1

        best = max(scores, key=lambda dt: scores[dt])

        if scores[best] == 0:
            return DocumentType.UNKNOWN

        return best
