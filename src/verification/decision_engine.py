from typing import Optional, List, Dict, Any
from src.schemas.document_schemas import AadhaarData, PanData, LicenceData, RcData
from src.schemas.response_schemas import (
    DriverVerificationResponse,
    AadhaarDocumentStatus,
    PanDocumentStatus,
    LicenceDocumentStatus,
    RcDocumentStatus,
    MatchResult,
    VehicleVerificationResult
)
from src.verification.matchers.name_matcher import name_matcher
from src.verification.matchers.vehicle_matcher import vehicle_matcher

class DecisionEngine:
    """
    Deterministic rule engine that evaluates extracted document data and produces
    a VERIFIED or REJECTED decision.
    """
    def evaluate(
        self,
        driver_id: str,
        provided_vehicle_class: str,
        aadhaar: Optional[AadhaarData] = None,
        pan: Optional[PanData] = None,
        licence: Optional[LicenceData] = None,
        rc: Optional[RcData] = None
    ) -> DriverVerificationResponse:
        rejection_reasons: List[str] = []
        doc_statuses: Dict[str, Any] = {}

        # 1. Document Presence & Document-Specific Field Extraction
        doc_statuses["aadhaar"] = AadhaarDocumentStatus(
            processed=bool(aadhaar and aadhaar.name),
            name=aadhaar.name if aadhaar else None,
            dob=aadhaar.date_of_birth if aadhaar else None
        )
        if not aadhaar or not aadhaar.name:
            rejection_reasons.append("AADHAAR_NOT_FOUND")

        doc_statuses["pan"] = PanDocumentStatus(
            processed=bool(pan and pan.name),
            name=pan.name if pan else None,
            father_name=pan.father_name if pan else None,
            dob=pan.date_of_birth if pan else None
        )
        if not pan or not pan.name:
            rejection_reasons.append("PAN_NOT_FOUND")

        doc_statuses["licence"] = LicenceDocumentStatus(
            processed=bool(licence and licence.name),
            name=licence.name if licence else None,
            issue_date=licence.issue_date if licence else None,
            validity=licence.validity if licence else None,
            vehicle_classes=licence.vehicle_classes if licence else []
        )
        if not licence or not licence.name:
            rejection_reasons.append("LICENCE_NOT_FOUND")

        doc_statuses["rc"] = RcDocumentStatus(
            processed=bool(rc and rc.vehicle_class),
            name=rc.owner_name if rc else None,
            vehicle_class=rc.vehicle_class if rc else None,
            date_of_registration=rc.date_of_registration if rc else None,
            registration_validity=rc.registration_validity if rc else None
        )
        if not rc or not rc.vehicle_class:
            rejection_reasons.append("RC_NOT_FOUND")

        # 2. Name Matching Rules (Aadhaar is primary reference)
        name_verification: Dict[str, MatchResult] = {}

        if aadhaar and aadhaar.name and pan and pan.name:
            ap_match = name_matcher.compare_names(aadhaar.name, pan.name)
            name_verification["aadhaar_pan"] = ap_match
            if not ap_match.match:
                rejection_reasons.append("AADHAAR_PAN_NAME_MISMATCH")
        else:
            name_verification["aadhaar_pan"] = MatchResult(
                match=False, score=0.0, details="Missing document(s) for comparison"
            )

        if aadhaar and aadhaar.name and licence and licence.name:
            al_match = name_matcher.compare_names(aadhaar.name, licence.name)
            name_verification["aadhaar_licence"] = al_match
            if not al_match.match:
                rejection_reasons.append("AADHAAR_LICENCE_NAME_MISMATCH")
        else:
            name_verification["aadhaar_licence"] = MatchResult(
                match=False, score=0.0, details="Missing document(s) for comparison"
            )

        # 3. Vehicle Class Matching Rule
        v_match: Optional[VehicleVerificationResult] = None
        if rc and rc.vehicle_class:
            v_match = vehicle_matcher.compare(provided_vehicle_class, rc.vehicle_class)
            if not v_match.match:
                rejection_reasons.append("RC_VEHICLE_CLASS_MISMATCH")
        else:
            v_match = VehicleVerificationResult(
                provided_class=provided_vehicle_class,
                rc_class=None,
                normalized_provided_class=provided_vehicle_class,
                normalized_rc_class=None,
                match=False
            )

        # 4. Final Deterministic Status
        status_value = "VERIFIED" if len(rejection_reasons) == 0 else "REJECTED"

        return DriverVerificationResponse(
            driver_id=driver_id,
            status=status_value,
            documents=doc_statuses,
            name_verification=name_verification,
            vehicle_verification=v_match,
            rejection_reasons=rejection_reasons
        )

decision_engine = DecisionEngine()
