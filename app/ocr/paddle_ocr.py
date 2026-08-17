# app/ocr/paddle_ocr.py
import numpy as np
from paddleocr import PaddleOCR
from app.ocr.config import ocr_config
from app.models.ocr_models import (
    Point,
    BoundingBox,
    OCRText,
    OCRResult,
)


class PaddleOCRService:
    """
    PaddleOCR wrapper — uses server-weight det/rec models configured via OCRConfig.
    """

    def __init__(
        self,
        det_model_dir: str | None = None,
        rec_model_dir: str | None = None,
        cls_model_dir: str | None = None,
        min_confidence: float | None = None,
        rec_image_shape: str | None = None,
        use_gpu: bool | None = None,
    ):
        self.min_confidence = (
            min_confidence if min_confidence is not None else ocr_config.MIN_CONFIDENCE
        )
        self.ocr = PaddleOCR(
            use_angle_cls=ocr_config.USE_ANGLE_CLS,
            lang=ocr_config.LANG,
            show_log=ocr_config.SHOW_LOG,
            use_gpu=use_gpu if use_gpu is not None else ocr_config.USE_GPU,
            det_model_dir=det_model_dir or ocr_config.DET_MODEL_DIR,
            rec_model_dir=rec_model_dir or ocr_config.REC_MODEL_DIR,
            cls_model_dir=cls_model_dir or ocr_config.CLS_MODEL_DIR,
            rec_image_shape=rec_image_shape or ocr_config.REC_IMAGE_SHAPE,
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