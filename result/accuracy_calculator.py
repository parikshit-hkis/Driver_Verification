"""
Accuracy Calculator & Summary Dashboard
========================================
Calculates field-level, document-level, and driver-level extraction accuracy
percentages across all processed documents without modifying core app code.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from app.models.driver_models import DriverVerificationResult, DocumentExtractionResult


@dataclass
class DocumentAccuracyStats:
    doc_type_label: str
    total_docs: int = 0
    fully_extracted_docs: int = 0
    total_expected_fields: int = 0
    successfully_extracted_fields: int = 0
    field_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # field_name -> {"expected": int, "extracted": int}

    @property
    def field_accuracy_pct(self) -> float:
        if self.total_expected_fields == 0:
            return 0.0
        return (self.successfully_extracted_fields / self.total_expected_fields) * 100.0

    @property
    def doc_completion_pct(self) -> float:
        if self.total_docs == 0:
            return 0.0
        return (self.fully_extracted_docs / self.total_docs) * 100.0


@dataclass
class OverallAccuracyReport:
    total_drivers: int = 0
    fully_extracted_drivers: int = 0
    total_documents: int = 0
    fully_extracted_documents: int = 0
    total_expected_fields: int = 0
    successfully_extracted_fields: int = 0
    doc_stats: Dict[str, DocumentAccuracyStats] = field(default_factory=dict)
    failure_reasons: Dict[str, int] = field(default_factory=dict)

    @property
    def overall_accuracy_pct(self) -> float:
        if self.total_expected_fields == 0:
            return 0.0
        return (self.successfully_extracted_fields / self.total_expected_fields) * 100.0

    @property
    def overall_doc_completion_pct(self) -> float:
        if self.total_documents == 0:
            return 0.0
        return (self.fully_extracted_documents / self.total_documents) * 100.0


class AccuracyCalculator:
    """Evaluates DriverVerificationResult objects and generates accuracy statistics."""

    # Mandatory fields expected per document type
    DOC_EXPECTED_FIELDS = {
        "AADHAAR": ["aadhaar_number", "full_name", "date_of_birth", "gender"],
        "LICENCE": ["licence_number", "full_name", "date_of_birth", "issue_date", "expiry_date", "vehicle_classes"],
        "PAN": ["pan_number", "full_name", "father_name", "date_of_birth"],
        "RC": ["registration_number", "owner_name", "date_of_registration", "registration_validity"],
    }

    def evaluate_driver_results(self, driver_results: List[DriverVerificationResult]) -> OverallAccuracyReport:
        report = OverallAccuracyReport(total_drivers=len(driver_results))

        for label in self.DOC_EXPECTED_FIELDS.keys():
            expected_fields = self.DOC_EXPECTED_FIELDS[label]
            report.doc_stats[label] = DocumentAccuracyStats(
                doc_type_label=label,
                field_counts={f: {"expected": 0, "extracted": 0} for f in expected_fields}
            )

        for driver_res in driver_results:
            driver_all_perfect = True
            driver_doc_count = 0

            doc_mapping = [
                ("AADHAAR", driver_res.aadhaar_result),
                ("LICENCE", driver_res.licence_result),
                ("PAN", driver_res.pan_result),
                ("RC", driver_res.rc_result),
            ]

            for doc_label, doc_res in doc_mapping:
                if doc_res is None or doc_res.status == "MISSING":
                    continue

                driver_doc_count += 1
                stats = report.doc_stats[doc_label]
                stats.total_docs += 1
                report.total_documents += 1

                expected_fields = self.DOC_EXPECTED_FIELDS[doc_label]
                doc_all_fields_ok = True

                for field_name in expected_fields:
                    stats.total_expected_fields += 1
                    report.total_expected_fields += 1
                    stats.field_counts[field_name]["expected"] += 1

                    has_val = False
                    if doc_res.data is not None:
                        val = getattr(doc_res.data, field_name, None)
                        if val is not None and val != "" and val != []:
                            has_val = True

                    if has_val:
                        stats.successfully_extracted_fields += 1
                        report.successfully_extracted_fields += 1
                        stats.field_counts[field_name]["extracted"] += 1
                    else:
                        doc_all_fields_ok = False
                        driver_all_perfect = False

                        # Record failure reason
                        diag_reason = "Unextracted detail"
                        if doc_res.data is not None and hasattr(doc_res.data, "field_diagnostics"):
                            diag_reason = doc_res.data.field_diagnostics.get(field_name, diag_reason)

                        report.failure_reasons[diag_reason] = report.failure_reasons.get(diag_reason, 0) + 1

                if doc_all_fields_ok:
                    stats.fully_extracted_docs += 1
                    report.fully_extracted_documents += 1

            if driver_doc_count > 0 and driver_all_perfect:
                report.fully_extracted_drivers += 1

        return report

    @staticmethod
    def format_dashboard(report: OverallAccuracyReport) -> str:
        """Renders a beautiful ASCII dashboard summary of extraction accuracy."""
        lines = []
        bar_len = 35

        def make_bar(pct: float) -> str:
            filled = int(round((pct / 100.0) * bar_len))
            return f"[{'=' * filled}{' ' * (bar_len - filled)}] {pct:5.1f}%"

        lines.append("")
        lines.append("=" * 65)
        lines.append("        DRIVER DOCUMENT EXTRACTION ACCURACY REPORT        ")
        lines.append("=" * 65)
        lines.append(f"  Processed Drivers     : {report.total_drivers}")
        lines.append(f"  Total Document Cards  : {report.total_documents}")
        lines.append(f"  Total Expected Fields : {report.total_expected_fields}")
        lines.append(f"  Extracted Fields      : {report.successfully_extracted_fields} / {report.total_expected_fields}")
        lines.append("-" * 65)
        lines.append(f"  OVERALL ACCURACY      : {make_bar(report.overall_accuracy_pct)}")
        lines.append(f"  DOC COMPLETION RATE   : {make_bar(report.overall_doc_completion_pct)}")
        lines.append("=" * 65)
        lines.append("  DOCUMENT BREAKDOWN:")

        for doc_label, stats in report.doc_stats.items():
            lines.append(f"\n  [{doc_label}]")
            lines.append(f"    Cards Processed   : {stats.total_docs}")
            lines.append(f"    Field Accuracy    : {make_bar(stats.field_accuracy_pct)} ({stats.successfully_extracted_fields}/{stats.total_expected_fields})")
            lines.append(f"    Doc Completion    : {make_bar(stats.doc_completion_pct)} ({stats.fully_extracted_docs}/{stats.total_docs})")
            lines.append("    Field Breakdown   :")
            for fname, counts in stats.field_counts.items():
                exp = counts["expected"]
                ext = counts["extracted"]
                fpct = (ext / exp * 100.0) if exp > 0 else 0.0
                status_icon = "[OK]" if ext == exp else "[!]"
                lines.append(f"      {status_icon} {fname:<22}: {ext:2d}/{exp:2d} ({fpct:5.1f}%)")

        if report.failure_reasons:
            lines.append("\n" + "-" * 65)
            lines.append("  UNEXTRACTED FIELD DIAGNOSTICS:")
            for reason, cnt in sorted(report.failure_reasons.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"    - [{cnt}x] {reason}")

        lines.append("=" * 65)
        lines.append("")

        return "\n".join(lines)
