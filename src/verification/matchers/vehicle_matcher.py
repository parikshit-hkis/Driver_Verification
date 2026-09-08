from typing import Optional
from src.normalization.vehicle_normalizer import vehicle_normalizer
from src.schemas.response_schemas import VehicleVerificationResult

class VehicleMatcher:
    """
    Compares the API-provided vehicle class against the extracted RC vehicle class.
    """
    def compare(
        self,
        provided_class: str,
        rc_extracted_class: Optional[str]
    ) -> VehicleVerificationResult:
        norm_provided = vehicle_normalizer.normalize(provided_class) or provided_class.lower().strip()
        norm_rc = vehicle_normalizer.normalize(rc_extracted_class) if rc_extracted_class else None

        is_match = bool(norm_provided and norm_rc and norm_provided == norm_rc)

        return VehicleVerificationResult(
            provided_class=provided_class,
            rc_class=rc_extracted_class,
            normalized_provided_class=norm_provided,
            normalized_rc_class=norm_rc,
            match=is_match
        )

vehicle_matcher = VehicleMatcher()
