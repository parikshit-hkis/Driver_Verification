"""
Production Metrics & Observability for RC Service
"""

import time
import threading
from typing import Dict, Any, Optional
from microservices.shared.models import RCData


class RCMetrics:
    """Thread-safe metrics accumulator for RC Extraction operations."""

    def __init__(self):
        self._lock = threading.Lock()
        self.documents_processed: int = 0
        self.successful_extractions: int = 0
        self.partial_extractions: int = 0
        self.failed_extractions: int = 0
        self.empty_ocr_documents: int = 0
        self.total_latency_ms: float = 0.0
        self.field_stats: Dict[str, Dict[str, Any]] = {
            "registration_number": {"extracted": 0, "total_conf": 0.0, "conflicts": 0},
            "owner_name": {"extracted": 0, "total_conf": 0.0, "conflicts": 0},
            "vehicle_class": {"extracted": 0, "total_conf": 0.0, "conflicts": 0},
            "registration_date": {"extracted": 0, "total_conf": 0.0, "conflicts": 0},
            "fitness_expiry": {"extracted": 0, "total_conf": 0.0, "conflicts": 0},
        }

    def record_extraction(
        self,
        rc_data: RCData,
        latency_ms: float,
        is_empty_ocr: bool = False,
        had_conflict: bool = False,
    ) -> None:
        with self._lock:
            self.documents_processed += 1
            self.total_latency_ms += latency_ms

            if is_empty_ocr:
                self.empty_ocr_documents += 1
                self.failed_extractions += 1
                return

            has_reg = bool(rc_data.registration_number)
            has_owner = bool(rc_data.owner_name)
            has_class = bool(rc_data.vehicle_class)
            has_reg_date = bool(rc_data.registration_date)
            has_fit_exp = bool(rc_data.fitness_expiry)

            extracted_count = sum([has_reg, has_owner, has_class, has_reg_date, has_fit_exp])

            if extracted_count >= 4:
                self.successful_extractions += 1
            elif extracted_count > 0:
                self.partial_extractions += 1
            else:
                self.failed_extractions += 1

            for field_name in self.field_stats.keys():
                val = getattr(rc_data, field_name, None)
                conf = rc_data.confidence_scores.get(field_name, 0.0)
                if val:
                    self.field_stats[field_name]["extracted"] += 1
                    self.field_stats[field_name]["total_conf"] += conf

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            avg_latency = (
                round(self.total_latency_ms / self.documents_processed, 2)
                if self.documents_processed > 0
                else 0.0
            )

            fields_summary = {}
            for fname, stats in self.field_stats.items():
                ext = stats["extracted"]
                avg_c = round(stats["total_conf"] / ext, 2) if ext > 0 else 0.0
                ext_rate = (
                    round((ext / self.documents_processed) * 100, 1)
                    if self.documents_processed > 0
                    else 0.0
                )
                fields_summary[fname] = {
                    "extracted_count": ext,
                    "extraction_rate_pct": ext_rate,
                    "average_confidence": avg_c,
                    "conflict_count": stats["conflicts"],
                }

            success_rate = (
                round((self.successful_extractions / self.documents_processed) * 100, 1)
                if self.documents_processed > 0
                else 0.0
            )

            return {
                "documents_processed": self.documents_processed,
                "successful_extractions": self.successful_extractions,
                "partial_extractions": self.partial_extractions,
                "failed_extractions": self.failed_extractions,
                "empty_ocr_documents": self.empty_ocr_documents,
                "success_rate_pct": success_rate,
                "average_extraction_time_ms": avg_latency,
                "field_metrics": fields_summary,
            }

    def reset(self) -> None:
        with self._lock:
            self.documents_processed = 0
            self.successful_extractions = 0
            self.partial_extractions = 0
            self.failed_extractions = 0
            self.empty_ocr_documents = 0
            self.total_latency_ms = 0.0
            for stats in self.field_stats.values():
                stats["extracted"] = 0
                stats["total_conf"] = 0.0
                stats["conflicts"] = 0


rc_metrics = RCMetrics()
