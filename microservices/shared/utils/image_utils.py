"""
Image Reading and Preprocessing Helpers for Microservices
"""

from typing import Optional, Tuple
import numpy as np
import cv2
from fastapi import UploadFile


async def read_image_from_upload(upload_file: Optional[UploadFile]) -> Optional[np.ndarray]:
    """Read FastAPI UploadFile asynchronously and decode into OpenCV BGR numpy array."""
    if not upload_file:
        return None
    contents = await upload_file.read()
    if not contents:
        return None
    nparr = np.frombuffer(contents, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)


def decode_image_bytes(file_bytes: bytes) -> Optional[np.ndarray]:
    """Decode raw bytes into OpenCV BGR numpy array."""
    if not file_bytes:
        return None
    nparr = np.frombuffer(file_bytes, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)


def encode_image_to_bytes(img: np.ndarray, format: str = ".jpg") -> bytes:
    """Encode OpenCV image back to bytes for HTTP transmission."""
    success, buffer = cv2.imencode(format, img)
    if not success:
        raise ValueError("Failed to encode image to bytes")
    return buffer.tobytes()
