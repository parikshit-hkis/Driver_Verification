from typing import Optional
from pydantic import BaseModel


class PanData(BaseModel):
    # PAN number
    pan_number: Optional[str] = None   # AAAAA9999A format

    # Name
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None

    # Father's / Parent's name
    father_name: Optional[str] = None

    # Date of birth
    dob: Optional[str] = None          # ISO YYYY-MM-DD

    def display(self) -> str:
        lines = [
            f"  {'PAN Number':<20}: {self.pan_number or '—'}",
            f"  {'Full Name':<20}: {self.full_name or '—'}",
            f"  {'First Name':<20}: {self.first_name or '—'}",
            f"  {'Middle Name':<20}: {self.middle_name or '—'}",
            f"  {'Last Name':<20}: {self.last_name or '—'}",
            f"  {'Father Name':<20}: {self.father_name or '—'}",
            f"  {'Date of Birth':<20}: {self.dob or '—'}",
        ]
        return "\n".join(lines)
