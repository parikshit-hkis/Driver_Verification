import unittest
from app.models.ocr_models import OCRResult, OCRText, BoundingBox, Point
from app.services.driving_license_extractor.extractor import DrivingLicenceExtractor
from app.services.driving_license_extractor.models import DrivingLicenceData


def make_ocr_text(text: str, min_x: float, min_y: float, max_x: float, max_y: float, confidence: float = 0.95) -> OCRText:
    points = [
        Point(x=min_x, y=min_y),
        Point(x=max_x, y=min_y),
        Point(x=max_x, y=max_y),
        Point(x=min_x, y=max_y),
    ]
    return OCRText(
        text=text,
        confidence=confidence,
        bounding_box=BoundingBox(points=points)
    )


class TestDrivingLicenceExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = DrivingLicenceExtractor()

    def test_expiry_date_from_validity_inline(self):
        texts = [
            make_ocr_text("DL NO: GJ-01-20150012345", 100, 100, 500, 140),
            make_ocr_text("NAME: PATEL JAY DHANSUKHBHAI", 100, 160, 600, 200),
            make_ocr_text("DOB: 15-08-1995", 100, 220, 400, 260),
            make_ocr_text("VALIDITY (NT): 14-08-2035", 100, 280, 500, 320),
        ]
        ocr = OCRResult(full_text="", texts=texts)
        data = self.extractor.extract(ocr)

        self.assertEqual(data.licence_number, "GJ-01-2015-0012345")
        self.assertEqual(data.date_of_birth, "1995-08-15")
        self.assertEqual(data.expiry_date, "2035-08-14")

    def test_expiry_date_from_valid_till_label(self):
        texts = [
            make_ocr_text("DL No: MH-02-20180012345", 100, 100, 500, 140),
            make_ocr_text("Valid Till", 100, 280, 250, 320),
            make_ocr_text("10/05/2038", 270, 280, 450, 320),
        ]
        ocr = OCRResult(full_text="", texts=texts)
        data = self.extractor.extract(ocr)

        self.assertEqual(data.licence_number, "MH-02-2018-0012345")
        self.assertEqual(data.expiry_date, "2038-05-10")

    def test_tabular_dates_extraction(self):
        texts = [
            make_ocr_text("DL NO: UP-65-20200012345", 100, 100, 500, 140),
            make_ocr_text("ISSUE DATE  VALIDITY", 100, 200, 600, 240),
            make_ocr_text("10-01-2020", 100, 260, 280, 300),
            make_ocr_text("09-01-2040", 350, 260, 530, 300),
        ]
        ocr = OCRResult(full_text="", texts=texts)
        data = self.extractor.extract(ocr)

        self.assertEqual(data.issue_date, "2020-01-10")
        self.assertEqual(data.expiry_date, "2040-01-09")

    def test_vehicle_classes_extraction_and_cov_exclusion(self):
        texts = [
            make_ocr_text("COV", 100, 300, 200, 340),  # Header - must not be in vehicle_classes
            make_ocr_text("MCWG", 100, 350, 250, 390),
            make_ocr_text("LMV-NT", 100, 400, 300, 440),
            make_ocr_text("3W-CAB", 100, 450, 300, 490),
        ]
        ocr = OCRResult(full_text="", texts=texts)
        data = self.extractor.extract(ocr)

        self.assertNotIn("COV", data.vehicle_classes)
        self.assertIn("MCWG", data.vehicle_classes)
        self.assertIn("LMV-NT", data.vehicle_classes)
        self.assertIn("3W-CAB", data.vehicle_classes)

    def test_old_dl_back_upper_left_vehicle_classes(self):
        texts_front = [
            make_ocr_text("DL NO: KA-01-20120012345", 100, 100, 500, 140),
            make_ocr_text("MCWG", 100, 300, 200, 340),
        ]
        texts_back = [
            make_ocr_text("KA-01-20120012345", 100, 80, 500, 120),  # Licence number at top left
            make_ocr_text("LMV-NT", 100, 150, 250, 190),            # Below DL number upper left
            make_ocr_text("TRANS", 100, 200, 250, 240),
        ]
        ocr_front = OCRResult(full_text="", texts=texts_front)
        ocr_back = OCRResult(full_text="", texts=texts_back)

        data = self.extractor.extract_dl(ocr_front, ocr_back)

        self.assertEqual(data.licence_number, "KA-01-2012-0012345")
        self.assertIn("MCWG", data.vehicle_classes)
        self.assertIn("LMV-NT", data.vehicle_classes)
        self.assertIn("TRANS", data.vehicle_classes)


if __name__ == "__main__":
    unittest.main()
