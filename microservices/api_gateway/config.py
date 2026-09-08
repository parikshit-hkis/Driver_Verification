"""
Configuration for API Gateway & Orchestration Service
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class GatewayConfig:
    PORT: int = int(os.getenv("GATEWAY_PORT", "8000"))
    HOST: str = os.getenv("GATEWAY_HOST", "0.0.0.0")

    # Downstream Microservices URLs
    OCR_SERVICE_URL: str = os.getenv("OCR_SERVICE_URL", "http://127.0.0.1:8001")
    AADHAAR_SERVICE_URL: str = os.getenv("AADHAAR_SERVICE_URL", "http://127.0.0.1:8002")
    DL_SERVICE_URL: str = os.getenv("DL_SERVICE_URL", "http://127.0.0.1:8003")
    PAN_SERVICE_URL: str = os.getenv("PAN_SERVICE_URL", "http://127.0.0.1:8004")
    RC_SERVICE_URL: str = os.getenv("RC_SERVICE_URL", "http://127.0.0.1:8005")
    VALIDATOR_SERVICE_URL: str = os.getenv("VALIDATOR_SERVICE_URL", "http://127.0.0.1:8006")

    # Persistence Paths
    EXTRACTION_OUTPUT_DIR: Path = ROOT_DIR / os.getenv("EXTRACTION_OUTPUT_DIR", "result/extr_result")
    VALIDATION_OUTPUT_DIR: Path = ROOT_DIR / os.getenv("VALIDATION_OUTPUT_DIR", "result/vldt_result")


gateway_config = GatewayConfig()
