from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

class MatchResult(BaseModel):
    match: bool
    score: float = Field(..., description="Match confidence score (0 to 100)")
    details: Optional[str] = None

class VehicleVerificationResult(BaseModel):
    provided_class: str
    rc_class: Optional[str] = None
    normalized_provided_class: str
    normalized_rc_class: Optional[str] = None
    match: bool

class AadhaarDocumentStatus(BaseModel):
    processed: bool
    name: Optional[str] = None
    dob: Optional[str] = None

class PanDocumentStatus(BaseModel):
    processed: bool
    name: Optional[str] = None
    father_name: Optional[str] = None
    dob: Optional[str] = None

class LicenceDocumentStatus(BaseModel):
    processed: bool
    name: Optional[str] = None
    issue_date: Optional[str] = None
    validity: Optional[str] = None
    vehicle_classes: List[str] = Field(default_factory=list)

class RcDocumentStatus(BaseModel):
    processed: bool
    name: Optional[str] = None
    vehicle_class: Optional[str] = None
    date_of_registration: Optional[str] = None
    registration_validity: Optional[str] = None

# Backward-compatibility alias
DocumentItemStatus = Any

class DriverVerificationResponse(BaseModel):
    driver_id: str
    status: Literal["VERIFIED", "REJECTED", "ERROR"]
    documents: Dict[str, Any] = Field(default_factory=dict)
    name_verification: Dict[str, MatchResult] = Field(default_factory=dict)
    vehicle_verification: Optional[VehicleVerificationResult] = None
    rejection_reasons: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None

class BatchDriverVerificationResponse(BaseModel):
    total_count: int
    verified_count: int
    rejected_count: int
    error_count: int
    processing_time_ms: float
    results: List[DriverVerificationResponse] = Field(default_factory=list)
