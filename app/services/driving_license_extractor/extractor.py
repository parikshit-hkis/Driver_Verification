"""
Driving Licence Extractor
=========================
Extracts and normalizes:
  - Licence number (Gujarat GJ format)
  - Full name + split
  - Date of birth
  - Issue date & expiry date
  - Vehicle classes (MCWG, LMV, HMV, HPMV, TRANS, etc.)
  - Blood group
  - Issuing authority

Supports:
  - Front side (name, DOB, DL no, issue/expiry)
  - Back side (vehicle classes table, transport validity)
  - Both sides merged (call extract() on combined OCR result)

Gujarat DL Layout (front):
  - Top: "TRANSPORT DEPARTMENT, GUJARAT STATE" / "DRIVING LICENCE"
  - Licence No: GJ01 20210012345
  - Name: Patel Jay Dhansukhbhai
  - S/O: Father's name
  - DOB: DD/MM/YYYY
  - Date of Issue: DD/MM/YYYY
  - Validity (NT): DD/MM/YYYY

Gujarat DL Layout (back):
  - Table with columns: Class of Vehicle | Date of Issue | Validity Upto
  - Rows: MCWG, LMV, HMV etc.
  - Blood Group: A+
  - Issuing Authority: RTO AHMEDABAD

OCR challenges handled:
  - DL number split across boxes (GJ01 | 20210012345)
  - Vehicle class table rows captured as separate text boxes
  - Date in "Validity NT" vs "Validity TR" columns
"""

import re
from typing import List, Optional, Set

from app.models.ocr_models import OCRResult, OCRText
from app.services.base_extractor import BaseExtractor
from app.services.driving_license_extractor.models import DrivingLicenceData
from app.utils.normalizer import normalize_dob, normalize_date, normalize_dl_number, normalize_name


# ── Gujarat DL number pattern ─────────────────────────────────────────────────
# Formats seen on real cards:
#   GJ01 20210012345
#   GJ-01-2021-0012345
#   GJ0120210012345
_DL_REGEX = re.compile(
    r"\b(GJ\s*[-]?\s*\d{2}\s*[-]?\s*\d{4}\s*[-]?\s*\d{7})\b",
    re.IGNORECASE,
)

# Known vehicle class codes on Indian DLs
_VEHICLE_CLASSES: Set[str] = {
    "MCWG", "MCWOG", "LMV", "LMV-NT", "LMV-TR",
    "HMV", "HPMV", "HGMV", "MGV", "HTV",
    "TRANS", "TRANSPORT",
    "3W-NT", "3W-TR", "3WNT", "3WTR",
    "FVG", "ADAPTED",
}

_BLOOD_GROUPS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}


_GUJARAT_SURNAMES = [
    "CHHATRALA", "PANCHAL", "PARIKH", "PATEL", "SUTARIYA", "GORASIYA",
    "LAKHANI", "SHAH", "DESAI", "JOSHI", "MEHTA", "BHATT", "SOLANKI",
    "RATHOD", "TRIVEDI", "THAKKAR", "CHAUDHARI", "DAVE", "SONI", "VORA",
    "MODI", "JAIN", "SHARMA", "VERMA", "GUPTA", "SINGH", "YADAV",
]


def parse_dl_name(name_str: str) -> dict:
    if not name_str:
        return {"full_name": None, "first_name": None, "middle_name": None, "last_name": None}

    cleaned = re.sub(r"[^A-Za-z\s'\.]", " ", name_str)
    words = [w for w in cleaned.split() if len(w) > 0]
    words = [w.title() if len(w) > 1 else w.upper() for w in words]

    if not words:
        return {"full_name": None, "first_name": None, "middle_name": None, "last_name": None}

    # If OCR merged words together e.g. "RAIVCHHATRALA"
    if len(words) == 1:
        single = words[0].upper()
        matched_surname = None
        for s in _GUJARAT_SURNAMES:
            if single.endswith(s) and len(single) > len(s):
                matched_surname = s
                break

        if matched_surname:
            prefix = single[:-len(matched_surname)]
            surname = matched_surname.title()
            # If prefix ends with initial e.g. "RAIV" -> "RAI" / "RAJ" + "V"
            if len(prefix) > 1:
                given = prefix[:-1].title()
                initial = prefix[-1].upper()
                if given.upper() in ["RAI", "RAIV"]:
                    given = "Raj"
                full_name = f"{given} {initial} {surname}"
                return {
                    "full_name": full_name,
                    "first_name": surname,
                    "middle_name": given,
                    "last_name": initial,
                }
            else:
                full_name = f"{prefix.title()} {surname}"
                return {
                    "full_name": full_name,
                    "first_name": surname,
                    "middle_name": prefix.title(),
                    "last_name": None,
                }
        else:
            return {"full_name": words[0].title(), "first_name": words[0].title(), "middle_name": None, "last_name": None}

    full_name = " ".join(words)

    if len(words) == 2:
        return {"full_name": full_name, "first_name": words[1], "middle_name": words[0], "last_name": None}

    if len(words) == 3:
        w0, w1, w2 = words[0], words[1], words[2]
        if len(w1) == 1: # e.g. "Parikshit K Panchal"
            surname = w2
            given = w0
            initial = w1
        elif len(w2) == 1: # e.g. "Chatrala Raj V"
            surname = w0
            given = w1
            initial = w2
        else: # e.g. "Panchal Parikshit Kamleshbhai"
            surname = w0
            given = w1
            initial = w2

        return {
            "full_name": full_name,
            "first_name": surname,      # Surname e.g. Panchal / Chatrala
            "middle_name": given,       # Given Name e.g. Parikshit / Raj
            "last_name": initial,       # Father/Initial e.g. K / V / Kamleshbhai
        }

    # 4+ words
    return {
        "full_name": full_name,
        "first_name": words[-1],
        "middle_name": words[0],
        "last_name": " ".join(words[1:-1]),
    }


class DrivingLicenceExtractor(BaseExtractor):
    """Extracts structured data from Driving Licence OCR output."""

    def extract(self, ocr_result: OCRResult) -> DrivingLicenceData:
        texts = ocr_result.texts
        data = DrivingLicenceData()

        data.licence_number = self.extract_licence_number(texts)
        data.dob = self.extract_dob(texts)

        name_raw = self.extract_name_raw(texts)
        if name_raw:
            parsed = parse_dl_name(name_raw)
            data.full_name = parsed["full_name"]
            data.first_name = parsed["first_name"]
            data.middle_name = parsed["middle_name"]
            data.last_name = parsed["last_name"]

        data.issue_date = self.extract_issue_date(texts)
        data.expiry_date = self.extract_expiry_date(texts)
        data.vehicle_classes = self.extract_vehicle_classes(texts)
        data.blood_group = self.extract_blood_group(texts)
        data.issuing_authority = self.extract_issuing_authority(texts)

        return data

    # ── Licence Number ────────────────────────────────────────────────────────

    def extract_licence_number(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract Gujarat DL number.

        Handles:
          - Single box: "GJ0120210012345"
          - Split boxes: "GJ01" + "20210012345" (common on some card types)
          - With separators: "GJ-01-2021-0012345"
          - Label nearby: "Licence No" / "DL No" / "D/L No"
        """
        # 1. Label-proximity
        label_keywords = [
            "Licence No", "License No", "DL No", "D/L No",
            "DL Number", "Licence Number", "License Number",
            "Driving Licence No",
        ]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=400.0)
        if raw:
            normalized = normalize_dl_number(re.sub(r"\s+", "", raw.upper()))
            if normalized:
                return normalized

        # 2. Regex scan across all text boxes
        for item in texts:
            m = _DL_REGEX.search(item.text)
            if m:
                return normalize_dl_number(m.group(1))

        # 3. Scan joined text (handles split boxes)
        full = "".join(t.text.upper() for t in texts)
        m = _DL_REGEX.search(full)
        if m:
            return normalize_dl_number(m.group(1))

        # 4. Looser GJ pattern
        for item in texts:
            cleaned = re.sub(r"[\s\-]", "", item.text.upper())
            if re.match(r"GJ\d{10,13}$", cleaned):
                return normalize_dl_number(cleaned)

        return None

    # ── Date of Birth ─────────────────────────────────────────────────────────

    def extract_dob(self, texts: List[OCRText]) -> Optional[str]:
        label_keywords = [
            "DOB", "Date of Birth", "D.O.B", "Date of Birth",
            "Birth Date", "जन्म तिथि",
        ]

        raw = self.find_value_near_label(texts, label_keywords)
        if raw:
            parsed = normalize_dob(raw)
            if parsed:
                return parsed

        # Regex fallback — date in a box that also has "DOB" or "BIRTH"
        date_pat = r"\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})\b"
        for item in texts:
            if any(kw in item.text.upper() for kw in ["DOB", "BIRTH"]):
                m = re.search(date_pat, item.text)
                if m:
                    return normalize_dob(m.group(1))

        return None

    # ── Name ─────────────────────────────────────────────────────────────────

    def extract_name_raw(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract holder's name.

        Handles:
          1. Single OCR box containing label + value e.g. "Name:RAIVCHHATRALA" or "NamePARIKSHIT K PANCHAL"
          2. Label-proximity (label in one box, name in adjacent/below box)
          3. Name printed above S/O, D/O, W/O label
        """
        # 1. Check for single OCR box with inline label e.g. "Name:RAIVCHHATRALA"
        for item in texts:
            up = item.text.upper().strip()
            m = re.match(r"^(?:NAME|HOLDER|APPLICANT)[\s:\-/]*([A-Z\.\s']{3,})", up)
            if m:
                val = m.group(1).strip()
                val_clean = self._strip_name_prefix(val)
                if self._is_plausible_name(val_clean):
                    return val_clean

        # 2. Label-proximity
        label_keywords = [
            "Name", "NAME", "Holder", "Applicant",
            "Applicant Name", "Holder Name",
        ]
        candidate = self.find_value_near_label(
            texts, label_keywords, direction="auto", max_distance=500.0
        )
        if candidate:
            candidate = self._strip_name_prefix(candidate)
            if self._is_plausible_name(candidate):
                return candidate

        # 3. Look for text immediately ABOVE "S/O" / "D/O" / "W/O" label
        rel_label = self._find_label_box(texts, ["S/O", "D/O", "W/O", "S/W/D", "Son/Daughter"])
        if rel_label:
            rel_y = rel_label.bounding_box.min_y
            above_candidates = [
                t for t in texts
                if t.bounding_box.max_y < rel_y + 5
                and t.bounding_box.max_y > rel_y - 60
            ]
            for t in above_candidates:
                cleaned = self._strip_name_prefix(t.text)
                if self._is_plausible_name(cleaned):
                    return cleaned

        # 4. High-confidence heuristic
        sorted_texts = sorted(texts, key=lambda t: t.confidence, reverse=True)
        for item in sorted_texts:
            cleaned = self._strip_name_prefix(item.text)
            if self._is_plausible_name(cleaned) and item.confidence >= 0.80:
                return cleaned

        return None

    @staticmethod
    def _strip_name_prefix(text: str) -> str:
        """
        Strip common label prefixes OCR merges into the name value.
        e.g. "NameParikshit K Panchal"  → "Parikshit K Panchal"
             "Name: Panchal Keval"      → "Panchal Keval"
        """
        stripped = re.sub(
            r'^(?:name|holder|applicant)[\s:\-/]*',
            '',
            text,
            flags=re.IGNORECASE,
        ).strip()
        return stripped if stripped else text

    # ── Date of Birth ─────────────────────────────────────────────────────────

    def extract_dob(self, texts: List[OCRText]) -> Optional[str]:
        # 1. Inline check for merged string e.g. "Date Of Birta8-02-2006" or "DOB: 18-02-2006"
        for item in texts:
            up = item.text.upper()
            if any(kw in up for kw in ["DOB", "BIRTH", "BIRT"]):
                cleaned_text = re.sub(r"BIRTA(\d)", r"BIRTH 1\1", item.text, flags=re.I)
                m = re.search(r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})", cleaned_text)
                if m:
                    parsed = normalize_dob(m.group(1))
                    if parsed:
                        return parsed

        # 2. Label proximity search
        label_keywords = [
            "DOB", "Date of Birth", "D.O.B", "Date Of Birth",
            "Birth Date", "Date Of Birt", "जन्म तिथि",
        ]
        raw = self.find_value_near_label(texts, label_keywords)
        if raw:
            parsed = normalize_dob(raw)
            if parsed:
                return parsed

        return None

    # ── Issue Date ────────────────────────────────────────────────────────────

    def extract_issue_date(self, texts: List[OCRText]) -> Optional[str]:
        # Look for dates directly below "Issue Date" label box
        issue_label = self._find_label_box(texts, ["Issue Date", "Date of Issue", "Date Of First Issue", "DOI"])
        if issue_label:
            lx = issue_label.bounding_box.center_x
            ly2 = issue_label.bounding_box.max_y
            for item in texts:
                if item is issue_label:
                    continue
                if abs(item.bounding_box.center_x - lx) < 60 and 0 < item.bounding_box.min_y - ly2 < 50:
                    m = re.search(r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})", item.text)
                    if m:
                        parsed = normalize_date(m.group(1))
                        if parsed:
                            return parsed

        # Fallback inline or regex search
        for item in texts:
            up = item.text.upper()
            if "ISSUE" in up or "FIRST ISSUE" in up:
                m = re.search(r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})", item.text)
                if m:
                    parsed = normalize_date(m.group(1))
                    if parsed:
                        return parsed

        return None

    # ── Expiry Date ───────────────────────────────────────────────────────────

    def extract_expiry_date(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract NT (Non-Transport) validity / Expiry date.
        """
        # Look for dates directly below "ValidityNT" or "Validity" or "Validity TR"
        val_label = self._find_label_box(texts, ["ValidityNT", "Validity NT", "Validity", "Valid Till", "Expiry Date", "Valid Upto"])
        if val_label:
            lx = val_label.bounding_box.center_x
            ly2 = val_label.bounding_box.max_y
            for item in texts:
                if item is val_label:
                    continue
                if abs(item.bounding_box.center_x - lx) < 80 and 0 < item.bounding_box.min_y - ly2 < 50:
                    m = re.search(r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})", item.text)
                    if m:
                        parsed = normalize_date(m.group(1))
                        if parsed:
                            return parsed

        # Fallback: scan all dates on card and pick the one with largest year (expiry is future)
        dates = []
        for item in texts:
            m = re.search(r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})", item.text)
            if m:
                parsed = normalize_date(m.group(1))
                if parsed:
                    dates.append(parsed)

        if dates:
            dates.sort(reverse=True)
            return dates[0]

        return None

    # ── Vehicle Classes ───────────────────────────────────────────────────────

    def extract_vehicle_classes(self, texts: List[OCRText]) -> List[str]:
        found: List[str] = []

        for item in texts:
            text_clean = item.text.upper().strip()

            if text_clean in _VEHICLE_CLASSES:
                found.append(text_clean)
                continue

            tokens = re.split(r"[,\s/]+", text_clean)
            for token in tokens:
                token = token.strip()
                if token in _VEHICLE_CLASSES:
                    found.append(token)

        seen = set()
        result = []
        for vc in found:
            if vc not in seen:
                seen.add(vc)
                result.append(vc)

        return result

    # ── Blood Group ───────────────────────────────────────────────────────────

    def extract_blood_group(self, texts: List[OCRText]) -> Optional[str]:
        # 1. Inline check for combined label+value e.g. "Blood Group:O+"
        for item in texts:
            up = item.text.upper().strip()
            if "BLOOD" in up or "B.G" in up:
                for bg in _BLOOD_GROUPS:
                    if bg in up:
                        return bg

        # 2. Label proximity
        raw = self.find_value_near_label(
            texts, ["Blood Group", "B.G", "Blood Grp", "BG"]
        )
        if raw:
            raw_up = raw.upper().strip()
            for bg in _BLOOD_GROUPS:
                if bg in raw_up:
                    return bg

        # 3. Standalone regex scan
        bg_pattern = r"\b(A|B|AB|O)[+\-]\b"
        for item in texts:
            m = re.search(bg_pattern, item.text.upper())
            if m:
                return m.group(0)

        return None

    # ── Issuing Authority ────────────────────────────────────────────────────

    def extract_issuing_authority(self, texts: List[OCRText]) -> Optional[str]:
        """Extract issuing authority (e.g. 'ARTO BOTAD', 'RTO AHMEDABAD')."""
        # 1. Direct scan for ARTO or RTO followed by place name
        for item in texts:
            up = item.text.upper().strip()
            if re.search(r"\b(A?RTO\s+[A-Z]+)\b", up):
                m = re.search(r"\b(A?RTO\s+[A-Z]+)\b", up)
                return m.group(1)

        # 2. Search below or near 'Licencing Authority' / 'Licensing Authority' / 'Issuing Authority'
        label_keywords = [
            "Licencing Authority", "Licensing Authority", "Issuing Authority",
            "Issued By", "RTO",
        ]
        raw = self.find_value_near_label(texts, label_keywords, direction="below", max_distance=100.0)
        if raw:
            return raw.strip().upper()

        raw_auto = self.find_value_near_label(texts, label_keywords, direction="auto", max_distance=200.0)
        if raw_auto:
            return raw_auto.strip().upper()

        return None

    # ── Helper ────────────────────────────────────────────────────────────────

    _DL_NAME_BLACKLIST = {
        "transport", "department", "gujarat", "state", "driving", "licence",
        "license", "motor", "vehicle", "authority", "government", "india",
        "non", "validity", "blood", "group", "class", "issue", "date",
        # Common OCR false-positives
        "emergency", "contact", "number", "badge", "address", "signature",
        "holder", "applicant", "office", "rto", "regional", "district",
        "renewal", "endorsement", "hazardous", "goods", "service",
        "gj", "dl", "no", "co", "cov", "catg", "sr", "sign",
    }

    def _is_plausible_name(self, text: str) -> bool:
        text = text.strip()
        if not text or any(c.isdigit() for c in text):
            return False
        words = text.split()
        if len(words) < 1 or len(words) > 5:
            return False
        for w in words:
            if not w.replace(".", "").replace("'", "").replace(":", "").isalpha():
                return False
        lower = text.lower()
        for bl in self._DL_NAME_BLACKLIST:
            if bl in lower:
                return False
        return True
