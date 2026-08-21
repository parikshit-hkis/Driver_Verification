"""
Typed domain data structures and models for RC Extractor
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from microservices.shared.models import OCRText


@dataclass
class Candidate:
    text: str
    ocr_box: OCRText
    label_box: OCRText
    spatial_score: float
    format_score: float
    vocab_bonus: float
    side_score: float
    label_score: float = 0.0
    total_score: float = 0.0
    relationship: str = "inline"
    margin: float = 0.0
    rejection_reason: Optional[str] = None


@dataclass
class ConfidenceSignals:
    raw_ocr_conf: float = 0.0
    label_match_score: float = 0.0
    spatial_score: float = 0.0
    format_validity_score: float = 0.0
    semantic_score: float = 0.0
    candidate_margin: float = 0.0
    cross_field_penalty: float = 0.0
    calibrated_confidence: float = 0.0


@dataclass
class FieldEvidence:
    field_name: str
    raw_text: str
    normalized_value: Optional[str] = None
    extraction_method: str = "label_spatial"  # "inline", "right", "below", "fallback", "form23"
    confidence_signals: ConfidenceSignals = field(default_factory=ConfidenceSignals)
    diagnostics: Optional[str] = None
