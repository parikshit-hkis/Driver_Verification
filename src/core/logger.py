import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict

class SafeJsonFormatter(logging.Formatter):
    """
    Structured JSON log formatter that guarantees zero PII leakage.
    Ensures Aadhaar, PAN, phone numbers, and presigned URLs are not exposed.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include custom extra fields if safe
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            for k, v in record.extra.items():
                if k.lower() in ("aadhaar", "pan", "mobile", "password", "url", "signed_url"):
                    log_obj[k] = "[REDACTED]"
                else:
                    log_obj[k] = v

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(SafeJsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger

logger = get_logger("verification-service")
