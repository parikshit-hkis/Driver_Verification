"""
Manufacturer Repository
=======================
DB / Config-backed repository for known vehicle manufacturers.
Provides soft-hint query capabilities without making manufacturers a strict whitelist.
"""

import json
import logging
from pathlib import Path
from typing import List, Set, Optional

logger = logging.getLogger(__name__)


class ManufacturerRepository:
    """Repository for known vehicle manufacturer names."""

    def __init__(self, data_path: Optional[Path] = None):
        if data_path is None:
            data_path = Path(__file__).resolve().parents[2] / "config" / "known_manufacturers.json"
        self._data_path = data_path
        self._known_manufacturers: Set[str] = set()
        self.reload()

    def reload(self) -> None:
        """Reload manufacturer data from persistent store/config."""
        if not self._data_path.exists():
            logger.warning(f"Manufacturer data path {self._data_path} not found.")
            return

        try:
            with open(self._data_path, "r", encoding="utf-8") as f:
                items = json.load(f)
                if isinstance(items, list):
                    self._known_manufacturers = {m.strip().upper() for m in items}
        except Exception as e:
            logger.error(f"Failed to load manufacturer repository from {self._data_path}: {e}")

    def is_known(self, candidate: str) -> bool:
        """Check if candidate text matches or contains any known manufacturer."""
        cand_up = candidate.strip().upper()
        if not cand_up:
            return False
        for mfr in self._known_manufacturers:
            if mfr in cand_up or cand_up in mfr:
                return True
        return False

    def get_known_match(self, candidate: str) -> Optional[str]:
        """Return matching known manufacturer string if present."""
        cand_up = candidate.strip().upper()
        for mfr in self._known_manufacturers:
            if mfr in cand_up:
                return mfr
        return None

    def get_all(self) -> List[str]:
        """Get list of all known manufacturers."""
        return sorted(list(self._known_manufacturers))
