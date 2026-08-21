"""
PaddleOCR PP-OCRv4 Engine Wrapper for OCR Microservice
"""

import logging
from typing import Optional
import numpy as np
from paddleocr import PaddleOCR

from microservices.shared.models import Point, BoundingBox, OCRText, OCRResult
from microservices.ocr_service.config import ocr_config

logger = logging.getLogger("ocr_service.paddle_ocr")


class PaddleOCRService:
    """Singleton-ready PaddleOCR wrapper."""

    def __init__(self):
        use_gpu = ocr_config.USE_GPU

        # 1. Proactively check if CUDA runtime and GPU hardware are available
        try:
            import paddle
            if use_gpu:
                if not paddle.is_compiled_with_cuda() or paddle.device.cuda.device_count() == 0:
                    logger.warning(
                        "GPU requested in OCR configuration (OCR_USE_GPU=true), but no compatible "
                        "CUDA-enabled GPU was detected on this system. Automatically falling back to CPU mode."
                    )
                    use_gpu = False
        except Exception as e:
            logger.warning(f"Could not verify CUDA availability ({e}). Falling back to CPU mode.")
            use_gpu = False

        logger.info(f"Initializing PaddleOCR PP-OCRv4 Engine (GPU Mode: {use_gpu})...")
        self.min_confidence = ocr_config.MIN_CONFIDENCE

        # 2. Initialize with graceful fallback try/except
        try:
            self.ocr = PaddleOCR(
                use_angle_cls=ocr_config.USE_ANGLE_CLS,
                lang=ocr_config.LANG,
                show_log=ocr_config.SHOW_LOG,
                use_gpu=use_gpu,
                det_model_dir=ocr_config.DET_MODEL_DIR,
                rec_model_dir=ocr_config.REC_MODEL_DIR,
                cls_model_dir=ocr_config.CLS_MODEL_DIR,
                rec_image_shape=ocr_config.REC_IMAGE_SHAPE,
            )
        except Exception as err:
            if use_gpu:
                logger.error(
                    f"PaddleOCR failed to initialize with GPU ({err}). "
                    f"Retrying initialization in CPU mode..."
                )
                self.ocr = PaddleOCR(
                    use_angle_cls=ocr_config.USE_ANGLE_CLS,
                    lang=ocr_config.LANG,
                    show_log=ocr_config.SHOW_LOG,
                    use_gpu=False,
                    det_model_dir=ocr_config.DET_MODEL_DIR,
                    rec_model_dir=ocr_config.REC_MODEL_DIR,
                    cls_model_dir=ocr_config.CLS_MODEL_DIR,
                    rec_image_shape=ocr_config.REC_IMAGE_SHAPE,
                )
            else:
                raise err

        logger.info("PaddleOCR engine initialized successfully.")

    def extract(self, image_input: np.ndarray, min_confidence: Optional[float] = None) -> OCRResult:
        threshold = min_confidence if min_confidence is not None else self.min_confidence
        raw_result = self.ocr.ocr(image_input, cls=True)
        
        # for i in raw_result:
        #     print(i)
        #     print("-----------------------------------------------------------------------------------------------------")
        # print("x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x-x")
        # if raw_result and raw_result[0]:
        #     print("\n" + "=" * 55, flush=True)
        #     print("  --- OCR RAW EXTRACTED TEXT ---", flush=True)
        #     print("=" * 55, flush=True)
        #     for line in raw_result[0]:
        #         box, (text, conf) = line
        #         print(f"  * {text:<32} (conf: {conf:.2f})", flush=True)
        #     print("=" * 55 + "\n", flush=True)

        return self._convert_result(raw_result, threshold)

    def _convert_result(self, raw_result, threshold: float) -> OCRResult:
        if not raw_result or raw_result[0] is None:
            return OCRResult(full_text="", texts=[])

        texts = []
        for item in raw_result[0]:
            box = item[0]
            text = item[1][0]
            confidence = float(item[1][1])

            if confidence < threshold:
                continue

            points = [Point(x=float(p[0]), y=float(p[1])) for p in box]
            texts.append(
                OCRText(
                    text=text,
                    confidence=confidence,
                    bounding_box=BoundingBox(points=points),
                )
            )

        # Sort top-to-bottom, left-to-right
        texts.sort(key=lambda t: (round(t.bounding_box.min_y / 15) * 15, t.bounding_box.min_x))

        return OCRResult(
            full_text="\n".join(t.text for t in texts),
            texts=texts,
        )
