"""
Shared Data Models and DTOs for Driver Verification Microservices Suite
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass, field
from enum import Enum


class DocumentType(str, Enum):
    AADHAAR = "aadhaar"
    PAN = "pan"
    DRIVING_LICENCE = "driving_licence"
    RC = "rc"
    UNKNOWN = "unknown"


# ── OCR Models ────────────────────────────────────────────────────────────────

class Point(BaseModel):
    x: float
    y: float


class BoundingBox(BaseModel):
    points: List[Point]

    @property
    def min_x(self) -> float:
        return min(p.x for p in self.points)

    @property
    def max_x(self) -> float:
        return max(p.x for p in self.points)

    @property
    def min_y(self) -> float:
        return min(p.y for p in self.points)

    @property
    def max_y(self) -> float:
        return max(p.y for p in self.points)

    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) / 2.0

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2.0

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


class OCRText(BaseModel):
    text: str
    confidence: float
    bounding_box: BoundingBox


class OCRResult(BaseModel):
    full_text: str = ""
    texts: List[OCRText] = Field(default_factory=list)


@dataclass
class ImageQualityReport:
    """Detailed image quality assessment results."""
    blur_score: float = 0.0
    is_blurry: bool = False
    brightness: float = 0.0
    is_too_dark: bool = False
    is_too_bright: bool = False
    glare_percentage: float = 0.0
    has_glare: bool = False
    was_rotated: bool = False
    rotation_applied: int = 0
    skew_corrected: bool = False
    skew_angle: float = 0.0
    was_enhanced: bool = False
    original_width: int = 0
    original_height: int = 0
    warnings: list = field(default_factory=list)

    def is_acceptable(self) -> bool:
        return not (self.is_blurry and self.blur_score < 30.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blur_score": self.blur_score,
            "is_blurry": self.is_blurry,
            "brightness": self.brightness,
            "is_too_dark": self.is_too_dark,
            "is_too_bright": self.is_too_bright,
            "glare_percentage": self.glare_percentage,
            "has_glare": self.has_glare,
            "was_rotated": self.was_rotated,
            "rotation_applied": self.rotation_applied,
            "skew_corrected": self.skew_corrected,
            "skew_angle": self.skew_angle,
            "was_enhanced": self.was_enhanced,
            "warnings": self.warnings,
        }


# ── Domain Extractor Models ───────────────────────────────────────────────────

class AadhaarData(BaseModel):
    aadhaar_number: Optional[str] = None
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    field_diagnostics: Dict[str, str] = Field(default_factory=dict)


class DrivingLicenceData(BaseModel):
    licence_number: Optional[str] = None
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    vehicle_classes: List[str] = Field(default_factory=list)
    field_diagnostics: Dict[str, str] = Field(default_factory=dict)


class PanData(BaseModel):
    pan_number: Optional[str] = None
    full_name: Optional[str] = None
    father_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    field_diagnostics: Dict[str, str] = Field(default_factory=dict)


class RCData(BaseModel):
    registration_number: Optional[str] = None
    owner_name: Optional[str] = None
    vehicle_class: Optional[str] = None
    fuel_type: Optional[str] = None
    maker_model: Optional[str] = None
    engine_number: Optional[str] = None
    chassis_number: Optional[str] = None
    registration_date: Optional[str] = None
    fitness_expiry: Optional[str] = None
    confidence_scores: Dict[str, float] = Field(default_factory=dict)
    overall_confidence: float = 0.0
    field_diagnostics: Dict[str, str] = Field(default_factory=dict)


DocumentData = Union[AadhaarData, PanData, DrivingLicenceData, RCData, None]


# ── Cross-Validation Models ───────────────────────────────────────────────────

class NameMatchResult(BaseModel):
    doc1_key: str
    doc2_key: str
    doc1_name: str
    doc2_name: str
    similarity: float
    status: str  # "MATCH", "REVIEW", "MISMATCH", "MISSING"


class DOBMatchResult(BaseModel):
    doc1_key: str
    doc2_key: str
    doc1_dob: str
    doc2_dob: str
    status: str  # "MATCH", "MISMATCH", "MISSING"


class PairwiseValidationResult(BaseModel):
    name: NameMatchResult
    date_of_birth: DOBMatchResult
    status: str  # "MATCH", "REVIEW", "MISMATCH"


class CrossValidationResult(BaseModel):
    driver_id: str
    aadhaar_vs_pan: PairwiseValidationResult
    aadhaar_vs_licence: PairwiseValidationResult
    pan_vs_licence: PairwiseValidationResult
    overall_name_status: str  # "MATCHED", "REVIEW", "MISMATCH"
    overall_dob_status: str   # "MATCHED", "MISMATCH"
    overall_status: str       # "MATCHED", "REVIEW", "MISMATCH"

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# ── Consolidated Driver Verification Models ────────────────────────────────────

class DocumentExtractionResult(BaseModel):
    document_type: DocumentType
    data: Optional[Dict[str, Any]] = None
    front_quality: Optional[Dict[str, Any]] = None
    back_quality: Optional[Dict[str, Any]] = None
    status: str = "MISSING"  # "EXTRACTED", "PARTIAL", "MISSING", "FAILED"
    warning: Optional[str] = None


class DriverVerificationResult(BaseModel):
    driver_id: str
    documents: Dict[str, Optional[DocumentExtractionResult]] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
