# app/ocr/paddle_ocr.py
import numpy as np
from paddleocr import PaddleOCR
from app.models.ocr_models import (
    Point,
    BoundingBox,
    OCRText,
    OCRResult,
)

MIN_CONFIDENCE = 0.80  # tune against your own document set


class PaddleOCRService:
    """
    PaddleOCR wrapper — now using server-weight det/rec models instead of
    the default mobile weights, since the mobile recognizer is the main
    source of hallucinated text on small/dense ID-card fonts.
    """

    def __init__(
        self,
        det_model_dir: str = "models/det_server/ch_PP-OCRv4_det_server_infer",
        rec_model_dir: str = "models/rec_server/en_PP-OCRv4_rec_server_infer",
        cls_model_dir: str = "models/cls/ch_ppocr_mobile_v2.0_cls_infer",
        min_confidence: float = MIN_CONFIDENCE,
    ):
        self.min_confidence = min_confidence
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            show_log=False,
            use_gpu=True,
            det_model_dir=det_model_dir,
            rec_model_dir=rec_model_dir,
            cls_model_dir=cls_model_dir,
            # server rec models expect a taller input — bump this up from
            # the mobile default (48) or you lose most of the accuracy gain
            rec_image_shape="3,64,320",
        )

    def extract(self, image_input, min_confidence: float | None = None) -> OCRResult:
        raw_result = self.ocr.ocr(image_input, cls=True)
        # for i in raw_result:
        #     print(i)
        threshold = min_confidence if min_confidence is not None else self.min_confidence
        return self._convert_result(raw_result, threshold)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _convert_result(self, raw_result, threshold: float) -> OCRResult:
        if not raw_result or raw_result[0] is None:
            return OCRResult(full_text="", texts=[])

        texts = []
        dropped = 0

        for item in raw_result[0]:
            box = item[0]
            text = item[1][0]
            confidence = float(item[1][1])

            # 2. Confidence-threshold filtering — this is where the
            # hallucinated words get caught. Anything below the threshold
            # is discarded entirely rather than passed downstream.
            if confidence < threshold:
                dropped += 1
                continue

            points = [Point(x=float(p[0]), y=float(p[1])) for p in box]

            texts.append(
                OCRText(
                    text=text,
                    confidence=confidence,
                    bounding_box=BoundingBox(points=points),
                )
            )

        if dropped:
            import logging
            logging.getLogger(__name__).debug(
                f"Dropped {dropped} low-confidence OCR box(es) below {threshold}"
            )

        texts.sort(key=lambda t: (round(t.bounding_box.min_y / 15) * 15, t.bounding_box.min_x))

        return OCRResult(
            full_text="\n".join(t.text for t in texts),
            texts=texts,
        )