import re
from typing import Optional, Dict, List
from src.core.config import settings

class VehicleClassNormalizer:
    """
    Maps varied RC and user vehicle class terminology to canonical business classes
    (e.g., '2 wheeler', 'car', '3 wheeler', 'truck').
    """
    def __init__(self, mapping: Optional[Dict[str, List[str]]] = None):
        self.mapping = mapping or settings.VEHICLE_CLASS_MAPPING

    def normalize(self, raw_class: Optional[str]) -> Optional[str]:
        """
        Returns canonical vehicle class string or None if unrecognized.
        """
        if not raw_class:
            return None

        # Clean string: lowercase
        cleaned_raw = raw_class.lower().strip()
        cleaned_compact = re.sub(r"[\s-]+", " ", cleaned_raw)
        alphanumeric_input = re.sub(r"[^a-z0-9]", "", cleaned_raw)

        # Check if already canonical
        if cleaned_raw in self.mapping or cleaned_compact in self.mapping:
            return cleaned_compact if cleaned_compact in self.mapping else cleaned_raw

        # 1. Exact string match against aliases (both with spaces, hyphens, and stripped)
        for canonical, aliases in self.mapping.items():
            for alias in aliases:
                alias_lower = alias.lower().strip()
                alias_compact = re.sub(r"[\s-]+", " ", alias_lower)
                alias_alphanumeric = re.sub(r"[^a-z0-9]", "", alias_lower)

                if (cleaned_raw == alias_lower or 
                    cleaned_compact == alias_compact or 
                    alphanumeric_input == alias_alphanumeric):
                    return canonical

        # 2. Substring / token boundary match against aliases
        for canonical, aliases in self.mapping.items():
            for alias in aliases:
                alias_lower = alias.lower().strip()
                alias_compact = re.sub(r"[\s-]+", " ", alias_lower)
                pattern = r"(?:^|\b|\s)" + re.escape(alias_compact) + r"(?:$|\b|\s)"
                if re.search(pattern, cleaned_compact):
                    return canonical

        return None

vehicle_normalizer = VehicleClassNormalizer()
