from typing import Optional, List, Literal
from pydantic import BaseModel, Field

class OCRBlock(BaseModel):
    text: str
    confidence: Optional[float] = None
    bounding_box: Optional[List[List[int]]] = None

class OCRResult(BaseModel):
    raw_text: str
    blocks: List[OCRBlock] = Field(default_factory=list)
    confidence: Optional[float] = None

class DocumentFile(BaseModel):
    source: str  # e.g. "aadhaar_zip", "licence_zip"
    file_path: str
    page_number: int = 1
    document_type: str = "unknown"

class AadhaarData(BaseModel):
    document_type: Literal["aadhaar"] = "aadhaar"
    name: Optional[str] = None
    date_of_birth: Optional[str] = None
    aadhaar_number: Optional[str] = None

class PanData(BaseModel):
    document_type: Literal["pan"] = "pan"
    name: Optional[str] = None
    father_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    pan_number: Optional[str] = None

class LicenceData(BaseModel):
    document_type: Literal["licence"] = "licence"
    name: Optional[str] = None
    issue_date: Optional[str] = None
    validity: Optional[str] = None
    licence_number: Optional[str] = None
    vehicle_classes: List[str] = Field(default_factory=list)

class RcData(BaseModel):
    document_type: Literal["rc"] = "rc"
    owner_name: Optional[str] = None
    vehicle_class: Optional[str] = None
    date_of_registration: Optional[str] = None
    registration_validity: Optional[str] = None
    registration_number: Optional[str] = None

