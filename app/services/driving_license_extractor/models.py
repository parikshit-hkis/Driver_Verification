from typing import Optional, List
from pydantic import BaseModel


class DrivingLicenceData(BaseModel):
    # Licence number
    licence_number: Optional[str] = None   # GJ-RR-YYYY-NNNNNNN

    # Name
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None

    # Personal details
    dob: Optional[str] = None              # ISO YYYY-MM-DD
    blood_group: Optional[str] = None

    # Dates
    issue_date: Optional[str] = None       # ISO YYYY-MM-DD
    expiry_date: Optional[str] = None      # ISO YYYY-MM-DD (non-transport validity)
    transport_validity: Optional[str] = None  # separate transport class validity

    # Issuing authority
    issuing_authority: Optional[str] = None  # e.g. RTO AHMEDABAD

    # Vehicle classes the holder is authorized to drive
    vehicle_classes: List[str] = []

    def display(self) -> str:
        vc = ", ".join(self.vehicle_classes) if self.vehicle_classes else "—"
        lines = [
            f"  {'Licence Number':<22}: {self.licence_number or '—'}",
            f"  {'Full Name':<22}: {self.full_name or '—'}",
            f"  {'First Name':<22}: {self.first_name or '—'}",
            f"  {'Middle Name':<22}: {self.middle_name or '—'}",
            f"  {'Last Name':<22}: {self.last_name or '—'}",
            f"  {'Date of Birth':<22}: {self.dob or '—'}",
            f"  {'Issue Date':<22}: {self.issue_date or '—'}",
            f"  {'Expiry Date':<22}: {self.expiry_date or '—'}",
            f"  {'Vehicle Classes':<22}: {vc}",
            f"  {'Blood Group':<22}: {self.blood_group or '—'}",
            f"  {'Issuing Authority':<22}: {self.issuing_authority or '—'}",
        ]
        return "\n".join(lines)
