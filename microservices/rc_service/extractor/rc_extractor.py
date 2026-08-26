"""
Vehicle Registration Certificate (RC) Domain Extractor — Production Grade
========================================================================
Implements deterministic, resolution-independent label matching, OCR bounding-box
spatial reasoning, candidate margin scoring, calendar date validation, cross-field
consistency checks, and machine-readable explainability diagnostics.
"""

import re
import time
import logging
from datetime import datetime
from typing import List, Optional, Set, Tuple, Dict, Any
from rapidfuzz import fuzz

from microservices.shared.models import OCRResult, OCRText, RCData
from microservices.shared.utils import (
    BaseExtractor,
    normalize_date,
    normalize_rc_number,
)
from microservices.rc_service.config import rc_config
from microservices.rc_service.extractor.models import (
    Candidate,
    ConfidenceSignals,
    FieldEvidence,
)

logger = logging.getLogger("rc_service.extractor")

_EXPECTED_FIELD_SIDE = {
    "registration_number": "front",
    "owner_name": "front",
    "vehicle_class": "both",
    "registration_date": "front",
    "fitness_expiry": "front",
}


def _mask_pii(text: Optional[str]) -> str:
    """Mask sensitive names/text for logging."""
    if not text:
        return "<EMPTY>"
    text = text.strip()
    if len(text) <= 3:
        return "***"
    return text[0] + "***" + text[-1]


class RCExtractor(BaseExtractor):
    """Production-grade extractor for Indian RC documents."""

    def __init__(self):
        super().__init__()
        # Ensure configuration is verified
        self.config = rc_config

    def extract_rc(self, ocr_front: Optional[OCRResult], ocr_back: Optional[OCRResult]) -> RCData:
        """Extract structured data from front and optional back RC document images."""
        t0 = time.perf_counter()

        data_front = self._extract_side(ocr_front, side="front") if ocr_front else None
        data_back = self._extract_side(ocr_back, side="back") if ocr_back else None

        if data_front is None and data_back is None:
            data = RCData()
            self._generate_rc_diagnostics(data, [])
            return data

        if data_front is None:
            data = data_back
            combined_texts = ocr_back.texts if ocr_back else []
            self._apply_form23_validity_spans(data, combined_texts)
            self._apply_cross_field_sanity(data)
            self._calculate_overall_confidence(data)
            self._generate_rc_diagnostics(data, combined_texts)
            return data

        if data_back is None:
            data = data_front
            combined_texts = ocr_front.texts if ocr_front else []
            self._apply_form23_validity_spans(data, combined_texts)
            self._apply_cross_field_sanity(data)
            self._calculate_overall_confidence(data)
            self._generate_rc_diagnostics(data, combined_texts)
            return data

        merged = RCData()
        all_fields = [
            "registration_number", "owner_name", "vehicle_class", "registration_date",
            "fitness_expiry"
        ]

        # Merge front and back with side preference, vocabulary verification, and conflict detection
        for field_name in all_fields:
            pref_side = _EXPECTED_FIELD_SIDE.get(field_name, "front")
            val_front = getattr(data_front, field_name, None)
            val_back = getattr(data_back, field_name, None)

            conf_front = data_front.confidence_scores.get(field_name, 0.0)
            conf_back = data_back.confidence_scores.get(field_name, 0.0)

            if val_front and val_back and val_front.strip().upper() != val_back.strip().upper():
                conflict_msg = (
                    f"Front/Back conflict detected for {field_name}: "
                    f"front='{val_front}', back='{val_back}'"
                )
                logger.warning(conflict_msg)
                merged.field_diagnostics[f"{field_name}_conflict"] = conflict_msg

                if field_name == "vehicle_class":
                    f_in_vocab = val_front in self.config.vehicle_classes or self._normalize_vehicle_class(val_front) in self.config.vehicle_classes
                    b_in_vocab = val_back in self.config.vehicle_classes or self._normalize_vehicle_class(val_back) in self.config.vehicle_classes
                    if f_in_vocab and not b_in_vocab:
                        val, conf = val_front, conf_front
                    elif b_in_vocab and not f_in_vocab:
                        val, conf = val_back, conf_back
                    elif conf_front >= conf_back:
                        val, conf = val_front, conf_front
                    else:
                        val, conf = val_back, conf_back
                elif pref_side == "front":
                    val = val_front
                    conf = max(0.40, conf_front - 0.10)
                else:
                    val = val_back
                    conf = max(0.40, conf_back - 0.10)
            else:
                if field_name == "vehicle_class":
                    val = val_front if val_front is not None else val_back
                    conf = conf_front if val_front is not None else conf_back
                elif pref_side == "front":
                    val = val_front if val_front is not None else val_back
                    conf = conf_front if val_front is not None else conf_back
                else:
                    val = val_back if val_back is not None else val_front
                    conf = conf_back if val_back is not None else conf_front

            setattr(merged, field_name, val)    
            if val is not None and conf > 0.0:
                merged.confidence_scores[field_name] = round(conf, 2)

        combined_texts = []
        if ocr_front and ocr_front.texts:
            combined_texts.extend(ocr_front.texts)
        if ocr_back and ocr_back.texts:
            combined_texts.extend(ocr_back.texts)

        self._apply_form23_validity_spans(merged, combined_texts)
        self._apply_cross_field_sanity(merged)
        self._calculate_overall_confidence(merged)
        self._generate_rc_diagnostics(merged, combined_texts)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            f"RC extraction completed in {elapsed_ms:.1f}ms: reg={merged.registration_number}, "
            f"owner={_mask_pii(merged.owner_name)}, overall_conf={merged.overall_confidence}"
        )
        return merged

    def extract(self, ocr_result: OCRResult) -> RCData:
        """Extract structured RC data from a single OCR result payload."""
        t0 = time.perf_counter()
        data = self._extract_side(ocr_result, side="unknown")
        texts = ocr_result.texts if ocr_result else []
        if texts:
            self._apply_form23_validity_spans(data, texts)
        self._apply_cross_field_sanity(data)
        self._calculate_overall_confidence(data)
        self._generate_rc_diagnostics(data, texts)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(f"Single-image RC extraction completed in {elapsed_ms:.1f}ms")
        return data

    def _extract_side(self, ocr_result: Optional[OCRResult], side: str = "unknown") -> RCData:
        """Extract all candidate fields from one side with field-level isolation."""
        if not ocr_result or not ocr_result.texts:
            return RCData()

        texts = ocr_result.texts
        data = RCData()

        fields_to_extract = [
            "registration_number", "owner_name", "vehicle_class",
            "registration_date", "fitness_expiry"
        ]

        for f_name in fields_to_extract:
            try:
                val, conf = self._extract_field_with_confidence(texts, f_name, side)
                if val:
                    setattr(data, f_name, val)
                    data.confidence_scores[f_name] = round(conf, 2)
            except Exception as e:
                logger.error(f"Isolated error extracting field '{f_name}' on side '{side}': {e}", exc_info=True)
                data.field_diagnostics[f_name] = f"Extraction error: {str(e)}"

        self._calculate_overall_confidence(data)
        return data

    def _extract_field_with_confidence(
        self, texts: List[OCRText], field_name: str, side: str
    ) -> Tuple[Optional[str], float]:
        """Field-specific extraction dispatcher with multi-signal confidence scoring."""
        if field_name == "registration_number":
            reg_val, reg_conf = self._extract_registration_number_with_fallback(texts, side)
            if reg_val:
                return reg_val, reg_conf

        keywords = self._get_keywords_for_field(field_name)
        if not keywords:
            return None, 0.0

        allow_multiline = field_name == "owner_name"

        cand = self._get_best_candidate_for_keywords(
            texts=texts,
            keywords=keywords,
            field_type=field_name,
            side=side,
            allow_multiline=allow_multiline,
        )

        # Fallback to single-line if multiline candidate failed
        if not cand and field_name == "owner_name" and allow_multiline:
            cand = self._get_best_candidate_for_keywords(
                texts=texts,
                keywords=keywords,
                field_type=field_name,
                side=side,
                allow_multiline=False,
            )

        # Fallback to relation context for owner name (e.g. S/O, D/O, W/O)
        if not cand and field_name == "owner_name":
            relation_value, rel_conf = self._extract_owner_from_relation_context(texts)
            if relation_value:
                return relation_value.upper(), rel_conf

        if not cand:
            # Fallback: scan OCR text for known vehicle class patterns
            if field_name == "vehicle_class":
                fb_val, fb_conf = self._fallback_vehicle_class_scan(texts)
                if fb_val:
                    return fb_val, fb_conf
            return None, 0.0

        val = cand.text.strip()
        ocr_conf = cand.ocr_box.confidence if cand.ocr_box else 0.85

        # Compute calibrated confidence from multiple signals
        score_norm = self.config.scoring_weights.get("score_normalization_divisor", 140.0)
        ocr_weight = self.config.scoring_weights.get("ocr_weight_in_confidence", 0.55)
        score_weight = self.config.scoring_weights.get("score_weight_in_confidence", 0.45)

        score_conf = min(1.0, max(0.40, cand.total_score / score_norm))
        base_conf = (ocr_weight * ocr_conf) + (score_weight * score_conf)

        # Ambiguity penalty if candidate margin is narrow
        min_margin = self.config.scoring_weights.get("min_ambiguity_margin", 8.0)
        if cand.margin > 0 and cand.margin < min_margin:
            base_conf -= 0.08

        field_conf = round(min(0.99, max(0.30, base_conf)), 2)

        if field_name == "registration_number":
            norm = normalize_rc_number(re.sub(r"[\s\-]", "", val.upper()))
            if norm and self._is_valid_state_rc(norm):
                return norm, max(field_conf, 0.95)
            elif norm:
                return norm, field_conf
            return None, 0.0

        elif field_name == "owner_name":
            truncated = self._truncate_relation_marker(val)
            if self._is_plausible_owner_name(truncated):
                return truncated.upper(), field_conf
            return None, 0.0

        elif field_name in ("registration_date", "fitness_expiry"):
            norm_dt = normalize_date(val)
            if norm_dt and self._validate_rc_date(norm_dt):
                return norm_dt, max(field_conf, 0.92)
            elif norm_dt:
                return norm_dt, min(field_conf, 0.70)
            return None, 0.0

        elif field_name == "vehicle_class":
            cand_norm = self._normalize_vehicle_class(val)
            cand_is_valid = (
                cand_norm in self.config.vehicle_classes
                or val.upper().strip() in self.config.vehicle_classes
            ) and not self._is_body_type_value(cand_norm)

            fb_val, fb_conf = self._fallback_vehicle_class_scan(texts)

            if cand_is_valid:
                return cand_norm, max(field_conf, 0.92)
            elif fb_val:
                return fb_val, fb_conf
            elif not self._is_body_type_value(cand_norm) and not self._is_structural_label(cand_norm):
                if len(cand_norm) <= 35 and not re.search(r"\d{3,}", cand_norm) and not any(w in cand_norm for w in ["NAME", "CHASSIS", "ENGINE", "REGN", "DATE", "CARD", "ADDRESS"]):
                    return cand_norm, min(field_conf, 0.70)
            return None, 0.0

        return val.upper(), field_conf

    def _get_best_candidate_for_keywords(
        self,
        texts: List[OCRText],
        keywords: List[str],
        field_type: str,
        side: str,
        allow_multiline: bool = False,
    ) -> Optional[Candidate]:
        """Find matching label boxes and extract best candidate with margin computation."""
        label_boxes = self._find_all_matching_labels(texts, keywords)
        if not label_boxes:
            return None

        all_candidates: List[Candidate] = []
        scoring = self.config.scoring_weights

        for label_box in label_boxes:
            inline_val = self._extract_inline_value(label_box.text, keywords=keywords)
            if inline_val and not self._is_structural_label(inline_val):
                fmt_score, v_bonus = self._evaluate_candidate_format(inline_val, field_type)
                if fmt_score >= 0:
                    pref_side = _EXPECTED_FIELD_SIDE.get(field_type, "front")
                    side_score = scoring.get("side_match_bonus", 30.0) if (pref_side == "both" or side == pref_side or side == "unknown") else 0.0
                    inline_base = scoring.get("spatial_inline_base", 80.0)
                    ocr_scale = scoring.get("ocr_conf_scale", 10.0)
                    tot_score = inline_base + fmt_score + v_bonus + side_score + (ocr_scale * label_box.confidence)

                    cand_obj = Candidate(
                        text=inline_val,
                        ocr_box=label_box,
                        label_box=label_box,
                        spatial_score=inline_base,
                        format_score=fmt_score,
                        vocab_bonus=v_bonus,
                        side_score=side_score,
                        label_score=90.0,
                        total_score=tot_score,
                        relationship="inline",
                    )
                    all_candidates.append(cand_obj)

            cands = self._evaluate_candidates_for_label(
                texts, label_box, field_type, side, allow_multiline=allow_multiline
            )
            if cands:
                all_candidates.extend(cands)

        if not all_candidates:
            return None

        # Sort by total score descending
        all_candidates.sort(key=lambda c: c.total_score, reverse=True)
        top = all_candidates[0]

        min_score = scoring.get("min_candidate_score", 20.0)
        if top.total_score < min_score:
            return None

        # Compute margin against second distinct candidate
        if len(all_candidates) > 1:
            for second in all_candidates[1:]:
                if second.text.strip().upper() != top.text.strip().upper():
                    top.margin = top.total_score - second.total_score
                    break

        return top

    def _evaluate_candidates_for_label(
        self,
        texts: List[OCRText],
        label_box: OCRText,
        field_type: str,
        side: str,
        allow_multiline: bool = False,
    ) -> List[Candidate]:
        """Evaluate geometric candidates around a label box using resolution-independent metrics."""
        candidates: List[Candidate] = []
        spatial_p = self.config.spatial_params
        scoring = self.config.scoring_weights

        lx1, lx2 = label_box.bounding_box.min_x, label_box.bounding_box.max_x
        ly1, ly2 = label_box.bounding_box.min_y, label_box.bounding_box.max_y
        lcy = label_box.bounding_box.center_y
        l_height = max(15.0, label_box.bounding_box.height)
        label_center_x = (lx1 + lx2) / 2.0

        # Normalized resolution-independent tolerances
        same_row_tolerance = max(
            spatial_p.get("min_same_row_tolerance", 20.0),
            l_height * spatial_p.get("same_row_tolerance_factor", 0.9),
        )
        below_vertical_max = max(
            spatial_p.get("min_below_vertical_max", 140.0),
            l_height * spatial_p.get("below_vertical_max_factor", 4.5),
        )

        is_date_field = field_type.endswith("_date") or field_type.endswith("_expiry")
        if is_date_field:
            below_x_tolerance = max(
                spatial_p.get("min_date_below_x_tolerance", 60.0),
                l_height * spatial_p.get("date_below_x_tolerance_factor", 2.5),
            )
        else:
            below_x_tolerance = max(
                spatial_p.get("min_below_x_tolerance", 110.0),
                l_height * spatial_p.get("below_x_tolerance_factor", 5.0),
            )

        right_offset_min = max(
            spatial_p.get("min_right_offset", 8.0),
            l_height * spatial_p.get("right_offset_factor", 0.20),
        )

        for item in texts:
            if item is label_box or item.bounding_box.max_x < lx1 - 30.0:
                continue

            text_clean = self._clean_inline_value(item.text.strip())
            if not text_clean or self._is_structural_label(text_clean):
                continue

            icx = item.bounding_box.center_x
            icy = item.bounding_box.center_y
            ix1 = item.bounding_box.min_x
            iy1 = item.bounding_box.min_y
            ix2 = item.bounding_box.max_x
            iy2 = item.bounding_box.max_y

            right_of_label = ix1 >= lx2 - right_offset_min
            x_alignment = abs(icx - label_center_x)

            on_same_row = abs(icy - lcy) <= same_row_tolerance and right_of_label
            is_below = (
                iy1 >= ly2 - 5.0
                and (iy1 - ly2) <= below_vertical_max
                and x_alignment <= below_x_tolerance
            )
            is_above = (
                field_type == "vehicle_class"
                and ly1 >= iy2 - 5.0
                and (ly1 - iy2) <= below_vertical_max
                and x_alignment <= below_x_tolerance
            )

            if not on_same_row and not is_below and not is_above:
                continue

            relationship = "right" if on_same_row else ("below" if is_below else "above")
            merged_text = text_clean
            if allow_multiline:
                merged_text = self._merge_continuation_boxes(texts, item, relationship, field_type)

            if relationship == "right":
                dist = max(0.0, ix1 - lx2)
                base_right = scoring.get("spatial_right_base", 65.0)
                spatial_score = max(0.0, base_right - (dist / 3.5))
            elif relationship == "below":
                dist = max(0.0, iy1 - ly2)
                base_below = scoring.get("spatial_below_base", 55.0)
                max_align = scoring.get("spatial_col_align_max", 30.0)
                spatial_score = max(0.0, base_below - (dist / 3.0))
                col_align_bonus = max(0.0, max_align - (x_alignment / 3.0))
                spatial_score += col_align_bonus
            else:  # above
                dist = max(0.0, ly1 - iy2)
                base_above = scoring.get("spatial_below_base", 50.0)
                max_align = scoring.get("spatial_col_align_max", 30.0)
                spatial_score = max(0.0, base_above - (dist / 3.0))
                col_align_bonus = max(0.0, max_align - (x_alignment / 3.0))
                spatial_score += col_align_bonus

            pref_side = _EXPECTED_FIELD_SIDE.get(field_type, "front")
            side_bonus = scoring.get("side_match_bonus", 30.0)
            side_score = side_bonus if (pref_side == "both" or side == pref_side or side == "unknown") else 0.0

            fmt_score, v_bonus = self._evaluate_candidate_format(merged_text, field_type)
            if fmt_score < 0:
                continue

            ocr_scale = scoring.get("ocr_conf_scale", 10.0)
            total_score = spatial_score + fmt_score + v_bonus + side_score + (ocr_scale * item.confidence)
            candidates.append(
                Candidate(
                    text=merged_text,
                    ocr_box=item,
                    label_box=label_box,
                    spatial_score=spatial_score,
                    format_score=fmt_score,
                    vocab_bonus=v_bonus,
                    side_score=side_score,
                    total_score=total_score,
                    relationship=relationship,
                )
            )

        return candidates

    def _merge_continuation_boxes(
        self, texts: List[OCRText], start_item: OCRText, relationship: str, field_type: str
    ) -> str:
        """Merge horizontally aligned continuation boxes while preventing over-merging."""
        start_text = self._clean_inline_value(start_item.text.strip())
        if field_type == "owner_name" and any(c.isdigit() for c in start_text):
            return start_text

        spatial_p = self.config.spatial_params
        max_gap = spatial_p.get("max_continuation_gap", 130.0)
        h_factor = spatial_p.get("continuation_height_factor", 0.9)
        min_h_tol = spatial_p.get("min_continuation_height_tol", 18.0)
        max_words = spatial_p.get("max_owner_name_words", 5)

        merged_tokens = [start_text]
        curr = start_item

        # Find candidate boxes on the same horizontal band to the right of start_item
        row_boxes: List[OCRText] = []
        for other in texts:
            if other is start_item:
                continue
            h_tol = max(min_h_tol, start_item.bounding_box.height * h_factor)
            if abs(other.bounding_box.center_y - start_item.bounding_box.center_y) <= h_tol:
                if other.bounding_box.min_x >= start_item.bounding_box.min_x - 5.0:
                    row_boxes.append(other)

        # Sort horizontally by min_x
        row_boxes.sort(key=lambda b: b.bounding_box.min_x)

        for other in row_boxes:
            if other is curr or other.text.strip() in merged_tokens:
                continue
            o_text = self._clean_inline_value(other.text.strip())
            if not o_text:
                continue

            dist = other.bounding_box.min_x - curr.bounding_box.max_x
            if dist < 0:
                continue
            if dist > max_gap:
                break

            # Stop condition: structural label
            if self._is_structural_label(o_text):
                break

            # Stop condition: field keywords
            if any(lbl in o_text.upper() for lbl in [
                "REG.NO", "REG NO", "REGN", "OWNER", "CLASS", "ADDRESS", "VALIDITY", "MODEL",
                "MAKER", "ENGINE", "CHASSIS", "DATE", "SR.NO", "SR NO", "SIGN"
            ]):
                break

            # Stop condition: address blacklist keywords
            o_words = [w.upper() for w in re.findall(r"\b[A-Za-z]+\b", o_text)]
            if any(w in self.config.address_blacklist for w in o_words):
                break

            # Stop condition: digits in owner name
            if field_type == "owner_name" and any(c.isdigit() for c in o_text):
                break

            # Enforce max words
            proposed_words = (" ".join(merged_tokens) + " " + o_text).split()
            if field_type == "owner_name" and len(proposed_words) > max_words:
                break

            merged_tokens.append(o_text)
            curr = other

        return " ".join(merged_tokens)

    def _find_all_matching_labels(self, texts: List[OCRText], keywords: List[str]) -> List[OCRText]:
        """Find matching label OCR boxes sorted by match confidence with strict label disambiguation."""
        matches: List[Tuple[float, OCRText]] = []
        fuzzy_threshold = self.config.FUZZY_MATCH_THRESHOLD

        for kw in keywords:
            kw_clean = kw.upper().rstrip(":").rstrip(".").strip()
            for item in texts:
                t_clean = item.text.upper().strip().rstrip(":").rstrip(".").strip()

                # Disambiguate Date of Registration vs Validity/Expiry
                if any(w in kw_clean for w in ["VALIDITY", "VALID", "UPTO", "EXPIRY"]) and "DATE" in t_clean and not any(w in t_clean for w in ["VALIDITY", "VALID", "UPTO", "EXPIRY"]):
                    continue
                if "DATE" in kw_clean and any(w in t_clean for w in ["VALIDITY", "VALID", "UPTO", "EXPIRY"]) and "DATE" not in t_clean:
                    continue

                score = 0.0
                if t_clean == kw_clean:
                    score = 100.0
                elif t_clean.startswith(kw_clean) or kw_clean.startswith(t_clean):
                    if len(t_clean) == len(kw_clean) or t_clean[len(kw_clean):len(kw_clean)+1] in (" ", ":", "."):
                        score = 90.0

                if score == 0.0 and len(kw_clean) >= 4 and len(t_clean) >= 4:
                    ratio = fuzz.ratio(kw_clean, t_clean)
                    if ratio >= fuzzy_threshold:
                        score = ratio
                    else:
                        ts_ratio = fuzz.token_set_ratio(kw_clean, t_clean)
                        if ts_ratio >= fuzzy_threshold and abs(len(t_clean) - len(kw_clean)) <= 12:
                            score = ts_ratio

                if score > 0:
                    matches.append((score, item))

        matches.sort(key=lambda x: x[0], reverse=True)
        seen = set()
        unique: List[OCRText] = []
        for s, box in matches:
            b_id = id(box)
            if b_id not in seen:
                seen.add(b_id)
                unique.append(box)

        return unique

    def _is_structural_label(self, text: str) -> bool:
        """Determine if text is a known document/structural label to avoid extracting labels as values."""
        clean = text.upper().strip().rstrip(":").rstrip(".").strip()
        if not clean:
            return True
        if text.strip().endswith(":") and len(text.strip()) <= 35:
            return True

        fuzzy_threshold = self.config.FUZZY_MATCH_THRESHOLD
        for lbl in self.config.canonical_labels:
            lbl_clean = lbl.upper()
            if clean == lbl_clean or clean.startswith(lbl_clean + ":") or clean.startswith(lbl_clean + " "):
                return True
            if len(lbl_clean) >= 6 and len(clean) >= 4:
                if fuzz.token_set_ratio(lbl_clean, clean) >= fuzzy_threshold and abs(len(clean) - len(lbl_clean)) <= 15:
                    return True
                if fuzz.ratio(lbl_clean, clean) >= fuzzy_threshold:
                    return True
        return False

    def _extract_inline_value(self, text: str, keywords: Optional[List[str]] = None) -> Optional[str]:
        """Extract inline value from label text."""
        clean_text = text.strip()
        if ":" in clean_text:
            parts = clean_text.split(":", 1)
            val = parts[1].strip()
            if val and not self._is_structural_label(val):
                return val

        if keywords:
            text_up = clean_text.upper()
            for kw in keywords:
                kw_clean = kw.upper().rstrip(":").rstrip(".").strip()
                if text_up.startswith(kw_clean) and len(text_up) > len(kw_clean):
                    sep = text_up[len(kw_clean):len(kw_clean)+1]
                    if sep in (":", "-", " ", "."):
                        val = clean_text[len(kw_clean):].strip().lstrip(":").lstrip("-").lstrip(".").strip()
                        if val and not self._is_structural_label(val):
                            val_up = val.upper()
                            if not any(val_up.startswith(p) for p in ["'S", "OF ", "NAME", "NO.", "NUMBER", "DATE"]):
                                return val
        return None

    def _clean_inline_value(self, text: str) -> str:
        """Strip preceding label if separated by colon."""
        if ":" in text:
            parts = text.split(":", 1)
            if self._is_structural_label(parts[0]):
                return parts[1].strip()
        return text

    def _evaluate_candidate_format(self, text: str, field_type: str) -> Tuple[float, float]:
        """Evaluate candidate against field format and schema rules."""
        clean_up = text.upper().strip()
        cleaned_nodash = re.sub(r"[\s\-]", "", clean_up)

        if field_type in ("owner_name", "vehicle_class"):
            if normalize_date(text):
                return (-100.0, 0.0)
            if 8 <= len(cleaned_nodash) <= 11 and normalize_rc_number(cleaned_nodash):
                return (-100.0, 0.0)

        if field_type == "registration_number":
            norm = normalize_rc_number(cleaned_nodash)
            if norm:
                if self._is_valid_state_rc(norm):
                    return (60.0, 0.0)
                return (40.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "owner_name":
            truncated = self._truncate_relation_marker(text)
            if self._is_plausible_owner_name(truncated):
                return (50.0, 0.0)
            return (-100.0, 0.0)

        elif field_type == "vehicle_class":
            if self._is_body_type_value(clean_up):
                return (-100.0, 0.0)
            if normalize_date(text):
                return (-100.0, 0.0)
            if re.search(r"\d{4,}", clean_up):
                return (-100.0, 0.0)
            if self._is_structural_label(clean_up):
                return (-100.0, 0.0)
            if any(w in clean_up for w in [
                "VALIDITY", "CYLINDER", "REGISTRATION", "CERTIFICATE", "GOVERNMENT",
                "DEPARTMENT", "NAME", "AUTHORITY", "CARD", "ISSUE", "SERIAL",
                "WEIGHT", "CAPACITY", "WHEELBASE", "FINANCIER", "SIGN", "SON",
                "DAUGHTER", "WIFE", "ADDRESS", "STAGE", "FUEL", "PETROL", "DIESEL", "CNG"
            ]):
                return (-100.0, 0.0)
            if len(clean_up) <= 50:
                norm_vc = self._normalize_vehicle_class(clean_up)
                vocab_bonus = 40.0 if (clean_up in self.config.vehicle_classes or norm_vc in self.config.vehicle_classes) else 0.0
                return (50.0, vocab_bonus)
            return (-100.0, 0.0)

        elif field_type in ("registration_date", "fitness_expiry"):
            norm_dt = normalize_date(text)
            if norm_dt and self._validate_rc_date(norm_dt):
                return (60.0, 0.0)
            return (-100.0, 0.0)

        return (10.0, 0.0)

    def _is_valid_state_rc(self, rc_num: str) -> bool:
        """Validate if RC number has a recognized state code or BH series."""
        cleaned = re.sub(r"[^A-Z0-9]", "", rc_num.upper())
        if re.match(r"^\d{2}BH", cleaned):
            return True
        prefix = cleaned[:2]
        return prefix in self.config.state_codes

    def _validate_rc_date(self, date_str: str) -> bool:
        """Validate calendar date correctness and reasonable year range (1960 to 2050)."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return 1960 <= dt.year <= 2050
        except (ValueError, TypeError):
            return False

    def _truncate_relation_marker(self, text: str) -> str:
        """Truncate relation marker patterns (S/O, D/O, W/O, C/O, etc.)."""
        result = text.strip()
        for pat in self.config.RELATION_PATTERNS:
            m = pat.search(result)
            if m:
                result = result[:m.start()].strip()
                break
        return result

    def _is_plausible_owner_name(self, text: str) -> bool:
        """Validate if candidate text is a plausible owner name."""
        text = self._truncate_relation_marker(text.strip())
        if not text or any(c.isdigit() for c in text):
            return False

        text_up = text.upper()
        if text_up in self.config.vehicle_classes:
            return False

        # Check against address blacklist keywords
        words = text_up.split()
        if any(w in self.config.address_blacklist for w in words):
            return False

        # Check against labels / structural tokens
        if any(lbl in text_up for lbl in [
            "REG.NO", "REG NO", "REGN", "REGD", "REGISTRATION",
            "SR.NO", "SR NO", "SERIAL", "SIGN", "SIGNATURE",
            "CHASSIS", "ENGINE", "MODEL", "MAKER", "FORM", "VALIDITY", "CYLINDER",
            "FITNESS", "INSURANCE", "AUTHORITY", "DEPARTMENT", "GOVERNMENT",
            "NAME", "OWNER", "'S"
        ]):
            return False

        if len(words) < 1 or len(words) > 5:
            return False

        for w in words:
            # Allow common name punctuation like dots, apostrophes, hyphens
            w_clean = w.replace(".", "").replace("'", "").replace("-", "")
            if not w_clean.isalpha():
                return False

        return not self._is_structural_label(text)

    def _get_keywords_for_field(self, field_name: str) -> List[str]:
        """Return keyword search labels for a given RC field."""
        mapping = {
            "registration_number": [
                "Registration No", "Registration Number", "Regn.No", "Regn.Number",
                "Reg.No", "Regn No", "Regd No", "Reg No", "Rexn.Number", "Veh Reg No",
                "Vehicle Reg No", "Reg. No.", "Regn. No.", "Vehicle Regn No",
            ],
            "owner_name": [
                "Name of Owner", "Owner Name", "Owner's Name", "Registered Owner",
                "Regn Owner", "Vehicle Owner", "Name of Registered Owner",
                "Name of Regd Owner", "Owner", "Name",
            ],
            "vehicle_class": [
                "Vehicle Class", "Class of Vehicle", "Veh Class", "Vehicle Type",
                "Type of Vehicle", "Type of Veh", "Veh Type", "Class",
                "Veh. Class", "Veh.Class", "Vehicle Category", "Veh Catg",
                "Class/Type", "Description of Vehicle", "Vehicle CIass", "Veh CIass",
                "Vehide Class", "VencdeClass", "Venide Cass", "Vencde Class"
            ],
            "registration_date": [
                "Registration Date", "Date of Registration", "Date of Reg.", "Reg Date",
                "Regn Date", "Date of Regn.", "Date of Regn", "Reg. Date", "Regn. Date",
                "Date of Reg",
            ],
            "fitness_expiry": [
                "Registration Validity", "Regn.Validity", "Regn. Validity", "Registration Upto",
                "Regn Upto", "Fitness UpTo", "Fitness Upto", "Registration Valid Upto",
                "Regn Valid Till", "Fitness Validity", "Validity Upto", "Validity",
                "Valid Upto", "Valid Till", "Valid Until", "Expiry Date", "Reg Validity",
                "Reg. Validity", "Reg Valid Upto",
            ],
        }
        return mapping.get(field_name, [])

    def _extract_owner_from_relation_context(self, texts: List[OCRText]) -> Tuple[Optional[str], float]:
        """Fallback extraction for owner name directly from S/O, D/O, W/O label boxes."""
        relation_kw = ["Son/Daughter/Wife of", "Son/Wife/Daughter of", "S/O", "D/O", "W/O", "C/O"]
        cand = self._get_best_candidate_for_keywords(
            texts=texts, keywords=relation_kw, field_type="owner_name", side="front", allow_multiline=False
        )
        if cand:
            truncated = self._truncate_relation_marker(cand.text)
            if self._is_plausible_owner_name(truncated):
                return truncated, 0.85
        return None, 0.0

    # ── Body-Type Rejection & Vehicle-Class Fallback ──────────────────────────

    _BODY_TYPE_VALUES = {
        "BOLTED ON FRAME", "WELDED", "MONOCOQUE", "OPEN BODY", "CLOSED BODY",
        "CONVERTIBLE", "RIGID", "ARTICULATED", "TANKER", "TIPPER",
        "PANEL VAN", "TRUCK", "HALF BODY", "FULL BODY", "PICK UP",
        "PLATFORM", "FLAT BED", "CHASSIS ONLY", "CABIN CHASSIS",
        "SOLO", "SOLO+PILL.RIDER", "SOLO WITH PILLION", "SOLOWITHPILLION",
    }

    _BODY_TYPE_FRAGMENTS = [
        "BOLTED", "WELDED", "MONOCOQUE", "ON FRAME",
    ]

    def _is_body_type_value(self, text: str) -> bool:
        """Check if the value looks like a body-type description rather than a vehicle class."""
        clean = text.strip().lstrip("/").strip().upper()
        if clean in self._BODY_TYPE_VALUES:
            return True
        for frag in self._BODY_TYPE_FRAGMENTS:
            if frag in clean:
                return True
        return False

    # Regex to match inline "Vehicle Class: <VALUE>" in OCR text
    _VEHICLE_CLASS_INLINE_RE = re.compile(
        r"(?:VEHICLE\s*C[LI1]ASS|CLASS\s*OF\s*VEHICLE|VEH[A-Z0-9\.\s]*C[LI1]ASS|VENCDE\s*CLASS|VEHIDE\s*CLASS|VEH[A-Z0-9\.\s]*CARR[A-Z]*)\s*[:;.\-]?\s*(.+)",
        re.IGNORECASE,
    )

    def _normalize_vehicle_class(self, text: str) -> str:
        """Clean and normalize vehicle class strings and fix common OCR anomalies."""
        cleaned = text.strip().lstrip("/").rstrip(":").strip().upper()
        # Fix missing closing parenthesis e.g. (3WT -> (3WT)
        if cleaned.count("(") > cleaned.count(")"):
            cleaned += ")" * (cleaned.count("(") - cleaned.count(")"))
        elif cleaned.count(")") > cleaned.count("("):
            # Fix missing opening parenthesis e.g. THREE WHEELER PASSENGER)(3WT)
            cleaned = re.sub(r"\bPASSENGER\)\(", "(PASSENGER) (", cleaned)

        # Standardize 3-wheeler variants
        if cleaned.startswith("HREEWHEELER") or cleaned.startswith("HREE WHEELER"):
            cleaned = "T" + cleaned
        elif cleaned.startswith("THREEWHEELER"):
            cleaned = "THREE WHEELER" + cleaned[12:]
        elif cleaned.startswith("3WHEELER"):
            cleaned = "3 WHEELER" + cleaned[8:]

        # Standardize 2-wheeler typos
        if "M-.YDE" in cleaned or "H-CYCLE" in cleaned:
            cleaned = cleaned.replace("M-.YDE", "M-CYCLE").replace("H-CYCLE", "M-CYCLE")
        if cleaned.startswith("JOTOR") or cleaned.startswith("NOTOR"):
            cleaned = "M" + cleaned[1:]
        if cleaned == "NOTORCYCLE":
            cleaned = "MOTORCYCLE"
        if cleaned == "SOLOPILL.RIDER":
            cleaned = "SOLO+PILL.RIDER"

        # Standardize carrier typos
        if "CARRER" in cleaned:
            cleaned = cleaned.replace("CARRER", "CARRIER")

        return cleaned

    def _fallback_vehicle_class_scan(self, texts: List[OCRText]) -> Tuple[Optional[str], float]:
        """
        Fallback scanner for vehicle class when label-based extraction fails.
        Strategy:
          1. Look for inline pattern 'Vehicle Class: <value>' in any OCR box.
          2. Scan all OCR text for known vehicle class vocabulary matches with strict word boundary validation.
        """
        # Strategy 1: Inline regex on individual OCR boxes
        stop_words = [
            "Maker", "Model", "Colour", "Color", "Regn", "Seating", "Form", "Unladen",
            "Fuel", "Owner", "Son", "Address", "Date", "Chassis", "Engine", "Emission",
            "Certificate", "Government", "Bharat", "Stage", "Norms", "Validity"
        ]

        for item in texts:
            m = self._VEHICLE_CLASS_INLINE_RE.search(item.text)
            if m:
                raw = m.group(1).strip().rstrip(":").strip()
                for stop in stop_words:
                    idx = raw.upper().find(stop.upper())
                    if idx > 0:
                        raw = raw[:idx].strip().rstrip(",").rstrip(":").strip()
                        break
                if raw and len(raw) <= 45 and not self._is_body_type_value(raw) and not self._is_structural_label(raw):
                    clean = self._normalize_vehicle_class(raw)
                    conf = 0.95 if clean in self.config.vehicle_classes else 0.88
                    return clean, conf

        # Strategy 2: Concatenated text regex
        full = " ".join(t.text for t in texts)
        m = self._VEHICLE_CLASS_INLINE_RE.search(full)
        if m:
            raw = m.group(1).strip()
            for stop in stop_words:
                idx = raw.upper().find(stop.upper())
                if idx > 0:
                    raw = raw[:idx].strip().rstrip(",").rstrip(":").strip()
                    break
            if raw and len(raw) <= 45 and not self._is_body_type_value(raw) and not self._is_structural_label(raw):
                clean = self._normalize_vehicle_class(raw)
                if clean in self.config.vehicle_classes:
                    return clean, 0.92

        # Strategy 3: Direct vocabulary scan with strict word boundaries and blacklist
        blacklist_headers = [
            "CARD", "CERTIFICATE", "DEPARTMENT", "GOVERNMENT", "AUTHORITY",
            "REGISTRATION", "NAME OF", "DATE OF", "SIGNATURE", "CHASSIS",
            "ENGINE", "EMISSION", "ADDRESS", "OWNER", "SON/", "WIFE/", "DAUGHTER/",
            "FUEL", "PETROL", "DIESEL", "CNG"
        ]

        for item in texts:
            text_up = item.text.strip().upper()
            if any(h in text_up for h in blacklist_headers) or re.search(r"\d{4,}", text_up):
                continue
            norm_item = self._normalize_vehicle_class(text_up)

            if norm_item in self.config.vehicle_classes:
                return norm_item, 0.90

            # Match compound vehicle classes with word boundary
            for vc in sorted(self.config.vehicle_classes, key=len, reverse=True):
                if len(vc) >= 4 and not self._is_body_type_value(text_up):
                    if re.search(r"(?<![A-Z0-9])" + re.escape(vc) + r"(?![A-Z0-9])", norm_item):
                        return vc, 0.88

        return None, 0.0

    def _apply_form23_validity_spans(self, data: RCData, texts: List[OCRText]) -> None:
        """Extract and apply Form 23 'valid from X to Y' date spans."""
        if not texts:
            return
        full_text = " ".join(t.text for t in texts)
        m = self.config.VALIDITY_SPAN_REGEX.search(full_text)
        if m:
            start_date = normalize_date(m.group(1))
            end_date = normalize_date(m.group(2))

            if start_date and self._validate_rc_date(start_date):
                if not data.registration_date:
                    data.registration_date = start_date
                    data.confidence_scores["registration_date"] = 0.94
            if end_date and self._validate_rc_date(end_date):
                if not data.fitness_expiry:
                    data.fitness_expiry = end_date
                    data.confidence_scores["fitness_expiry"] = 0.94

    def _extract_registration_number_with_fallback(
        self, texts: List[OCRText], side: str
    ) -> Tuple[Optional[str], float]:
        """Extract RC number with spatial label priority followed by regex scanning fallbacks."""
        label_keywords = self._get_keywords_for_field("registration_number")
        cand = self._get_best_candidate_for_keywords(
            texts, label_keywords, field_type="registration_number", side=side
        )
        if cand:
            norm = normalize_rc_number(re.sub(r"[\s\-]", "", cand.text.upper()))
            if norm and self._is_valid_state_rc(norm):
                ocr_conf = cand.ocr_box.confidence if cand.ocr_box else 0.90
                conf = min(0.98, max(0.85, 0.60 * ocr_conf + 0.38))
                return norm, round(conf, 2)
            elif norm:
                return norm, 0.90

        # Fallback 1: Direct item regex scan
        for item in texts:
            m = self.config.RC_REGEX.search(item.text)
            if m:
                norm = normalize_rc_number(m.group(1))
                if norm and self._is_valid_state_rc(norm):
                    conf = min(0.95, max(0.80, 0.50 * item.confidence + 0.45))
                    return norm, round(conf, 2)
                elif norm:
                    return norm, 0.85

        # Fallback 2: Concatenated text regex scan
        full = " ".join(t.text.upper() for t in texts)
        m = self.config.RC_REGEX.search(full)
        if m:
            norm = normalize_rc_number(m.group(1))
            if norm and self._is_valid_state_rc(norm):
                return norm, 0.88
            elif norm:
                return norm, 0.80

        return None, 0.0

    def _apply_cross_field_sanity(self, data: RCData) -> None:
        """Cross-validate extracted fields against consistency and schema rules."""
        # 1. Owner name sanity check
        if data.owner_name:
            if (
                self._is_structural_label(data.owner_name)
                or data.owner_name in self.config.vehicle_classes
            ):
                data.field_diagnostics["owner_name_invalid"] = (
                    f"Owner name rejected by cross-field sanity check: '{data.owner_name}'"
                )
                data.owner_name = None
                data.confidence_scores.pop("owner_name", None)

        # 2. Chronological date check (registration_date <= fitness_expiry)
        if data.registration_date and data.fitness_expiry:
            try:
                dt_reg = datetime.strptime(data.registration_date, "%Y-%m-%d")
                dt_exp = datetime.strptime(data.fitness_expiry, "%Y-%m-%d")
                if dt_reg > dt_exp:
                    data.field_diagnostics["date_anomaly"] = (
                        f"Chronological anomaly: registration_date ({data.registration_date}) "
                        f"is after fitness_expiry ({data.fitness_expiry})"
                    )
                    # Apply confidence penalty
                    if "registration_date" in data.confidence_scores:
                        data.confidence_scores["registration_date"] = max(
                            0.40, round(data.confidence_scores["registration_date"] - 0.15, 2)
                        )
                    if "fitness_expiry" in data.confidence_scores:
                        data.confidence_scores["fitness_expiry"] = max(
                            0.40, round(data.confidence_scores["fitness_expiry"] - 0.15, 2)
                        )
            except Exception:
                pass

    def _calculate_overall_confidence(self, data: RCData) -> None:
        """Compute mean confidence across extracted fields."""
        scores = [v for k, v in data.confidence_scores.items() if getattr(data, k, None) is not None]
        data.overall_confidence = round(sum(scores) / len(scores), 2) if scores else 0.0

    def _generate_rc_diagnostics(self, data: RCData, texts: List[OCRText]) -> None:
        """Generate human and machine-readable explainability diagnostics."""
        if not texts:
            for field in [
                "registration_number", "owner_name", "vehicle_class",
                "registration_date", "fitness_expiry"
            ]:
                data.field_diagnostics[field] = "OCR returned no text from document image"
            return

        if not data.registration_number:
            data.field_diagnostics["registration_number"] = "No valid Indian RC number pattern found in OCR text"
        if not data.owner_name:
            data.field_diagnostics["owner_name"] = "No plausible owner name found near relevant label"
        if not data.vehicle_class:
            data.field_diagnostics["vehicle_class"] = "No vehicle type/class detected near label"
        if not data.registration_date:
            data.field_diagnostics["registration_date"] = "No registration date detected"
        if not data.fitness_expiry:
            data.field_diagnostics["fitness_expiry"] = "No validity/fitness expiry date detected"
