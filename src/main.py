import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.logger import logger
from src.core.exceptions import VerificationServiceException
from src.api.v1.router import api_v1_router
from src.api.v1.endpoints.health import router as health_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode")
    os.makedirs(settings.TEMP_DIR, exist_ok=True)
    yield
    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}")

app = FastAPI(
    title="Driver Document Verification Microservice",
    description="Autonomous microservice for OCR extraction and cross-verification of driver documents",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handlers
@app.exception_handler(VerificationServiceException)
async def domain_exception_handler(request: Request, exc: VerificationServiceException):
    logger.error(f"Domain error: {exc.message}", extra={"error_code": exc.error_code})
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "status": "ERROR",
            "error_code": exc.error_code,
            "message": exc.message
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "ERROR",
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred."
        }
    )

# Direct root-level probes for container orchestrators (Kubernetes / ECS)
app.include_router(health_router)

# Versioned API routes
app.include_router(api_v1_router, prefix="/api/v1")
