"""
RC Extractor Configuration
===========================
Domain configuration for Vehicle Registration Certificate (RC) extraction,
regex patterns, canonical labels, and JSON config paths.
"""

import os
import re
from pathlib import Path
from typing import Set, List, Dict
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[3]


def _get_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default


class RCConfig:
    """RC Extraction Domain Settings."""

    FUZZY_MATCH_THRESHOLD: float = _get_float("RC_FUZZY_MATCH_THRESHOLD", 85.0)

    RC_CONFIG_PATH: Path = ROOT_DIR / "app" / "config" / "rc_config.json"
    KNOWN_MANUFACTURERS_PATH: Path = ROOT_DIR / "app" / "config" / "known_manufacturers.json"

    # All-India RC number pattern
    RC_REGEX = re.compile(
        r"\b([A-Z]{2}[\s\-]?\d{1,2}[\s\-]?[A-Z]{1,3}[\s\-]?\d{4}|\d{2}[\s\-]?BH[\s\-]?\d{4}[\s\-]?[A-Z]{1,2})\b",
        re.IGNORECASE,
    )

    # Patterns indicating relation markers attached to owner names
    RELATION_PATTERN = re.compile(
        r"\b(S/O|D/O|W/O|C/O|SO|DO|WO|CO|SON\s+OF|DAUGHTER\s+OF|WIFE\s+OF|CARE\s+OF)\b",
        re.IGNORECASE,
    )

    # Validity span pattern e.g., "From : 15/06/2018 To : 14/06/2033"
    VALIDITY_SPAN_REGEX = re.compile(
        r"(?:FROM|FRM)[\s:]*([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{2,4})[\s\w:]*(?:TO|UNTIL)[\s:]*([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{2,4})",
        re.IGNORECASE,
    )

    # Canonical structural labels for RapidFuzz layout recognition
    CANONICAL_RC_LABELS: List[str] = [
        "Regn No", "Reg No", "Registration No", "Regn Date", "Registration Date", "Date of Regn",
        "Owner Name", "Name of Owner", "Son/Wife/Daughter of", "Father Name", "Address",
        "Chassis No", "Chassis Number", "Engine No", "Engine Number", "Maker", "Maker Name",
        "Manufacturer", "Model", "Model Name", "Vehicle Class", "Class of Vehicle", "Body Type",
        "Type of Body", "Fuel", "Fuel Type", "Seating Cap", "Seating Capacity", "Standing Cap",
        "Cubic Cap", "Cubic Capacity", "Wheelbase", "Unladen Wt", "Gross Veh Wt", "GVW",
        "Fitness Upto", "Fitness Valid Upto", "Tax Upto", "Insurance Upto", "PUCC Upto",
        "Regn Validity", "Registration Validity", "Valid Upto", "Issuing Authority", "Registering Authority",
        "Financier", "Hypothecated To", "Color", "Colour", "Cylinders", "No of Cyl",
    ]

    EXPECTED_FIELD_SIDE: Dict[str, str] = {
        "registration_number": "front",
        "date_of_registration": "front",
        "owner_name": "front",
        "chassis_number": "front",
        "engine_number": "front",
        "vehicle_type": "front",
        "manufacturer": "back",
        "model": "back",
        "fuel_type": "back",
        "registration_validity": "back",
        "fitness_validity": "back",
        "insurance_validity": "back",
        "tax_validity": "back",
        "issuing_rto": "front",
    }


# Service Singleton
rc_config = RCConfig()
