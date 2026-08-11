from typing import Optional, Dict
from pydantic import BaseModel, Field


class AadhaarData(BaseModel):
    aadhaar_number: Optional[str] = None
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None

    # Per-field failure diagnostics: field_name -> reason string
    field_diagnostics: Dict[str, str] = Field(default_factory=dict)

    def display(self) -> str:
        """Pretty formatted string for console output."""
        fields = [
            ("Aadhaar Number", "aadhaar_number", self.aadhaar_number),
            ("Full Name", "full_name", self.full_name),
            ("Date of Birth", "date_of_birth", self.date_of_birth),
            ("Gender", "gender", self.gender),
        ]
        lines = []
        for label, key, value in fields:
            if value:
                lines.append(f"  {label:<20}: {value}")
            else:
                reason = self.field_diagnostics.get(key, "")
                if reason:
                    lines.append(f"  {label:<20}: —  [!] {reason}")
                else:
                    lines.append(f"  {label:<20}: —")
        return "\n".join(lines)