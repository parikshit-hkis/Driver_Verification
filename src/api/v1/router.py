from fastapi import APIRouter
from src.api.v1.endpoints import verification, health

api_v1_router = APIRouter()

api_v1_router.include_router(verification.router)
api_v1_router.include_router(health.router)
