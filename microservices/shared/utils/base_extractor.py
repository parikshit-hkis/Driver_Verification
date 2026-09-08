"""
Shared Base Extractor with Label Proximity & Spatial Helpers
"""

import re
from typing import Optional, List, Tuple
from microservices.shared.models import OCRText, OCRResult


class BaseExtractor:
    """Provides label-proximity text extraction helpers shared by all document extractors."""

    def find_value_near_label(
        self,
        texts: List[OCRText],
        label_keywords: List[str],
        *,
        direction: str = "auto",
        max_distance: float = 400.0,
        same_row_tolerance: float = 18.0,
        min_confidence: float = 0.0,
        skip_label_chars: bool = True,
    ) -> Optional[str]:
        label_box = self._find_label_box(texts, label_keywords)
        if label_box is None:
            return None

        lx1 = label_box.bounding_box.min_x
        lx2 = label_box.bounding_box.max_x
        ly1 = label_box.bounding_box.min_y
        ly2 = label_box.bounding_box.max_y
        lcy = (ly1 + ly2) / 2.0

        candidates: List[Tuple[float, OCRText]] = []

        for item in texts:
            if item is label_box or item.confidence < min_confidence:
                continue

            icx = item.bounding_box.center_x
            icy = item.bounding_box.center_y
            ix1 = item.bounding_box.min_x

            if icx < lx1 - 10:
                continue

            on_same_row = abs(icy - lcy) <= same_row_tolerance
            is_below = icy > ly2 - 5

            if direction == "right":
                if not on_same_row:
                    continue
                dist = max(0.0, ix1 - lx2)
            elif direction == "below":
                if not is_below:
                    continue
                dist = max(0.0, item.bounding_box.min_y - ly2)
            else:  # auto
                if on_same_row:
                    dist = max(0.0, ix1 - lx2)
                elif is_below:
                    dist = max(0.0, item.bounding_box.min_y - ly2) + 5
                else:
                    continue

            if dist <= max_distance:
                candidates.append((dist, item))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        value = candidates[0][1].text.strip()
        if skip_label_chars:
            value = re.sub(r"^[\s:;/\-–—]+", "", value).strip()

        return value if value else None

    def find_by_regex(self, texts: List[OCRText], pattern: str, flags: int = re.IGNORECASE) -> Optional[str]:
        for item in texts:
            m = re.search(pattern, item.text, flags)
            if m:
                return m.group().strip()
        return None

    def find_all_by_regex(self, texts: List[OCRText], pattern: str, flags: int = re.IGNORECASE) -> List[str]:
        results = []
        for item in texts:
            results.extend(re.findall(pattern, item.text, flags))
        return results

    def full_text(self, texts: List[OCRText]) -> str:
        return "\n".join(t.text for t in texts)

    def _find_label_box(self, texts: List[OCRText], keywords: List[str]) -> Optional[OCRText]:
        kw_upper = [k.upper() for k in keywords]
        for item in texts:
            t = item.text.upper().strip().rstrip(":").rstrip()
            for kw in kw_upper:
                kw_clean = kw.upper().rstrip(":").rstrip()
                if t == kw_clean or kw_clean in t:
                    return item
        return None
