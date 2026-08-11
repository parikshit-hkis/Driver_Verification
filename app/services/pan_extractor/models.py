from typing import Optional, Dict
from pydantic import BaseModel, Field


class PanData(BaseModel):
    pan_number: Optional[str] = None
    full_name: Optional[str] = None
    father_name: Optional[str] = None
    date_of_birth: Optional[str] = None

    # Per-field failure diagnostics: field_name -> reason string
    field_diagnostics: Dict[str, str] = Field(default_factory=dict)

    def display(self) -> str:
        fields = [
            ("PAN Number", "pan_number", self.pan_number),
            ("Full Name", "full_name", self.full_name),
            ("Father Name", "father_name", self.father_name),
            ("Date of Birth", "date_of_birth", self.date_of_birth),
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
