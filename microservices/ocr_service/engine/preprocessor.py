"""
Image Preprocessor for OCR Microservice
"""

import logging
from pathlib import Path
from typing import Tuple, Optional
import cv2
import numpy as np
from PIL import Image, ExifTags

from microservices.shared.models import ImageQualityReport
from microservices.ocr_service.config import ocr_config

logger = logging.getLogger("ocr_service.preprocessor")


class ImagePreprocessor:
    """Preprocesses a document image for best OCR accuracy."""

    def preprocess(
        self,
        image_input,
        *,
        fix_orientation: bool = True,
        enhance: bool = True,
    ) -> Tuple[np.ndarray, ImageQualityReport]:
        report = ImageQualityReport()
        img = self._load_image(image_input)
        report.original_height, report.original_width = img.shape[:2]

        img = self._downscale_if_oversized(img)
        img = self._fix_exif_orientation(image_input, img)

        if fix_orientation:
            img, rotation = self._correct_document_rotation(img)
            if rotation != 0:
                report.was_rotated = True
                report.rotation_applied = rotation

            img, skew_angle = self._correct_skew(img)
            if abs(skew_angle) > 0.3:
                report.skew_corrected = True
                report.skew_angle = round(skew_angle, 2)

        report.blur_score = round(self._laplacian_score(img), 2)
        report.is_blurry = report.blur_score < ocr_config.BLUR_THRESHOLD

        report.brightness = round(self._mean_brightness(img), 2)
        report.is_too_dark = report.brightness < ocr_config.DARK_THRESHOLD
        report.is_too_bright = report.brightness > ocr_config.BRIGHT_THRESHOLD

        report.glare_percentage = round(self._glare_percent(img), 2)
        report.has_glare = report.glare_percentage > ocr_config.GLARE_THRESHOLD_PERCENT

        if enhance:
            enhanced = self._enhance(img, report)
            if enhanced is not img:
                report.was_enhanced = True
                img = enhanced

        if report.is_blurry:
            report.warnings.append(
                f"Image is blurry (score: {report.blur_score:.1f} < {ocr_config.BLUR_THRESHOLD})"
            )
        if report.is_too_dark:
            report.warnings.append(f"Image is too dark (brightness: {report.brightness:.1f})")
        if report.is_too_bright:
            report.warnings.append(f"Image is overexposed (brightness: {report.brightness:.1f})")
        if report.has_glare:
            report.warnings.append(f"Glare detected ({report.glare_percentage:.1f}% of image)")

        return img, report

    def _load_image(self, image_input) -> np.ndarray:
        if isinstance(image_input, np.ndarray):
            return image_input.copy()
        if isinstance(image_input, Image.Image):
            return self._pil_to_bgr(image_input)
        if isinstance(image_input, (bytes, bytearray)):
            nparr = np.frombuffer(bytes(image_input), np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("Could not decode image bytes")
            return img
        if isinstance(image_input, (str, Path)):
            img = cv2.imread(str(image_input))
            if img is None:
                pil_img = Image.open(str(image_input))
                img = self._pil_to_bgr(pil_img)
            if img is None:
                raise FileNotFoundError(f"Could not read image: {image_input}")
            return img
        raise ValueError(f"Unsupported image input type: {type(image_input)}")

    @staticmethod
    def _downscale_if_oversized(img: np.ndarray, max_dim: int = 1920) -> np.ndarray:
        h, w = img.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return img

    @staticmethod
    def _pil_to_bgr(pil_img: Image.Image) -> np.ndarray:
        rgb = np.array(pil_img.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def _fix_exif_orientation(self, original_input, img: np.ndarray) -> np.ndarray:
        try:
            pil_img = None
            if isinstance(original_input, Image.Image):
                pil_img = original_input
            elif isinstance(original_input, (str, Path)) and Path(original_input).is_file():
                pil_img = Image.open(str(original_input))
            if pil_img is None:
                return img
            exif_data = pil_img._getexif() if hasattr(pil_img, "_getexif") else None
            if not exif_data:
                return img
            orientation_key = next((k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None)
            if orientation_key is None or orientation_key not in exif_data:
                return img
            orientation = exif_data[orientation_key]
            rotation_map = {
                3: cv2.ROTATE_180,
                6: cv2.ROTATE_90_CLOCKWISE,
                8: cv2.ROTATE_90_COUNTERCLOCKWISE,
            }
            if orientation in rotation_map:
                img = cv2.rotate(img, rotation_map[orientation])
        except Exception:
            pass
        return img

    def _correct_document_rotation(self, img: np.ndarray) -> Tuple[np.ndarray, int]:
        best_img = img
        best_score = self._projection_variance(img)
        best_rotation = 0
        candidates = [90, 180, 270]
        rotate_codes = {
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }
        for deg in candidates:
            rotated = cv2.rotate(img, rotate_codes[deg])
            score = self._projection_variance(rotated)
            threshold = 1.50 if deg == 180 else 1.25
            if score > best_score * threshold:
                best_score = score
                best_img = rotated
                best_rotation = deg
        return best_img, best_rotation

    @staticmethod
    def _projection_variance(img: np.ndarray) -> float:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        h_proj = np.sum(binary, axis=1).astype(np.float64)
        return float(np.var(h_proj))

    def _correct_skew(self, img: np.ndarray) -> Tuple[np.ndarray, float]:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=100,
            minLineLength=img.shape[1] * 0.2,
            maxLineGap=20,
        )
        if lines is None or len(lines) < 5:
            return img, 0.0
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 == x1:
                continue
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if abs(angle) < 15:
                angles.append(angle)
        if len(angles) < 3:
            return img, 0.0
        skew_angle = float(np.median(angles))
        if abs(skew_angle) < 0.3:
            return img, 0.0
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, skew_angle, 1.0)
        deskewed = cv2.warpAffine(
            img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        return deskewed, skew_angle

    @staticmethod
    def _laplacian_score(img: np.ndarray) -> float:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    @staticmethod
    def _mean_brightness(img: np.ndarray) -> float:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))

    @staticmethod
    def _glare_percent(img: np.ndarray) -> float:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float(np.sum(gray > 250) / gray.size * 100.0)

    def _enhance(self, img: np.ndarray, report: ImageQualityReport) -> np.ndarray:
        needs_clahe = report.is_too_dark or report.has_glare or (
            report.brightness < 100 and not report.is_too_bright
        )
        if not needs_clahe:
            return img

        enhanced = img.copy()
        lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=ocr_config.CLAHE_CLIP_LIMIT, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        lab = cv2.merge([l_ch, a_ch, b_ch])
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        if report.is_too_dark:
            inv_gamma = 1.0 / ocr_config.GAMMA
            lut = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)], dtype=np.uint8)
            enhanced = cv2.LUT(enhanced, lut)

        return enhanced
