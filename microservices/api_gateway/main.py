"""
Driver Document Verification System — Master API Gateway (Port 8000)
====================================================================
Edge API Gateway and orchestrator aggregating all microservices in the suite.
"""

import sys
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import uvicorn

from microservices.api_gateway.config import gateway_config
from microservices.api_gateway.routers.driver_router import router as driver_router
from microservices.api_gateway.routers.batch_router import router as batch_router
from microservices.api_gateway.routers.proxy_router import router as proxy_router
from microservices.api_gateway.middleware.timing_middleware import TimingAndTracingMiddleware
from microservices.api_gateway.clients.service_clients import ServiceClients

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s")
logger = logging.getLogger("api_gateway")

_clients = ServiceClients()

app = FastAPI(
    title="Driver Document Verification — API Gateway",
    description="""
    ## True Microservices Suite for Driver KYC & Document Extraction
    
    ### System Microservices Topology:
    * **Gateway Service** (`Port 8000`): Master entrypoint, asynchronous multi-service orchestration & historical records.
    * **OCR Engine Service** (`Port 8001`): Dedicated GPU-accelerated PP-OCRv4 & OpenCV preprocessor.
    * **Aadhaar Extractor Service** (`Port 8002`): Aadhaar UID, care-of, DOB, gender & address parsing.
    * **Driving Licence Service** (`Port 8003`): Sarathi DL format, validity dates & vehicle categories.
    * **PAN Card Service** (`Port 8004`): Permanent Account Number, father's name & DOB extraction.
    * **RC Service** (`Port 8005`): Vehicle Registration Certificate parsing & confidence scoring.
    * **Identity Cross-Validator Service** (`Port 8006`): Pairwise Fuzzy Name & Exact DOB matching.
    """,
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Attach Middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TimingAndTracingMiddleware)

# Register API Routes
app.include_router(driver_router, prefix="/api/v1")
app.include_router(batch_router, prefix="/api/v1")
app.include_router(proxy_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["System Health"], summary="Cluster-wide microservice health aggregation")
async def cluster_health():
    """Aggregates and reports the live health status of all 6 downstream microservices."""
    health_report = await _clients.check_all_services_health()
    return {
        "gateway": "HEALTHY",
        "version": "2.0.0",
        "cluster": health_report,
    }


if __name__ == "__main__":
    uvicorn.run("microservices.api_gateway.main:app", host=gateway_config.HOST, port=gateway_config.PORT, reload=True)
