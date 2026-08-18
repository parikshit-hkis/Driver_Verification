"""
Configuration for Driving Licence Extractor Microservice
"""

import os
import re
from typing import Set, List
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class DrivingLicenceConfig:
    PORT: int = int(os.getenv("DL_PORT", "8003"))
    HOST: str = os.getenv("DL_HOST", "0.0.0.0")
    OCR_SERVICE_URL: str = os.getenv("OCR_SERVICE_URL", "http://127.0.0.1:8001")

    MIN_DRIVER_AGE: int = int(os.getenv("DL_MIN_DRIVER_AGE", "16"))

    DL_REGEX = re.compile(
        r"\b([A-Z]{2}\s*[-]?\s*\d{2}[A-Z0-9]?\s*[-]?\s*\d{4}\s*[-]?\s*\d{7})\b",
        re.IGNORECASE,
    )

    VEHICLE_CLASSES: Set[str] = {
        "MCWG", "MCWO", "MCWOG", "LMV", "LMY", "LMV-NT", "LMV-TR", "LMV-CAB", "LMVCAB",
        "HMV", "HPMV", "HGMV", "MGV", "HTV", "TRANS", "TRANSPORT", "AGRTLR",
        "3W-NT", "3W-TR", "3WNT", "3WTR", "3W-CAB", "3WCAB",
        "FVG", "ADAPTED", "INVCR", "PSV-BUS", "PSVBUS", "TRACTOR", "TRCTOR", "LDRXCV",
    }

    ISSUE_KEYWORDS: List[str] = [
        "DATE OF ISSUE", "ISSUE DATE", "DATE OF FIRST ISSUE", "DATE OF 1ST ISSUE",
        "FIRST ISSUE DATE", "FIRST ISSUE", "DOI",
    ]

    EXPIRY_KEYWORDS: List[str] = [
        "VALIDITY", "VALIDITY UPTO", "VALID UPTO", "VALID TILL", "VALID UNTIL",
        "VALID TO", "EXPIRY DATE", "EXPIRY", "EXPIRATION DATE", "Licence Validity", "Issue DateValidity(NT)",
    ]

    DOB_KEYWORDS: List[str] = [
        "DATE OF BIRTH", "BIRTH DATE", "DATE OF BIRT", "DOB", "D.O.B"
    ]

    NAME_BLACKLIST: Set[str] = {
        "UNION", "INDIAN", "DRIVING", "LICENCE", "LICENSE", "GOVERNMENT", "GOVT",
        "STATE", "TRANSPORT", "DEPARTMENT", "AUTHORITY", "REGISTERING", "ISSUING",
        "DATE", "ISSUE", "VALIDITY", "EXPIRE", "EXPIRY", "BIRTH", "BLOOD", "GROUP",
        "ORGAN", "DONOR", "ADDRESS", "FORM", "RULE", "CLASS", "VEHICLE", "CATEGORY",
        "CODE", "BADGE", "NUMBER", "EMERGENCY", "CONTACT", "SIGNATURE", "HOLDER",
        "MVSD", "UP66", "UTTAR", "PRADESH", "GUJARAT", "MAHARASHTRA", "RAJASTHAN",
        "FIRST", "DATE OF FIRST ISSUE", "DATE OF ISSUE", "FIRST ISSUE", "ISSUE DATE",
        "OFFICER", "AHMEDABAD", "RTO", "AHMEDABAD RTO", "REGISTERING AUTHORITY",
        "ISSUING AUTHORITY", "HOLDER'S SIGNATURE", "HOLDER SIGNATURE", "'S SIGNATURE",
    }


dl_config = DrivingLicenceConfig()
