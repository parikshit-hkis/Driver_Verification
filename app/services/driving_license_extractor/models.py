from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class DrivingLicenceData(BaseModel):
    licence_number: Optional[str] = None
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    vehicle_classes: List[str] = []

    # Per-field failure diagnostics: field_name -> reason string
    field_diagnostics: Dict[str, str] = Field(default_factory=dict)

    def display(self) -> str:
        vc = ", ".join(self.vehicle_classes) if self.vehicle_classes else None
        fields = [
            ("Licence Number", "licence_number", self.licence_number),
            ("Full Name", "full_name", self.full_name),
            ("Date of Birth", "date_of_birth", self.date_of_birth),
            ("Issue Date", "issue_date", self.issue_date),
            ("Expiry Date", "expiry_date", self.expiry_date),
            ("Vehicle Classes", "vehicle_classes", vc),
        ]
        lines = []
        for label, key, value in fields:
            if value:
                lines.append(f"  {label:<22}: {value}")
            else:
                reason = self.field_diagnostics.get(key, "")
                if reason:
                    lines.append(f"  {label:<22}: —  [!] {reason}")
                else:
                    lines.append(f"  {label:<22}: —")
        return "\n".join(lines)
