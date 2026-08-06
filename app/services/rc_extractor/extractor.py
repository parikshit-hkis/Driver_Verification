"""
RC (Registration Certificate) Extractor
========================================
Extracts and normalizes:
  - Registration number (Gujarat GJ format)
  - Owner name
  - Vehicle class, type, fuel type, manufacturer, model
  - Chassis number, engine number
  - Date of registration, registration validity, fitness validity,
    insurance validity, tax validity

Gujarat RC Layout:
  RC Book (booklet) or Smart Card RC:
    Front: Registration No, Owner Name, Address, Vehicle Details
    Back:  Chassis No, Engine No, Fitness Upto, Insurance Upto, Tax Upto

Smart Card RC (common newer format):
  - All info on one side in a tabular layout
  - Registration No top right
  - Owner Name prominent
  - Dates in a table at the bottom

OCR challenges handled:
  - Multi-line owner name (across 2 boxes)
  - "Regn. No." vs "Reg. No." vs "Registration No." label variations
  - Fitness Upto vs Fitness Valid Upto
  - "GJ 01 AB 1234" (spaced) vs "GJ01AB1234" (compact)
"""

import re
from typing import List, Optional

from app.models.ocr_models import OCRResult, OCRText
from app.services.base_extractor import BaseExtractor
from app.services.rc_extractor.models import RCData
from app.utils.normalizer import normalize_date, normalize_name, normalize_rc_number


# Gujarat RC number pattern — GJ + 2-digit RTO + 1-3 letters + 4 digits
_RC_REGEX = re.compile(
    r"\b(GJ[\s\-]?\d{2}[\s\-]?[A-Z]{1,3}[\s\-]?\d{4})\b",
    re.IGNORECASE,
)

# Chassis number: typically 17 chars (VIN standard) or shorter
_CHASSIS_REGEX = re.compile(r"\b([A-Z0-9]{6,17})\b")

# Engine number: shorter, variable format
_ENGINE_REGEX = re.compile(r"\b([A-Z0-9]{5,12})\b")

_FUEL_TYPES = {
    "PETROL": "PETROL",
    "DIESEL": "DIESEL",
    "CNG": "CNG",
    "LPG": "LPG",
    "ELECTRIC": "ELECTRIC",
    "EV": "ELECTRIC",
    "HYBRID": "HYBRID",
    "PETROL+CNG": "PETROL+CNG",
    "PETROL/CNG": "PETROL+CNG",
    "PETROL/LPG": "PETROL+LPG",
    "BS6": "BS6",   # Sometimes OCR captures emission norm instead of fuel type
}


class RCExtractor(BaseExtractor):
    """Extracts structured data from RC (Registration Certificate) OCR output."""

    def extract(self, ocr_result: OCRResult) -> RCData:
        texts = ocr_result.texts
        data = RCData()

        data.registration_number = self.extract_registration_number(texts)
        data.owner_name = self.extract_owner_name(texts)
        data.vehicle_class = self.extract_vehicle_class(texts)
        data.vehicle_type = self.extract_vehicle_type(texts)
        data.fuel_type = self.extract_fuel_type(texts)
        data.manufacturer = self.extract_manufacturer(texts)
        data.model = self.extract_model(texts)
        data.chassis_number = self.extract_chassis_number(texts)
        data.engine_number = self.extract_engine_number(texts)
        data.date_of_registration = self.extract_date_of_registration(texts)
        data.registration_validity = self.extract_registration_validity(texts)
        data.fitness_validity = self.extract_fitness_validity(texts)
        data.insurance_validity = self.extract_insurance_validity(texts)
        data.tax_validity = self.extract_tax_validity(texts)
        data.issuing_rto = self.extract_issuing_rto(texts)

        return data

    # ── Registration Number ───────────────────────────────────────────────────

    def extract_registration_number(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract Gujarat RC number: GJ-RR-XX-NNNN

        Handles:
          - "GJ 01 AB 1234" (space-separated)
          - "GJ-01-AB-1234" (hyphen)
          - "GJ01AB1234" (compact)
          - Mixed: "GJ01 AB 1234"
        """
        # 1. Label-proximity
        label_keywords = [
            "Regn. No", "Reg. No", "Registration No", "Registration Number",
            "Regn No", "Regd No", "Reg No", "Veh Reg No",
        ]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=400.0)
        if raw:
            normalized = normalize_rc_number(re.sub(r"[\s\-]", "", raw.upper()))
            if normalized:
                return normalized

        # 2. Regex across all text boxes
        for item in texts:
            m = _RC_REGEX.search(item.text)
            if m:
                return normalize_rc_number(m.group(1))

        # 3. Scan joined text
        full = " ".join(t.text.upper() for t in texts)
        m = _RC_REGEX.search(full)
        if m:
            return normalize_rc_number(m.group(1))

        return None

    # ── Owner Name ────────────────────────────────────────────────────────────

    def extract_owner_name(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract registered owner's name.

        Labels: "Name of Owner", "Owner Name", "Owner", "Registered Owner"
        """
        label_keywords = [
            "Name of Owner", "Owner Name", "Owner's Name", "Owner",
            "Registered Owner", "Regn Owner", "Vehicle Owner",
        ]

        candidate = self.find_value_near_label(
            texts, label_keywords, direction="auto", max_distance=400.0
        )
        if candidate and self._is_plausible_name(candidate):
            return candidate.upper()

        # Try below direction specifically (RC booklets often have name below label)
        candidate = self.find_value_near_label(
            texts, label_keywords, direction="below", max_distance=80.0
        )
        if candidate and self._is_plausible_name(candidate):
            return candidate.upper()

        return None

    # ── Vehicle Class ─────────────────────────────────────────────────────────

    def extract_vehicle_class(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract vehicle class code.
        Common Gujarat RC values: LMV-CAR, M-CYCLE/SCOOTER, HMV, MGV, etc.
        """
        label_keywords = [
            "Vehicle Class", "Class of Vehicle", "Veh Class",
            "Class", "Type of Vehicle",
        ]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=400.0)
        if raw:
            return raw.upper().strip()
        return None

    # ── Vehicle Type ─────────────────────────────────────────────────────────

    def extract_vehicle_type(self, texts: List[OCRText]) -> Optional[str]:
        """Extract vehicle type (MOTOR CAR, MOTORCYCLE, etc.)."""
        label_keywords = ["Vehicle Type", "Type of Veh", "Body Type", "Veh Type"]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=300.0)
        if raw:
            return raw.upper().strip()
        return None

    # ── Fuel Type ─────────────────────────────────────────────────────────────

    def extract_fuel_type(self, texts: List[OCRText]) -> Optional[str]:
        """Extract fuel type."""
        label_keywords = [
            "Fuel Type", "Fuel Used", "Fuel", "Type of Fuel",
        ]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=300.0)
        if raw:
            raw_up = raw.upper().strip()
            # Match known fuel types
            for key, val in _FUEL_TYPES.items():
                if key in raw_up:
                    return val
            return raw_up

        # Scan full text for fuel type keywords
        full = self.full_text(texts).upper()
        for key, val in _FUEL_TYPES.items():
            if key in full:
                return val

        return None

    # ── Manufacturer ─────────────────────────────────────────────────────────

    def extract_manufacturer(self, texts: List[OCRText]) -> Optional[str]:
        """Extract vehicle manufacturer / maker."""
        label_keywords = [
            "Maker", "Maker's Name", "Manufacturer", "Make",
            "Mfr Name", "Manufacturer Name",
        ]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=300.0)
        if raw:
            return raw.upper().strip()
        return None

    # ── Model ────────────────────────────────────────────────────────────────

    def extract_model(self, texts: List[OCRText]) -> Optional[str]:
        """Extract vehicle model name."""
        label_keywords = [
            "Model", "Model Name", "Vehicle Model", "Veh Model",
        ]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=300.0)
        if raw:
            return raw.upper().strip()
        return None

    # ── Chassis Number ────────────────────────────────────────────────────────

    def extract_chassis_number(self, texts: List[OCRText]) -> Optional[str]:
        """
        Extract chassis / VIN number (typically 17 alphanumeric chars).
        """
        label_keywords = [
            "Chassis No", "Chassis Number", "VIN", "Chassis/Engine No",
            "Chasis No",  # common OCR misspelling
        ]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=400.0)
        if raw:
            cleaned = re.sub(r"[\s\-]", "", raw.upper())
            if 5 <= len(cleaned) <= 20:
                return cleaned
        return None

    # ── Engine Number ─────────────────────────────────────────────────────────

    def extract_engine_number(self, texts: List[OCRText]) -> Optional[str]:
        """Extract engine number."""
        label_keywords = [
            "Engine No", "Engine Number", "Eng No",
        ]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=400.0)
        if raw:
            cleaned = re.sub(r"[\s\-]", "", raw.upper())
            if 4 <= len(cleaned) <= 20:
                return cleaned
        return None

    # ── Dates ─────────────────────────────────────────────────────────────────

    def extract_date_of_registration(self, texts: List[OCRText]) -> Optional[str]:
        label_keywords = [
            "Date of Reg", "Date of Registration", "Reg Date",
            "Regn Date", "Registration Date",
        ]
        raw = self.find_value_near_label(texts, label_keywords)
        return normalize_date(raw) if raw else None

    def extract_registration_validity(self, texts: List[OCRText]) -> Optional[str]:
        label_keywords = [
            "Regn Upto", "Registration Upto", "Reg Upto",
            "Registration Valid Upto", "Regn Valid Till",
            "Registration Validity",
        ]
        raw = self.find_value_near_label(texts, label_keywords)
        return normalize_date(raw) if raw else None

    def extract_fitness_validity(self, texts: List[OCRText]) -> Optional[str]:
        label_keywords = [
            "Fitness Upto", "Fitness Valid Upto", "Fitness Valid Till",
            "Fitness Validity", "FC Upto", "Fit Upto",
        ]
        raw = self.find_value_near_label(texts, label_keywords)
        return normalize_date(raw) if raw else None

    def extract_insurance_validity(self, texts: List[OCRText]) -> Optional[str]:
        label_keywords = [
            "Insurance Upto", "Insurance Valid Upto", "Ins Upto",
            "Insurance Validity", "Insurance Expiry",
        ]
        raw = self.find_value_near_label(texts, label_keywords)
        return normalize_date(raw) if raw else None

    def extract_tax_validity(self, texts: List[OCRText]) -> Optional[str]:
        label_keywords = [
            "Tax Upto", "Tax Valid Upto", "Tax Validity", "Road Tax Upto",
        ]
        raw = self.find_value_near_label(texts, label_keywords)
        return normalize_date(raw) if raw else None

    # ── Issuing RTO ───────────────────────────────────────────────────────────

    def extract_issuing_rto(self, texts: List[OCRText]) -> Optional[str]:
        """Extract issuing RTO office name."""
        label_keywords = [
            "Issuing Authority", "RTO", "Registering Authority",
            "Issued At", "Office",
        ]
        raw = self.find_value_near_label(texts, label_keywords, max_distance=400.0)
        if raw:
            return raw.upper().strip()

        # Scan for "RTO" followed by city name
        for item in texts:
            if "RTO" in item.text.upper():
                return item.text.upper().strip()

        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    _RC_NAME_BLACKLIST = {
        "registration", "certificate", "transport", "department",
        "government", "india", "gujarat", "vehicle", "owner", "name",
        "chassis", "engine", "fuel", "type", "class", "model",
    }

    def _is_plausible_name(self, text: str) -> bool:
        text = text.strip()
        if not text or any(c.isdigit() for c in text):
            return False
        words = text.split()
        if len(words) < 1 or len(words) > 6:
            return False
        for w in words:
            if not w.replace(".", "").replace("'", "").replace("-", "").isalpha():
                return False
        lower = text.lower()
        for bl in self._RC_NAME_BLACKLIST:
            if bl in lower:
                return False
        return True
