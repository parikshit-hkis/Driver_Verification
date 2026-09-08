from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional, Dict, List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Application
    APP_NAME: str = "document-verification-service"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Google Cloud Vision
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    GOOGLE_VISION_API_KEY: Optional[str] = None

    # Storage & Archive Limits
    MAX_ZIP_SIZE: int = Field(default=50 * 1024 * 1024, description="50 MB max zip size")
    MAX_EXTRACTED_SIZE: int = Field(default=100 * 1024 * 1024, description="100 MB max extracted size")
    MAX_FILES_PER_ZIP: int = 50
    TEMP_DIR: str = "/tmp/driver_verification"

    # Network Timeouts (seconds)
    DOWNLOAD_TIMEOUT: int = 30
    VISION_TIMEOUT: int = 30

    # Batch & Concurrency Configuration
    MAX_BATCH_SIZE: int = 50
    MAX_CONCURRENT_WORKERS: int = 5

    # Verification Match Thresholds
    NAME_MATCH_THRESHOLD: int = 95
    NAME_FUZZY_REVIEW_THRESHOLD: int = 85

    # Vehicle Class Canonical Mapping
    VEHICLE_CLASS_MAPPING: Dict[str, List[str]] = {
        "2 wheeler": [
            "motor cycle",
            "motorcycle",
            "scooter",
            "m-cycle",
            "mcwg",
        ],
        "3 wheeler": [
            "three wheeler",
            "3 wheeler",
            "auto",
            "e-rickshaw",
            "erickshaw",
            "autorickshaw",
        ],
        "car": [
            "motor car",
            "motorcar",
            "car",
            "lmv",
            "light motor vehicle",
        ],
        "truck": [
            "truck",
            "hgv",
            "lgv",
            "heavy goods vehicle",
            "goods carrier",
            "good carrier",
            "goods vehicle",
        ],
    }

settings = Settings()
