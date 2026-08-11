
from typing import Optional, Dict
from pydantic import BaseModel, Field


class RCData(BaseModel):
    registration_number: Optional[str] = None    # Registration No
    owner_name: Optional[str] = None             # Owner Name
    vehicle_type: Optional[str] = None           # Vehicle Type
    date_of_registration: Optional[str] = None   # Date of Registration
    registration_validity: Optional[str] = None  # Registration Validity / Expiry Date

    # Confidence & Uncertainty Output Metrics
    confidence_scores: Dict[str, float] = Field(default_factory=dict)
    overall_confidence: float = 0.0

    # Per-field failure diagnostics: field_name -> reason string
    field_diagnostics: Dict[str, str] = Field(default_factory=dict)

    def _fmt_conf(self, field_name: str) -> str:
        score = self.confidence_scores.get(field_name)
        if score is None or getattr(self, field_name) is None:
            return "—"
        pct = int(score * 100)
        if score >= 0.85:
            rating = "HIGH"
        elif score >= 0.65:
            rating = "MEDIUM"
        else:
            rating = "LOW / UNCERTAIN"
        return f"{pct}% {rating}"

    def display(self) -> str:
        fields = [
            ("Registration No", "registration_number"),
            ("Owner Name", "owner_name"),
            ("Date of Registration", "date_of_registration"),
            ("Registration Validity", "registration_validity"),
        ]
        lines = []
        for label, key in fields:
            value = getattr(self, key)
            conf = self._fmt_conf(key)
            if value:
                lines.append(f"  {label:<24}: {value:<28} [{conf}]")
            else:
                reason = self.field_diagnostics.get(key, "")
                if reason:
                    lines.append(f"  {label:<24}: {'—':<28} [{conf}]  [!] {reason}")
                else:
                    lines.append(f"  {label:<24}: {'—':<28} [{conf}]")
        lines.append(f"  {'Overall Confidence':<24}: {f'{int(self.overall_confidence * 100)}%' if self.overall_confidence else '—'}")
        return "\n".join(lines)
