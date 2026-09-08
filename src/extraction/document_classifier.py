import re
from typing import Optional
from src.schemas.document_schemas import OCRResult

class DocumentClassifier:
    """
    Classifies documents based on source context hints and OCR keyword heuristics.
    Uses word-boundary regex to avoid substring false positives (e.g. 'PAN' in 'PANCHAL').
    """
    AADHAAR_KEYWORDS = [
        "GOVERNMENT OF INDIA", "UNIQUE IDENTIFICATION", "ENROLMENT NO",
        "DOB", "YEAR OF BIRTH", "MERA AADHAAR", "AADHAAR"
    ]
    PAN_KEYWORDS = [
        "INCOME TAX DEPARTMENT", "PAN"
    ]
    LICENCE_KEYWORDS = [
        "DRIVING LICENCE", "UNION OF INDIA", "TRANSPORT", "DL NO",
        "AUTHORISATION TO DRIVE", "DRIVING LICENSE"
    ]
    RC_KEYWORDS = [
        "REGISTRATION CERTIFICATE", "CERTIFICATE OF REGISTRATION",
        "TRANSPORT DEPARTMENT", "REGISTERING AUTHORITY", "REGN NO", "CHASSIS"
    ]

    def classify(self, ocr_result: OCRResult, source_hint: Optional[str] = None) -> str:
        """
        Returns one of: 'aadhaar', 'pan', 'licence', 'rc', or 'unknown'.
        """
        text_upper = ocr_result.raw_text.upper()

        def count_matches(keywords):
            count = 0
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", text_upper):
                    count += 1
            return count

        aadhaar_score = count_matches(self.AADHAAR_KEYWORDS)
        pan_score = count_matches(self.PAN_KEYWORDS)
        licence_score = count_matches(self.LICENCE_KEYWORDS)
        rc_score = count_matches(self.RC_KEYWORDS)

        # Source hint weighting
        hint_str = (source_hint or "").lower()
        if "aadhaar" in hint_str and aadhaar_score > 0:
            aadhaar_score += 2
        elif "pan" in hint_str and pan_score > 0:
            pan_score += 2
        elif ("licence" in hint_str or "license" in hint_str) and licence_score > 0:
            licence_score += 2
        elif "rc" in hint_str and rc_score > 0:
            rc_score += 2

        scores = {
            "aadhaar": aadhaar_score,
            "pan": pan_score,
            "licence": licence_score,
            "rc": rc_score
        }

        best_match, max_score = max(scores.items(), key=lambda item: item[1])

        if max_score > 0:
            return best_match

        # Fallback to source hint if no keywords matched
        if "aadhaar" in hint_str:
            return "aadhaar"
        if "pan" in hint_str:
            return "pan"
        if "licence" in hint_str or "license" in hint_str:
            return "licence"
        if "rc" in hint_str:
            return "rc"

        return "unknown"
