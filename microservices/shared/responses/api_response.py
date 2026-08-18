"""
Standardized API Response Envelopes and Error Wrappers
"""

from typing import Generic, TypeVar, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime

T = TypeVar("T")


class ApiError(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    status: str = "SUCCESS"  # "SUCCESS", "PARTIAL", "FAILED"
    data: Optional[T] = None
    error: Optional[ApiError] = None
    meta: Dict[str, Any] = Field(default_factory=lambda: {
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })
