"""
Identity Cross-Validator Microservice (Port 8006)
==================================================
Performs pairwise fuzzy matching of Name and exact DOB consistency checks across documents.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import uvicorn

from microservices.validator_service.config import validator_config
from microservices.validator_service.validator.cross_validator import IdentityCrossValidator
from microservices.shared.responses import ApiResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s")
logger = logging.getLogger("validator_service")

_validator = IdentityCrossValidator()

app = FastAPI(
    title="Identity Cross-Validator Microservice",
    description="Cross-verifies holder Full Name and Date of Birth across Aadhaar, PAN, and DL documents using RapidFuzz Token Sort Ratio and strict DOB matching.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["System Health"])
async def health_check():
    return {
        "service": "validator_service",
        "status": "HEALTHY",
        "port": validator_config.PORT,
        "name_match_threshold": validator_config.NAME_MATCH_THRESHOLD,
        "name_review_threshold": validator_config.NAME_REVIEW_THRESHOLD,
    }


@app.post("/cross-verify", summary="Cross-verify identity across extracted document payloads")
async def cross_verify(
    payload: Dict[str, Any] = Body(
        ...,
        description="Driver extraction JSON payload containing documents map",
        example={
            "driver_id": "DRIVER_001",
            "documents": {
                "aadhaar": {"data": {"full_name": "PATEL JAY DHANSUKHBHAI", "date_of_birth": "1995-11-20"}},
                "licence": {"data": {"full_name": "PATEL JAY DHANSUKHBHAI", "date_of_birth": "1995-11-20"}},
                "pan": {"data": {"full_name": "PATEL JAY DHANSUKHBHAI", "date_of_birth": "1995-11-20"}}
            }
        }
    )
):
    try:
        result = _validator.validate_driver_json(payload)
        return ApiResponse(
            success=True,
            status="SUCCESS",
            data=result.to_dict(),
        )
    except Exception as e:
        logger.error(f"Cross-verification error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cross-validation failed: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("microservices.validator_service.main:app", host=validator_config.HOST, port=validator_config.PORT, reload=True)
