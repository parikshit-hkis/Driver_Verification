from pydantic import BaseModel
from typing import List, Optional
from dataclasses import dataclass, field


class Point(BaseModel):
    x: float
    y: float


class BoundingBox(BaseModel):
    points: List[Point]

    @property
    def min_x(self) -> float:
        return min(p.x for p in self.points)

    @property
    def max_x(self) -> float:
        return max(p.x for p in self.points)

    @property
    def min_y(self) -> float:
        return min(p.y for p in self.points)

    @property
    def max_y(self) -> float:
        return max(p.y for p in self.points)

    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) / 2.0

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2.0

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


class OCRText(BaseModel):
    text: str
    confidence: float
    bounding_box: BoundingBox


class OCRResult(BaseModel):
    full_text: str
    texts: List[OCRText]


@dataclass
class ImageQualityReport:
    """Detailed image quality assessment results."""
    blur_score: float = 0.0
    is_blurry: bool = False
    brightness: float = 0.0
    is_too_dark: bool = False
    is_too_bright: bool = False
    glare_percentage: float = 0.0
    has_glare: bool = False
    was_rotated: bool = False
    rotation_applied: int = 0       # degrees
    skew_corrected: bool = False
    skew_angle: float = 0.0
    was_enhanced: bool = False
    original_width: int = 0
    original_height: int = 0
    warnings: list = field(default_factory=list)

    def is_acceptable(self) -> bool:
        """Returns True if image quality is usable for OCR."""
        return not (self.is_blurry and self.blur_score < 30.0)

    def summary(self) -> str:
        lines = [
            f"  Blur Score   : {self.blur_score:.1f}   {'[BLURRY]' if self.is_blurry else '[CLEAR]'}",
            f"  Brightness   : {self.brightness:.1f}   "
            f"{'[TOO DARK]' if self.is_too_dark else '[TOO BRIGHT]' if self.is_too_bright else '[GOOD]'}",
            f"  Glare        : {self.glare_percentage:.1f}%  {'[DETECTED]' if self.has_glare else '[OK]'}",
            f"  Rotation     : {self.rotation_applied}°  {'[CORRECTED]' if self.was_rotated else '[NONE]'}",
            f"  Enhanced     : {'YES' if self.was_enhanced else 'NO'}",
        ]
        if self.warnings:
            lines.append(f"  Warnings     : {'; '.join(self.warnings)}")
        return "\n".join(lines)