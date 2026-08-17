"""
Driver Document Verification System — Microservices API Server
==============================================================
FastAPI Server aggregating OCR, Domain Extractors, Identity Cross-Validator,
and Master Gateway endpoints with interactive OpenAPI Swagger UI at /docs.
"""

import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# Ensure root directory is in sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1.gateway_router import router as gateway_router
from app.api.v1.ocr_router import router as ocr_router
from app.api.v1.aadhaar_router import router as aadhaar_router
from app.api.v1.dl_router import router as dl_router
from app.api.v1.pan_router import router as pan_router
from app.api.v1.rc_router import router as rc_router
from app.api.v1.validator_router import router as validator_router
from app.ocr.config import ocr_config

# Initialize FastAPI App
app = FastAPI(
    title="Driver Document Verification System — Microservices API",
    description="""
    ## Automated KYC & Identity Verification Microservices Suite for Ride-Hailing Platforms
    
    ### Available Services:
    * **Gateway Service**: End-to-end multi-document verification pipeline (`/api/v1/driver/verify`)
    * **OCR Engine Service**: High-accuracy PP-OCRv4 neural inference (`/api/v1/ocr/extract`)
    * **Aadhaar Extractor Service**: Aadhaar UID, Name, DOB, Gender extraction (`/api/v1/aadhaar/extract`)
    * **Driving Licence Service**: Sarathi DL, semantic date resolution, vehicle classes (`/api/v1/dl/extract`)
    * **PAN Card Service**: Permanent Account Number & Father name extraction (`/api/v1/pan/extract`)
    * **RC Service**: Registration Certificate & confidence metrics (`/api/v1/rc/extract`)
    * **Identity Cross-Validator**: Pairwise fuzzy Name & exact DOB matching (`/api/v1/validate/cross-verify`)
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Microservice Routers
app.include_router(gateway_router, prefix="/api/v1")
app.include_router(ocr_router, prefix="/api/v1")
app.include_router(aadhaar_router, prefix="/api/v1")
app.include_router(dl_router, prefix="/api/v1")
app.include_router(pan_router, prefix="/api/v1")
app.include_router(rc_router, prefix="/api/v1")
app.include_router(validator_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to interactive Swagger UI documentation."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["System Health"], summary="Health check endpoint")
async def health_check():
    """Returns system status, GPU availability, and model configurations."""
    return {
        "status": "HEALTHY",
        "version": "2.0.0",
        "ocr_engine": {
            "use_gpu": ocr_config.USE_GPU,
            "min_confidence": ocr_config.MIN_CONFIDENCE,
            "lang": ocr_config.LANG,
            "det_model": ocr_config.DET_MODEL_DIR,
            "rec_model": ocr_config.REC_MODEL_DIR,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.server:app", host="127.0.0.1", port=8000, reload=True)
