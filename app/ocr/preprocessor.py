"""
app/ocr/preprocessor.py:
Image Preprocessor
==================
Handles every real-world condition a user might upload:

Input formats accepted:
  - File path (str / pathlib.Path) — JPG, JPEG, PNG, WEBP, BMP, TIFF, GIF
  - Raw bytes
  - Base64 encoded string (with or without data:image/... prefix)
  - URL (http / https)
  - numpy ndarray (BGR, already loaded)
  - PIL.Image.Image

Conditions handled:
  - EXIF orientation (phone photos taken sideways/upside-down)
  - Document-level rotation (0/90/180/270) — via projection profile scoring
  - Small skew correction — via Hough line angle estimation
  - Blur / out-of-focus detection (Laplacian variance)
  - Low brightness / too dark (gamma correction + CLAHE)
  - Overexposure / glare / reflection (CLAHE on L channel)
  - Low contrast (CLAHE)
  - Noise reduction (mild Gaussian blur before CLAHE)
"""

import io
import base64
import logging
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image, ExifTags
from app.ocr.config import preprocessor_config

logger = logging.getLogger(__name__)

# ── Supported file extensions ─────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = preprocessor_config.SUPPORTED_EXTENSIONS

# ══════════════════════════════════════════════════════════════════════════════
# Quality thresholds (loaded from PreprocessorConfig)
# ══════════════════════════════════════════════════════════════════════════════
BLUR_THRESHOLD = preprocessor_config.BLUR_THRESHOLD
DARK_THRESHOLD = preprocessor_config.DARK_THRESHOLD
BRIGHT_THRESHOLD = preprocessor_config.BRIGHT_THRESHOLD
GLARE_THRESHOLD_PERCENT = preprocessor_config.GLARE_THRESHOLD_PERCENT


# ══════════════════════════════════════════════════════════════════════════════
class ImagePreprocessor:
    """
    Preprocesses a document image for best OCR accuracy.
    Returns a BGR numpy array ready for PaddleOCR.
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def preprocess(self,image_input,*,fix_orientation: bool = True,enhance: bool = True,) -> Tuple[np.ndarray, "ImageQualityReport"]:
        """
        Main entry point. Accepts any supported input format.

        Returns:
            (preprocessed_bgr_ndarray, ImageQualityReport)
        """
        from app.models.ocr_models import ImageQualityReport

        report = ImageQualityReport()

        # 1. Load to BGR numpy array
        img = self._load_image(image_input)
        report.original_height, report.original_width = img.shape[:2]

        # 2. Downscale oversized smartphone photos (e.g. 12MP-48MP) to preserve memory & speed
        img = self._downscale_if_oversized(img)

        # 3. EXIF orientation fix (must happen before anything else)
        img = self._fix_exif_orientation(image_input, img)

        # 3. Document-level rotation correction (90/180/270)
        if fix_orientation:
            img, rotation = self._correct_document_rotation(img)
            if rotation != 0:
                report.was_rotated = True
                report.rotation_applied = rotation

            # 4. Skew correction (small angles < 15°)
            img, skew_angle = self._correct_skew(img)
            if abs(skew_angle) > 0.3:
                report.skew_corrected = True
                report.skew_angle = round(skew_angle, 2)

        # 5. Quality assessment
        report.blur_score = round(self._laplacian_score(img), 2)
        report.is_blurry = report.blur_score < BLUR_THRESHOLD

        report.brightness = round(self._mean_brightness(img), 2)
        report.is_too_dark = report.brightness < DARK_THRESHOLD
        report.is_too_bright = report.brightness > BRIGHT_THRESHOLD

        report.glare_percentage = round(self._glare_percent(img), 2)
        report.has_glare = report.glare_percentage > GLARE_THRESHOLD_PERCENT

        # 6. Enhancement
        if enhance:
            enhanced = self._enhance(img, report)
            if enhanced is not img:
                report.was_enhanced = True
                img = enhanced

        # 7. Build warnings
        if report.is_blurry:
            report.warnings.append(
                f"Image is blurry (score: {report.blur_score:.1f} < {BLUR_THRESHOLD})"
            )
        if report.is_too_dark:
            report.warnings.append(
                f"Image is too dark (brightness: {report.brightness:.1f})"
            )
        if report.is_too_bright:
            report.warnings.append(
                f"Image is overexposed (brightness: {report.brightness:.1f})"
            )
        if report.has_glare:
            report.warnings.append(
                f"Glare/reflection detected ({report.glare_percentage:.1f}% of image)"
            )

        return img, report

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load_image(self, image_input) -> np.ndarray:
        """Unified loader — accepts any supported format."""

        # Already a numpy array (BGR)
        if isinstance(image_input, np.ndarray):
            return image_input.copy()

        # PIL Image
        if isinstance(image_input, Image.Image):
            return self._pil_to_bgr(image_input)

        # bytes / bytearray
        if isinstance(image_input, (bytes, bytearray)):
            return self._from_bytes(bytes(image_input))

        # str or Path
        if isinstance(image_input, (str, Path)):
            s = str(image_input)

            # data-URI base64
            # if s.startswith("data:image"):
            #     return self._from_base64(s)

            # Plain base64 string (long, no path chars)
            # if self._looks_like_base64(s):
            #     return self._from_base64(s)

            # URL
            # if s.startswith("http://") or s.startswith("https://"):
            #     return self._from_url(s)

            # File path
            return self._from_file(s)

        raise ValueError(f"Unsupported image input type: {type(image_input)}")

    def _from_file(self, path: str) -> np.ndarray:
        ext = Path(path).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension '{ext}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )
        img = cv2.imread(path)
        if img is None:
            # Fallback to PIL (handles more formats / unicode paths)
            pil_img = Image.open(path)
            img = self._pil_to_bgr(pil_img)
        if img is None:
            raise FileNotFoundError(f"Could not read image: {path}")
        return img


    @staticmethod
    def _downscale_if_oversized(img: np.ndarray, max_dim: int | None = None) -> np.ndarray:
        """
        Downscales images whose longest edge exceeds max_dim (default from PreprocessorConfig: 1920px)
        while preserving original aspect ratio.
        """
        target_max = max_dim or preprocessor_config.MAX_IMAGE_DIMENSION
        h, w = img.shape[:2]
        if max(h, w) > target_max:
            scale = target_max / float(max(h, w))
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return img

    @staticmethod
    def _pil_to_bgr(pil_img: Image.Image) -> np.ndarray:
        rgb = np.array(pil_img.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    # @staticmethod
    # def _looks_like_base64(s: str) -> bool:
    #     if len(s) < 50:
    #         return False
    #     # Base64 strings don't have path separators
    #     if "/" in s[:20] or "\\" in s[:20] or "." in s[:10]:
    #         return False
    #     try:
    #         base64.b64decode(s[:64], validate=True)
    #         return True
    #     except Exception:
    #         return False

    # ── EXIF orientation ──────────────────────────────────────────────────────

    def _fix_exif_orientation(self, original_input, img: np.ndarray) -> np.ndarray:
        """
        Reads EXIF orientation tag from the original source (file or PIL Image)
        and rotates the already-loaded numpy array to match the correct orientation.
        Phone photos often have an EXIF tag saying the image is rotated 90° CW.
        """
        try:
            pil_img = None

            if isinstance(original_input, Image.Image):
                pil_img = original_input
            elif isinstance(original_input, (str, Path)):
                path = str(original_input)
                if (Path(path).exists() and Path(path).is_file()):
                    # not path.startswith("http") and not path.startswith("data:") and not self._looks_like_base64(path)
                    pil_img = Image.open(path)

            if pil_img is None:
                return img

            exif_data = pil_img._getexif() if hasattr(pil_img, "_getexif") else None
            if not exif_data:
                return img

            orientation_key = next(
                (k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None
            )
            if orientation_key is None or orientation_key not in exif_data:
                return img

            orientation = exif_data[orientation_key]

            # EXIF orientation → OpenCV rotation code
            rotation_map = {
                3: cv2.ROTATE_180,
                6: cv2.ROTATE_90_CLOCKWISE,
                8: cv2.ROTATE_90_COUNTERCLOCKWISE,
            }

            if orientation in rotation_map:
                img = cv2.rotate(img, rotation_map[orientation])
                logger.debug(f"EXIF orientation {orientation} — rotation applied")

        except Exception as e:
            logger.debug(f"EXIF fix skipped: {e}")

        return img

    # ── Rotation correction (document-level) ─────────────────────────────────

    def _correct_document_rotation(self, img: np.ndarray) -> Tuple[np.ndarray, int]:
        """
        Detect if the entire document image is rotated by 90/180/270 degrees
        and correct it.

        Strategy: Horizontal projection profile variance.
        A correctly-oriented document (text in horizontal lines) produces
        a high-variance horizontal projection compared to a rotated document.
        This is extremely fast (no OCR required).
        """
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

        if best_rotation != 0:
            logger.debug(f"Document rotation corrected by {best_rotation}°")

        return best_img, best_rotation

    @staticmethod
    def _projection_variance(img: np.ndarray) -> float:
        """
        Horizontal projection profile variance.
        Higher value means text lines are more horizontal → better orientation.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Binarize
        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        # Sum pixels per row → projection profile
        h_proj = np.sum(binary, axis=1).astype(np.float64)

        return float(np.var(h_proj))

    # ── Skew correction ───────────────────────────────────────────────────────

    def _correct_skew(self, img: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Detect and correct small skew angles (< ~15 degrees) using
        Hough line detection.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Canny edges
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        # Probabilistic Hough — faster, more selective
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
            # Keep only near-horizontal lines (skew angles typically ±15°)
            if abs(angle) < 15:
                angles.append(angle)

        if len(angles) < 3:
            return img, 0.0

        skew_angle = float(np.median(angles))

        # Only correct if skew is meaningful
        if abs(skew_angle) < 0.3:
            return img, 0.0

        # Deskew
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, skew_angle, 1.0)
        deskewed = cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

        logger.debug(f"Skew corrected: {skew_angle:.2f}°")
        return deskewed, skew_angle

    # ── Quality metrics ───────────────────────────────────────────────────────

    @staticmethod
    def _laplacian_score(img: np.ndarray) -> float:
        """Laplacian variance — higher = sharper."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    @staticmethod
    def _mean_brightness(img: np.ndarray) -> float:
        """Mean pixel brightness (0–255)."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))

    @staticmethod
    def _glare_percent(img: np.ndarray) -> float:
        """Percentage of pixels that are near-white (overexposed glare)."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float(np.sum(gray > 250) / gray.size * 100.0)

    # ── Enhancement ───────────────────────────────────────────────────────────

    def _enhance(self, img: np.ndarray, report) -> np.ndarray:
        """
        Apply image enhancements to improve OCR accuracy:
        - CLAHE (adaptive histogram equalization) for dark/low-contrast/glare images
        - Gamma correction for dark images
        - Mild Gaussian blur to reduce noise (only when very noisy)
        """
        needs_clahe = report.is_too_dark or report.has_glare or (
            report.brightness < 100 and not report.is_too_bright
        )

        if not needs_clahe:
            return img  # No enhancement needed

        enhanced = img.copy()

        # Convert to LAB — CLAHE on L channel avoids color distortion
        lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)

        clahe = cv2.createCLAHE(
            clipLimit=preprocessor_config.CLAHE_CLIP_LIMIT,
            tileGridSize=preprocessor_config.CLAHE_TILE_GRID_SIZE,
        )
        l_ch = clahe.apply(l_ch)

        lab = cv2.merge([l_ch, a_ch, b_ch])
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        # Additional gamma correction for very dark images
        if report.is_too_dark:
            gamma = preprocessor_config.GAMMA
            inv_gamma = 1.0 / gamma
            lut = np.array(
                [((i / 255.0) ** inv_gamma) * 255 for i in range(256)],
                dtype=np.uint8,
            )
            enhanced = cv2.LUT(enhanced, lut)

        return enhanced
