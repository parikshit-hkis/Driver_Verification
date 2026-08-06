from typing import Optional
from pydantic import BaseModel


class RCData(BaseModel):
    # Registration details
    registration_number: Optional[str] = None  # GJ-RR-XX-NNNN

    # Owner
    owner_name: Optional[str] = None

    # Vehicle details
    vehicle_class: Optional[str] = None        # e.g. LMV-CAR, M-CYCLE/SCOOTER
    vehicle_type: Optional[str] = None         # e.g. MOTOR CAR, MOTORCYCLE
    fuel_type: Optional[str] = None            # PETROL / DIESEL / CNG / EV / HYBRID
    manufacturer: Optional[str] = None         # e.g. MARUTI SUZUKI
    model: Optional[str] = None               # e.g. SWIFT DZIRE
    chassis_number: Optional[str] = None
    engine_number: Optional[str] = None

    # Dates
    date_of_registration: Optional[str] = None  # ISO YYYY-MM-DD
    registration_validity: Optional[str] = None  # ISO YYYY-MM-DD
    fitness_validity: Optional[str] = None        # ISO YYYY-MM-DD
    insurance_validity: Optional[str] = None      # ISO YYYY-MM-DD
    tax_validity: Optional[str] = None

    # Issuing RTO
    issuing_rto: Optional[str] = None

    def display(self) -> str:
        lines = [
            f"  {'Registration No':<24}: {self.registration_number or '—'}",
            f"  {'Owner Name':<24}: {self.owner_name or '—'}",
            f"  {'Vehicle Class':<24}: {self.vehicle_class or '—'}",
            f"  {'Vehicle Type':<24}: {self.vehicle_type or '—'}",
            f"  {'Fuel Type':<24}: {self.fuel_type or '—'}",
            f"  {'Manufacturer':<24}: {self.manufacturer or '—'}",
            f"  {'Model':<24}: {self.model or '—'}",
            f"  {'Chassis Number':<24}: {self.chassis_number or '—'}",
            f"  {'Engine Number':<24}: {self.engine_number or '—'}",
            f"  {'Date of Registration':<24}: {self.date_of_registration or '—'}",
            f"  {'Registration Validity':<24}: {self.registration_validity or '—'}",
            f"  {'Fitness Validity':<24}: {self.fitness_validity or '—'}",
            f"  {'Insurance Validity':<24}: {self.insurance_validity or '—'}",
            f"  {'Issuing RTO':<24}: {self.issuing_rto or '—'}",
        ]
        return "\n".join(lines)
