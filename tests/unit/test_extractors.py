import pytest
from src.extraction.document_classifier import DocumentClassifier
from src.extraction.extractors.aadhaar_extractor import AadhaarExtractor
from src.extraction.extractors.pan_extractor import PanExtractor
from src.extraction.extractors.licence_extractor import LicenceExtractor
from src.extraction.extractors.rc_extractor import RcExtractor
from src.schemas.document_schemas import OCRResult

def test_document_classifier():
    classifier = DocumentClassifier()

    aadhaar_ocr = OCRResult(raw_text="GOVERNMENT OF INDIA\nUNIQUE IDENTIFICATION AUTHORITY OF INDIA\nDOB: 15/08/1992")
    assert classifier.classify(aadhaar_ocr) == "aadhaar"

    pan_ocr = OCRResult(raw_text="INCOME TAX DEPARTMENT\nPERMANENT ACCOUNT NUMBER\nPAN: ABCDE1234F")
    assert classifier.classify(pan_ocr) == "pan"

    licence_ocr = OCRResult(raw_text="UNION OF INDIA\nDRIVING LICENCE\nDL NO: MH-12-20150012345")
    assert classifier.classify(licence_ocr) == "licence"

    rc_ocr = OCRResult(raw_text="REGISTRATION CERTIFICATE\nTRANSPORT DEPARTMENT\nREGN NO: MH12AB1234")
    assert classifier.classify(rc_ocr) == "rc"

    unknown_ocr = OCRResult(raw_text="RANDOM UNRECOGNIZABLE TEXT")
    assert classifier.classify(unknown_ocr, source_hint="aadhaar_zip") == "aadhaar"
    assert classifier.classify(unknown_ocr) == "unknown"

def test_aadhaar_extractor():
    extractor = AadhaarExtractor()
    ocr = OCRResult(raw_text="""
    GOVERNMENT OF INDIA
    PARIKSHIT PANCHAL
    DOB: 12/05/1995
    1234 5678 9012
    """)

    data = extractor.extract(ocr)
    assert data.name == "PARIKSHIT PANCHAL"
    assert data.date_of_birth == "12/05/1995"
    assert data.aadhaar_number == "123456789012"
    # Ensure gender is not an expected field
    assert not hasattr(data, "gender")

def test_pan_extractor():
    extractor = PanExtractor()
    ocr = OCRResult(raw_text="""
    INCOME TAX DEPARTMENT
    PARIKSHIT PANCHAL
    FATHER NAME: RAMESH PANCHAL
    DOB: 12/05/1995
    ABCDE1234F
    """)

    data = extractor.extract(ocr)
    assert data.name == "PARIKSHIT PANCHAL"
    assert data.pan_number == "ABCDE1234F"

def test_licence_extractor():
    extractor = LicenceExtractor()
    ocr = OCRResult(raw_text="""
    UNION OF INDIA DRIVING LICENCE
    DL No: MH-12-20180054321
    Name: PARIKSHIT PANCHAL
    Authorisation to Drive: MCWG, LMV
    """)

    data = extractor.extract(ocr)
    assert data.name == "PARIKSHIT PANCHAL"
    assert data.licence_number == "MH1220180054321"
    assert "MCWG" in data.vehicle_classes
    assert "LMV" in data.vehicle_classes

def test_rc_extractor():
    extractor = RcExtractor()
    ocr = OCRResult(raw_text="""
    FORM 23
    CERTIFICATE OF REGISTRATION
    REGN NO: MH12AB1234
    Owner Name: PARIKSHIT PANCHAL
    Class of Vehicle: MCWG
    Chassis No: MA3EWA1234567
    """)

    data = extractor.extract(ocr)
    assert data.owner_name == "PARIKSHIT PANCHAL"
    assert data.registration_number == "MH12AB1234"
    assert data.vehicle_class == "MCWG"
    # Ensure vehicle_make / vehicle_model are not required
    assert not hasattr(data, "vehicle_make")
    assert not hasattr(data, "vehicle_model")
