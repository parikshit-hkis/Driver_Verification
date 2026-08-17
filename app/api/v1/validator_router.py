"""
Identity Cross-Validation Microservice Router
=============================================
Provides cross-validation endpoints comparing Name and DOB across documents.
"""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Body

from app.services.identity_cross_validator.cross_validator import IdentityCrossValidator

router = APIRouter(prefix="/validate", tags=["Identity Cross-Validator"])

_validator = IdentityCrossValidator()


@router.post("/cross-verify", summary="Cross-verify identity across extracted documents")
async def cross_verify_identity(
    driver_data: Dict[str, Any] = Body(
        ...,
        description="Driver extraction JSON payload containing documents map",
        example={
            "driver_id": "DRIVER_001",
            "documents": {
                "aadhaar": {
                    "data": {
                        "full_name": "PATEL JAY DHANSUKHBHAI",
                        "date_of_birth": "1995-11-20"
                    }
                },
                "licence": {
                    "data": {
                        "full_name": "PATEL JAY DHANSUKHBHAI",
                        "date_of_birth": "1995-11-20"
                    }
                },
                "pan": {
                    "data": {
                        "full_name": "PATEL JAY DHANSUKHBHAI",
                        "date_of_birth": "1995-11-20"
                    }
                }
            }
        }
    )
):
    """
    Performs pairwise fuzzy matching of Name (token sort ratio) and exact DOB matching
    across Aadhaar, Driving Licence, and PAN documents.
    """
    try:
        result = _validator.validate_driver_json(driver_data)
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cross-validation failed: {str(e)}")
