import numpy as np
from paddleocr import PaddleOCR

from app.models.ocr_models import (
    Point,
    BoundingBox,
    OCRText,
    OCRResult,
)


class PaddleOCRService:
    """
    PaddleOCR wrapper.

    use_angle_cls=True  → per-text-box angle classification (handles
                          rotated / upside-down individual text regions)
    lang="en"           → English model

    Accepts both file paths and preprocessed numpy arrays (BGR).
    """

    def __init__(self):
        self.ocr = PaddleOCR(
            use_angle_cls=True,   # ON — handles any residual per-region rotation
            lang="en",
            show_log=False,
        )

    def extract(self, image_input) -> OCRResult:
        """
        Run OCR on a file path or a BGR numpy array.

        Args:
            image_input: str file path  OR  np.ndarray (BGR image)

        Returns:
            OCRResult with text + bounding boxes, y-sorted top-to-bottom.
        """
        raw_result = self.ocr.ocr(image_input, cls=True)
        # for i in raw_result:
        #     print(i)
        print(raw_result[0][1])
        return self._convert_result(raw_result)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _convert_result(self, raw_result) -> OCRResult:

        if not raw_result or raw_result[0] is None:
            return OCRResult(full_text="", texts=[])

        texts = []

        for item in raw_result[0]:
            box = item[0]
            text = item[1][0]
            confidence = float(item[1][1])

            points = [Point(x=float(p[0]), y=float(p[1])) for p in box]

            texts.append(
                OCRText(
                    text=text,
                    confidence=confidence,
                    bounding_box=BoundingBox(points=points),
                )
            )

        # Sort top-to-bottom, left-to-right for label-proximity matching
        texts.sort(key=lambda t: (round(t.bounding_box.min_y / 15) * 15, t.bounding_box.min_x))

        return OCRResult(
            full_text="\n".join(t.text for t in texts),
            texts=texts,
        )