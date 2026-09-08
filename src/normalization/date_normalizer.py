import re
from typing import Optional
from datetime import datetime

class DateNormalizer:
    """
    Standardizes varied date formats from OCR text to ISO-8601 (YYYY-MM-DD)
    or Year format (YYYY).
    """
    DATE_FORMATS = [
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d",
        "%d %b %Y", "%d %B %Y"
    ]

    YEAR_REGEX = re.compile(r"^\b(19\d\d|20\d\d)\b$")

    def normalize(self, raw_date: Optional[str]) -> Optional[str]:
        if not raw_date:
            return None

        clean_str = re.sub(r"[^\w/.-]", " ", raw_date.strip()).strip()

        # If it's just a 4-digit year
        if self.YEAR_REGEX.match(clean_str):
            return clean_str

        # Try parsing standard date formats
        for fmt in self.DATE_FORMATS:
            try:
                dt = datetime.strptime(clean_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return clean_str

date_normalizer = DateNormalizer()
