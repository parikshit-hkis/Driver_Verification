import os
from fastapi import APIRouter
from src.core.config import settings

router = APIRouter(tags=["Health & Probes"])

@router.get("/health", summary="Liveness Probe")
async def liveness_probe():
    """Returns 200 when service process is alive."""
    return {"status": "healthy"}

@router.get("/ready", summary="Readiness Probe")
async def readiness_probe():
    """Checks credentials presence and filesystem access without paid Vision calls."""
    credentials_configured = bool(settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS))
    
    # Check temp directory access
    temp_dir_writable = True
    try:
        os.makedirs(settings.TEMP_DIR, exist_ok=True)
    except Exception:
        temp_dir_writable = False

    is_ready = temp_dir_writable

    return {
        "status": "ready" if is_ready else "not_ready",
        "storage": "ok" if temp_dir_writable else "error",
        "credentials_configured": credentials_configured,
        "environment": settings.APP_ENV
    }
