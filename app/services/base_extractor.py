"""
Base Extractor
==============
Provides label-proximity text extraction helpers shared by all document
type extractors.

Label-Proximity Approach:
  Instead of running regex over a raw text blob, we use OCR bounding-box
  positions to locate a *label* (e.g. "DOB", "Name") and then find the
  nearest text box to its right or below. This is far more robust than
  regex-over-blob because:
    - Labels vary ("DOB" / "Date of Birth" / "D.O.B" / "जन्म तिथि")
    - Multiple similar patterns may appear (e.g. multiple dates)
    - Label position uniquely identifies the corresponding value
"""

import re
from typing import Optional, List, Tuple

from app.models.ocr_models import OCRText, OCRResult


class BaseExtractor:

    # ── Label-proximity search ─────────────────────────────────────────────

    def find_value_near_label(self,texts: List[OCRText],label_keywords: List[str],*,direction: str = "auto",
        max_distance: float = 400.0,
        same_row_tolerance: float = 18.0,
        min_confidence: float = 0.0,
        skip_label_chars: bool = True,
    ) -> Optional[str]:

        """Find the value text near a matching label on the document. """

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
            if item is label_box:
                continue
            if item.confidence < min_confidence:
                continue

            icx = item.bounding_box.center_x
            icy = item.bounding_box.center_y
            ix1 = item.bounding_box.min_x

            # Must be to the right or below — never to the left
            if icx < lx1 - 10:
                continue

            # Measure distance based on direction
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
                    dist = max(0.0, item.bounding_box.min_y - ly2) + 5  # slight below-penalty
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

    # def find_values_near_label(self,texts: List[OCRText],
    #     label_keywords: List[str],
    #     *,
    #     direction: str = "auto",
    #     max_distance: float = 400.0,
    #     same_row_tolerance: float = 18.0,
    #     top_n: int = 3,
    # ) -> List[str]:
    #     """
    #     Like find_value_near_label but returns multiple nearby values
    #     (useful for multi-value fields like vehicle classes on DL).
    #     """
    #     label_box = self._find_label_box(texts, label_keywords)
    #     if label_box is None:
    #         return []

    #     lx2 = label_box.bounding_box.max_x
    #     ly2 = label_box.bounding_box.max_y
    #     lcy = label_box.bounding_box.center_y

    #     candidates: List[Tuple[float, OCRText]] = []

    #     for item in texts:
    #         if item is label_box:
    #             continue

    #         icy = item.bounding_box.center_y
    #         ix1 = item.bounding_box.min_x

    #         on_same_row = abs(icy - lcy) <= same_row_tolerance
    #         is_below = icy > ly2 - 5

    #         if direction == "below":
    #             if not is_below:
    #                 continue
    #             dist = max(0.0, item.bounding_box.min_y - ly2)
    #         elif direction == "right":
    #             if not on_same_row:
    #                 continue
    #             dist = max(0.0, ix1 - lx2)
    #         else:
    #             if on_same_row:
    #                 dist = max(0.0, ix1 - lx2)
    #             elif is_below:
    #                 dist = max(0.0, item.bounding_box.min_y - ly2) + 5
    #             else:
    #                 continue

    #         if dist <= max_distance:
    #             candidates.append((dist, item))

    #     candidates.sort(key=lambda x: x[0])
    #     return [re.sub(r"^[\s:;/\-–—]+", "", c[1].text).strip() for c in candidates[:top_n]]

    # ── Full-text search helpers ───────────────────────────────────────────

    def find_by_regex(self, texts: List[OCRText], pattern: str, flags: int = re.IGNORECASE) -> Optional[str]:
        """Return the first regex match found across all OCR text lines."""
        for item in texts:
            m = re.search(pattern, item.text, flags)
            if m:
                return m.group().strip()
        return None

    def find_all_by_regex(self, texts: List[OCRText], pattern: str, flags: int = re.IGNORECASE) -> List[str]:
        """Return all regex matches across all OCR text lines (flattened)."""
        results = []
        for item in texts:
            results.extend(re.findall(pattern, item.text, flags))
        return results

    def full_text(self, texts: List[OCRText]) -> str:
        return "\n".join(t.text for t in texts)

    # ── Internal ──────────────────────────────────────────────────────────

    def _find_label_box(self, texts: List[OCRText], keywords: List[str]) -> Optional[OCRText]:
        """
        Find the first OCR box that matches any of the label keywords.
        Matching is case-insensitive and checks for containment.
        Keywords are tried in order so more specific ones should come first.
        """
        kw_upper = [k.upper() for k in keywords]

        for item in texts:
            t = item.text.upper().strip().rstrip(":").rstrip()
            for kw in kw_upper:
                kw_clean = kw.upper().rstrip(":").rstrip()
                # Exact match or keyword contained in this box's text
                if t == kw_clean or kw_clean in t:
                    return item

        return None
