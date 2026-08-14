"""
app/image_straightener/straightener.py
========================================
Universal Image Straightener & Disambiguated Orientation System
----------------------------------------------------------------
Performs 2-stage document orientation alignment (axis selection + 180° flip disambiguation),
4-corner perspective unwarping, and fine angle deskewing on image arrays prior to OCR.
"""

import logging
import re
import cv2
import numpy as np
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

_COMMON_DOC_KEYWORDS = {
    'GOVT', 'GOVERNMENT', 'INDIA', 'INDIAN', 'UNION', 'STATE', 'DEPARTMENT',
    'INCOME', 'TAX', 'PERMANENT', 'ACCOUNT', 'NUMBER', 'CARD', 'AADHAAR',
    'UNIQUE', 'IDENTIFICATION', 'AUTHORITY', 'DRIVING', 'LICENCE', 'LICENSE',
    'REGISTRATION', 'CERTIFICATE', 'VEHICLE', 'MOTOR', 'CHASSIS', 'ENGINE',
    'NAME', 'DATE', 'BIRTH', 'DOB', 'ISSUE', 'VALIDITY', 'EXPIRE', 'EXPIRY',
    'ADDRESS', 'MALE', 'FEMALE', 'FATHER', 'HOLDER', 'SIGNATURE', 'MCWG', 'LMV',
    'GJ', 'DL', 'RC', 'PAN', 'SURAT', 'GUJARAT', 'MAHARASHTRA', 'RAJASTHAN', 'DELHI'
}


class ImageStraightener:
    """
    Universal image straightener.
    Takes a BGR numpy array and returns a straightened, 100% upright BGR numpy array.
    """

    def __init__(self, ocr_service=None):
        self._ocr = ocr_service

    def straighten(self, img: np.ndarray, ocr_service=None) -> np.ndarray:
        """
        Main entry point. Straightens and aligns document image universally.
        
        Args:
            img: OpenCV BGR image (np.ndarray)
            ocr_service: Optional OCR service instance for 180° disambiguation
            
        Returns:
            Straightened OpenCV BGR image (np.ndarray)
        """
        if img is None or not isinstance(img, np.ndarray) or img.size == 0:
            return img

        if ocr_service is not None:
            self._ocr = ocr_service

        processed = img.copy()

        # Step 1: Universal 2-Stage Orientation Correction (0° / 90° / 180° / 270°)
        processed, rotation_deg = self._correct_orientation_universal(processed)
        if rotation_deg != 0:
            logger.info(f"[ImageStraightener] Document rotated by {rotation_deg}° to upright orientation.")

        # Step 2: Perspective Crop (if 4-corner document contour is detected)
        unwarped = self._perspective_crop(processed)
        if unwarped is not None and unwarped.size > 0:
            processed = unwarped
            logger.info("[ImageStraightener] Perspective unwarping applied.")

        # Step 3: Fine-Angle Deskewing (< 15°)
        processed, skew_angle = self._correct_fine_skew(processed)
        if abs(skew_angle) > 0.3:
            logger.info(f"[ImageStraightener] Fine skew corrected by {skew_angle:.2f}°.")

        return processed

    # ── Universal 2-Stage Orientation Disambiguation ──────────────────────────

    def _correct_orientation_universal(self, img: np.ndarray) -> Tuple[np.ndarray, int]:
        """
        Stage 1: Axis Selection (Horizontal vs Vertical text lines via projection variance).
        Stage 2: 180° Flip Disambiguation via Universal Vocabulary & OCR Confidence Evaluation.
        """
        # Score 0° (unrotated) and 90° clockwise
        score_0 = self._text_line_projection_score(img)
        img_90 = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        score_90 = self._text_line_projection_score(img_90)

        # Stage 1: Determine candidate axis
        if score_90 > score_0 * 1.10:
            # Text runs vertically in raw image -> Candidates are 90° and 270°
            candidates = [90, 270]
        else:
            # Text runs horizontally in raw image -> Candidates are 0° and 180°
            candidates = [0, 180]

        # Stage 2: Disambiguate between candidate pair (upright vs 180° upside-down)
        best_deg = self._disambiguate_candidates(img, candidates)

        if best_deg == 0:
            return img, 0

        rotate_codes = {
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }
        rotated_img = cv2.rotate(img, rotate_codes[best_deg])
        return rotated_img, best_deg

    def _disambiguate_candidates(self, img: np.ndarray, candidates: list) -> int:
        """
        Evaluates candidate rotations using OCR recognition confidence and universal document keywords.
        """
        rotate_codes = {
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }

        # Ensure OCR service is initialized
        if self._ocr is None:
            try:
                from app.ocr.paddle_ocr import PaddleOCRService
                self._ocr = PaddleOCRService()
            except Exception as e:
                logger.warning(f"Could not load OCR for orientation disambiguation: {e}")
                return candidates[0]

        best_score = -1.0
        best_deg = candidates[0]

        for deg in candidates:
            cand_img = img if deg == 0 else cv2.rotate(img, rotate_codes[deg])
            ocr_res = self._ocr.extract(cand_img)

            score = self._compute_orientation_score(ocr_res)
            logger.debug(f"[Orientation Disambiguation] Candidate {deg}° score: {score:.2f}")

            if score > best_score:
                best_score = score
                best_deg = deg

        return best_deg

    @staticmethod
    def _compute_orientation_score(ocr_res) -> float:
        """
        Universal orientation score:
        Score = Sum of OCR Confidence Scores + 50.0 * (Matched Universal Keywords)
        """
        if not ocr_res or not ocr_res.texts:
            return 0.0

        conf_sum = sum(t.confidence for t in ocr_res.texts)
        kw_matches = 0

        for t in ocr_res.texts:
            up_words = set(re.findall(r'[A-Z0-9]+', t.text.upper()))
            matched = up_words.intersection(_COMMON_DOC_KEYWORDS)
            kw_matches += len(matched)

        return (kw_matches * 50.0) + conf_sum

    def _text_line_projection_score(self, img: np.ndarray) -> float:
        """
        Calculates row projection variance after merging text horizontally.
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]
            scale = 600.0 / max(h, w)
            if scale < 1.0:
                gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
            merged = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            row_sums = np.sum(merged, axis=1).astype(np.float64)
            return float(np.var(row_sums))
        except Exception as e:
            logger.debug(f"Error computing text line projection score: {e}")
            return 0.0

    # ── 4-Point Corner Perspective Unwarping ──────────────────────────────────

    def _perspective_crop(self, img: np.ndarray) -> Optional[np.ndarray]:
        """
        Detects 4-corner card contours and unwarps perspective if valid card found.
        """
        try:
            h, w = img.shape[:2]
            img_area = h * w

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edged = cv2.Canny(blurred, 50, 150)

            contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return None

            contours = sorted(contours, key=cv2.contourArea, reverse=True)

            card_contour = None
            for c in contours[:5]:
                area = cv2.contourArea(c)
                if area < img_area * 0.25:
                    continue

                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)

                if len(approx) == 4:
                    card_contour = approx
                    break

            if card_contour is None:
                return None

            pts = card_contour.reshape(4, 2)
            rect = self._order_points(pts)
            (tl, tr, br, bl) = rect

            widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
            widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
            maxWidth = max(int(widthA), int(widthB))

            heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
            heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
            maxHeight = max(int(heightA), int(heightB))

            dst = np.array([
                [0, 0],
                [maxWidth - 1, 0],
                [maxWidth - 1, maxHeight - 1],
                [0, maxHeight - 1]
            ], dtype="float32")

            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(img, M, (maxWidth, maxHeight))
            return warped
        except Exception as e:
            logger.debug(f"Perspective crop skipped: {e}")
            return None

    @staticmethod
    def _order_points(pts: np.ndarray) -> np.ndarray:
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect

    # ── Fine Skew Angle Correction ───────────────────────────────────────────

    def _correct_fine_skew(self, img: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Detects fine tilt angle (< 15°) using Hough lines and deskews the image.
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)

            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=80,
                minLineLength=img.shape[1] * 0.15,
                maxLineGap=20,
            )

            if lines is None or len(lines) < 3:
                return img, 0.0

            angles = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                if x2 == x1:
                    continue
                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                if abs(angle) < 15.0:
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
                img, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
            return deskewed, skew_angle
        except Exception as e:
            logger.debug(f"Deskew skipped: {e}")
            return img, 0.0
