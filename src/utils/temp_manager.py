import os
import shutil
import uuid
from typing import Optional
from src.core.config import settings
from src.core.logger import logger

class TempDirectoryContext:
    """
    Context manager that provides an isolated temporary directory for a driver verification session.
    Automatically purges all temporary files upon exiting context.
    """
    def __init__(self, driver_id: str, prefix: Optional[str] = None):
        self.driver_id = driver_id
        session_id = prefix or str(uuid.uuid4())[:8]
        # Sanitize driver_id to avoid path injection
        clean_driver_id = "".join(c for c in driver_id if c.isalnum() or c in ("-", "_"))
        self.dir_path = os.path.join(settings.TEMP_DIR, f"{session_id}_{clean_driver_id}")

    def __enter__(self) -> str:
        os.makedirs(self.dir_path, exist_ok=True)
        return self.dir_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def cleanup(self):
        """Recursively removes the isolated temporary directory."""
        if os.path.exists(self.dir_path):
            try:
                shutil.rmtree(self.dir_path, ignore_errors=True)
                logger.info("Cleaned up temporary directory", extra={"driver_id": self.driver_id})
            except Exception as e:
                logger.error(f"Failed to cleanup temp dir {self.dir_path}: {e}")
