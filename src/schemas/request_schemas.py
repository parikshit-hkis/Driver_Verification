from typing import List, Optional
from pydantic import BaseModel, Field

class DriverVerificationRequest(BaseModel):
    driver_id: str = Field(..., min_length=1, description="Unique identifier for the driver")
    mobile_number: str = Field(..., pattern=r"^[0-9]{10}$", description="10-digit mobile number, used as ZIP password")
    vehicle_class: str = Field(..., min_length=1, description="Requested vehicle class, e.g. '2 wheeler', 'car'")

    aadhaar_zip_url: Optional[str] = Field(None, description="HTTPS URL to password-protected Aadhaar ZIP")
    licence_zip_url: Optional[str] = Field(None, description="HTTPS URL to password-protected Driving Licence ZIP")
    pan_zip_url: Optional[str] = Field(None, description="HTTPS URL to password-protected PAN ZIP")
    rc_zip_url: Optional[str] = Field(None, description="HTTPS URL to password-protected RC ZIP")

class BatchDriverVerificationRequest(BaseModel):
    drivers: List[DriverVerificationRequest] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Array of driver verification requests to process simultaneously (max 50 per batch)"
    )
