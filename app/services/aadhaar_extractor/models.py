from typing import Optional
from pydantic import BaseModel


class AadhaarData(BaseModel):
    # Aadhaar number
    aadhaar_number: Optional[str] = None

    # Name
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None

    # Personal details
    dob: Optional[str] = None          # ISO YYYY-MM-DD
    gender: Optional[str] = None       # MALE / FEMALE / TRANSGENDER

    # Address (from back side)
    address: Optional[str] = None

    def display(self) -> str:
        """Pretty formatted string for console output."""
        lines = [
            f"  {'Aadhaar Number':<20}: {self.aadhaar_number or '—'}",
            f"  {'Full Name':<20}: {self.full_name or '—'}",
            f"  {'First Name':<20}: {self.first_name or '—'}",
            f"  {'Middle Name':<20}: {self.middle_name or '—'}",
            f"  {'Last Name':<20}: {self.last_name or '—'}",
            f"  {'Date of Birth':<20}: {self.dob or '—'}",
            f"  {'Gender':<20}: {self.gender or '—'}",
        ]
        if self.address:
            lines.append(f"  {'Address':<20}: {self.address}")
        return "\n".join(lines)