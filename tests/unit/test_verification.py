import pytest
from src.verification.matchers.name_matcher import name_matcher
from src.verification.matchers.vehicle_matcher import vehicle_matcher
from src.verification.decision_engine import decision_engine
from src.schemas.document_schemas import AadhaarData, PanData, LicenceData, RcData

def test_name_matcher_levels():
    # Level 1: Exact
    res1 = name_matcher.compare_names("Parikshit Panchal", "PARIKSHIT PANCHAL")
    assert res1.match is True
    assert res1.score == 100.0

    # Level 2: Token reordered
    res2 = name_matcher.compare_names("Panchal Parikshit", "Parikshit Panchal")
    assert res2.match is True
    assert res2.score == 100.0

    # Level 3: Initials
    res3 = name_matcher.compare_names("Parikshit A Panchal", "Parikshit Panchal")
    assert res3.match is True
    assert res3.score >= 95.0

    # Mismatch
    res4 = name_matcher.compare_names("Parikshit Panchal", "Rahul Sharma")
    assert res4.match is False
    assert res4.score < 80.0

def test_vehicle_matcher():
    # Matching
    res1 = vehicle_matcher.compare("2 wheeler", "MCWG")
    assert res1.match is True
    assert res1.normalized_rc_class == "2 wheeler"

    res2 = vehicle_matcher.compare("car", "LMV")
    assert res2.match is True

    # Mismatch
    res3 = vehicle_matcher.compare("2 wheeler", "LMV")
    assert res3.match is False
    assert res3.normalized_provided_class == "2 wheeler"
    assert res3.normalized_rc_class == "car"

def test_decision_engine_fully_verified():
    aadhaar = AadhaarData(name="PARIKSHIT PANCHAL", aadhaar_number="123456789012")
    pan = PanData(name="PARIKSHIT PANCHAL", pan_number="ABCDE1234F")
    licence = LicenceData(name="PARIKSHIT PANCHAL", licence_number="MH1220180054321")
    rc = RcData(owner_name="PARIKSHIT PANCHAL", vehicle_class="MCWG")

    res = decision_engine.evaluate(
        driver_id="partner-101",
        provided_vehicle_class="2 wheeler",
        aadhaar=aadhaar,
        pan=pan,
        licence=licence,
        rc=rc
    )

    assert res.status == "VERIFIED"
    assert len(res.rejection_reasons) == 0
    assert res.documents["aadhaar"].processed is True
    assert res.name_verification["aadhaar_pan"].match is True
    assert res.vehicle_verification.match is True

def test_decision_engine_name_mismatch():
    aadhaar = AadhaarData(name="PARIKSHIT PANCHAL", aadhaar_number="123456789012")
    pan = PanData(name="AMIT SHARMA", pan_number="ABCDE1234F")
    licence = LicenceData(name="PARIKSHIT PANCHAL", licence_number="MH1220180054321")
    rc = RcData(owner_name="PARIKSHIT PANCHAL", vehicle_class="MCWG")

    res = decision_engine.evaluate(
        driver_id="partner-102",
        provided_vehicle_class="2 wheeler",
        aadhaar=aadhaar,
        pan=pan,
        licence=licence,
        rc=rc
    )

    assert res.status == "REJECTED"
    assert "AADHAAR_PAN_NAME_MISMATCH" in res.rejection_reasons

def test_decision_engine_vehicle_mismatch():
    aadhaar = AadhaarData(name="PARIKSHIT PANCHAL", aadhaar_number="123456789012")
    pan = PanData(name="PARIKSHIT PANCHAL", pan_number="ABCDE1234F")
    licence = LicenceData(name="PARIKSHIT PANCHAL", licence_number="MH1220180054321")
    rc = RcData(owner_name="PARIKSHIT PANCHAL", vehicle_class="LMV")

    res = decision_engine.evaluate(
        driver_id="partner-103",
        provided_vehicle_class="2 wheeler",
        aadhaar=aadhaar,
        pan=pan,
        licence=licence,
        rc=rc
    )

    assert res.status == "REJECTED"
    assert "RC_VEHICLE_CLASS_MISMATCH" in res.rejection_reasons

def test_decision_engine_missing_document():
    aadhaar = AadhaarData(name="PARIKSHIT PANCHAL", aadhaar_number="123456789012")
    pan = None
    licence = LicenceData(name="PARIKSHIT PANCHAL", licence_number="MH1220180054321")
    rc = RcData(owner_name="PARIKSHIT PANCHAL", vehicle_class="MCWG")

    res = decision_engine.evaluate(
        driver_id="partner-104",
        provided_vehicle_class="2 wheeler",
        aadhaar=aadhaar,
        pan=pan,
        licence=licence,
        rc=rc
    )

    assert res.status == "REJECTED"
    assert "PAN_NOT_FOUND" in res.rejection_reasons
