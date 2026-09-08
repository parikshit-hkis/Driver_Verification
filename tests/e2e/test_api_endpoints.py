import os
import io
import pytest
import pyzipper
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image

from src.schemas.document_schemas import OCRResult
from src.core.exceptions import VisionApiException


def create_in_memory_encrypted_zip(filename: str, content: bytes, password: str) -> bytes:
    buffer = io.BytesIO()
    with pyzipper.AESZipFile(buffer, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(password.encode("utf-8"))
        zf.writestr(filename, content)
    return buffer.getvalue()


def dummy_image_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), color="white").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def mock_e2e_environment():
    password = "9876543210"
    img_data = dummy_image_bytes()

    zips = {
        "aadhaar": create_in_memory_encrypted_zip("aadhaar.jpg", img_data, password),
        "pan": create_in_memory_encrypted_zip("pan.jpg", img_data, password),
        "licence": create_in_memory_encrypted_zip("dl.jpg", img_data, password),
        "rc": create_in_memory_encrypted_zip("rc.jpg", img_data, password),
    }

    async def mock_download_file(self, url: str, destination_path: str, doc_name: str = "document"):
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        if "bad_url" in url:
            from src.core.exceptions import DownloadException
            raise DownloadException("Failed to download", "DOWNLOAD_ERROR")

        data = zips.get(doc_name, b"")
        with open(destination_path, "wb") as f:
            f.write(data)
        return destination_path

    async def mock_extract_text(self, file_path: str):
        path_lower = file_path.lower()
        if "fail_vision" in path_lower or "case-6" in path_lower:
            raise VisionApiException("Vision backend unavailable", "VISION_API_FAILED")
        elif "aadhaar" in path_lower:
            return OCRResult(raw_text="GOVERNMENT OF INDIA\nRAHUL SHARMA\nDOB: 12/05/1995\n1234 5678 9012")
        elif "pan" in path_lower:
            if "pan_mismatch" in path_lower or "case-2" in path_lower or "batch-driver-2" in path_lower:
                return OCRResult(raw_text="INCOME TAX DEPARTMENT\nAMIT PATEL\nABCDE1234F")
            return OCRResult(raw_text="INCOME TAX DEPARTMENT\nRAHUL SHARMA\nABCDE1234F")
        elif "licence" in path_lower or "dl" in path_lower:
            if "dl_mismatch" in path_lower or "case-3" in path_lower:
                return OCRResult(raw_text="UNION OF INDIA DRIVING LICENCE\nDL NO: MH-12-20180054321\nName: VIKRAM SINGH\nAuthorisation: MCWG")
            return OCRResult(raw_text="UNION OF INDIA DRIVING LICENCE\nDL NO: MH-12-20180054321\nName: RAHUL SHARMA\nAuthorisation: MCWG")
        elif "rc" in path_lower:
            if "rc_lmv" in path_lower or "case-4" in path_lower:
                return OCRResult(raw_text="CERTIFICATE OF REGISTRATION\nREGN NO: MH12AB1234\nOwner: RAHUL SHARMA\nClass of Vehicle: LMV")
            return OCRResult(raw_text="CERTIFICATE OF REGISTRATION\nREGN NO: MH12AB1234\nOwner: RAHUL SHARMA\nClass of Vehicle: MCWG")
        return OCRResult(raw_text="UNKNOWN CONTENT")

    with patch("src.clients.s3_download_client.S3DownloadClient.download_file", new=mock_download_file), \
         patch("src.clients.vision_ai_client.VisionAIClient.extract_text_from_file", new=mock_extract_text):
        yield


def test_case_1_fully_valid_driver(client: TestClient, mock_e2e_environment):
    """Case 1: Fully Valid Driver -> VERIFIED"""
    payload = {
        "driver_id": "driver-case-1",
        "mobile_number": "9876543210",
        "vehicle_class": "2 wheeler",
        "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
        "pan_zip_url": "https://s3.example.com/pan.zip",
        "licence_zip_url": "https://s3.example.com/licence.zip",
        "rc_zip_url": "https://s3.example.com/rc.zip",
    }
    resp = client.post("/api/v1/verify-driver", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "VERIFIED"
    assert data["rejection_reasons"] == []
    assert data["name_verification"]["aadhaar_pan"]["match"] is True
    assert data["name_verification"]["aadhaar_licence"]["match"] is True
    assert data["vehicle_verification"]["match"] is True


def test_case_2_aadhaar_pan_name_mismatch(client: TestClient, mock_e2e_environment):
    """Case 2: Aadhaar/PAN Name Mismatch -> REJECTED with AADHAAR_PAN_NAME_MISMATCH"""
    payload = {
        "driver_id": "driver-case-2",
        "mobile_number": "9876543210",
        "vehicle_class": "2 wheeler",
        "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
        "pan_zip_url": "https://s3.example.com/pan_mismatch.zip",
        "licence_zip_url": "https://s3.example.com/licence.zip",
        "rc_zip_url": "https://s3.example.com/rc.zip",
    }
    resp = client.post("/api/v1/verify-driver", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "REJECTED"
    assert "AADHAAR_PAN_NAME_MISMATCH" in data["rejection_reasons"]
    assert data["name_verification"]["aadhaar_pan"]["match"] is False
    assert data["name_verification"]["aadhaar_licence"]["match"] is True


def test_case_3_aadhaar_licence_name_mismatch(client: TestClient, mock_e2e_environment):
    """Case 3: Aadhaar/Licence Name Mismatch -> REJECTED with AADHAAR_LICENCE_NAME_MISMATCH"""
    payload = {
        "driver_id": "driver-case-3",
        "mobile_number": "9876543210",
        "vehicle_class": "2 wheeler",
        "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
        "pan_zip_url": "https://s3.example.com/pan.zip",
        "licence_zip_url": "https://s3.example.com/dl_mismatch.zip",
        "rc_zip_url": "https://s3.example.com/rc.zip",
    }
    resp = client.post("/api/v1/verify-driver", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "REJECTED"
    assert "AADHAAR_LICENCE_NAME_MISMATCH" in data["rejection_reasons"]
    assert data["name_verification"]["aadhaar_pan"]["match"] is True
    assert data["name_verification"]["aadhaar_licence"]["match"] is False


def test_case_4_vehicle_mismatch(client: TestClient, mock_e2e_environment):
    """Case 4: Vehicle Mismatch -> REJECTED with RC_VEHICLE_CLASS_MISMATCH"""
    payload = {
        "driver_id": "driver-case-4",
        "mobile_number": "9876543210",
        "vehicle_class": "2 wheeler",
        "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
        "pan_zip_url": "https://s3.example.com/pan.zip",
        "licence_zip_url": "https://s3.example.com/licence.zip",
        "rc_zip_url": "https://s3.example.com/rc_lmv.zip",
    }
    resp = client.post("/api/v1/verify-driver", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "REJECTED"
    assert "RC_VEHICLE_CLASS_MISMATCH" in data["rejection_reasons"]
    assert data["vehicle_verification"]["match"] is False


def test_case_5_incorrect_zip_password(client: TestClient, mock_e2e_environment):
    """Case 5: Incorrect ZIP Password -> ERROR"""
    payload = {
        "driver_id": "driver-case-5",
        "mobile_number": "1111111111",  # Wrong password
        "vehicle_class": "2 wheeler",
        "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
        "pan_zip_url": "https://s3.example.com/pan.zip",
        "licence_zip_url": "https://s3.example.com/licence.zip",
        "rc_zip_url": "https://s3.example.com/rc.zip",
    }
    resp = client.post("/api/v1/verify-driver", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ERROR"
    assert any("INVALID_ZIP_PASSWORD" in r for r in data["rejection_reasons"])


def test_case_6_vision_api_failure(client: TestClient, mock_e2e_environment):
    """Case 6: Vision API Failure -> ERROR, not REJECTED"""
    payload = {
        "driver_id": "driver-case-6",
        "mobile_number": "9876543210",
        "vehicle_class": "2 wheeler",
        "aadhaar_zip_url": "https://s3.example.com/fail_vision_aadhaar.zip",
        "pan_zip_url": "https://s3.example.com/pan.zip",
    }
    resp = client.post("/api/v1/verify-driver", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ERROR"
    assert any("VISION_API_FAILED" in r for r in data["rejection_reasons"])


def test_case_7_simultaneous_batch_verification(client: TestClient, mock_e2e_environment):
    """Case 7: Simultaneous Batch Verification with mixed outcomes (1 VERIFIED, 1 REJECTED, 1 ERROR)"""
    payload = {
        "drivers": [
            {
                "driver_id": "batch-driver-1",
                "mobile_number": "9876543210",
                "vehicle_class": "2 wheeler",
                "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
                "pan_zip_url": "https://s3.example.com/pan.zip",
                "licence_zip_url": "https://s3.example.com/licence.zip",
                "rc_zip_url": "https://s3.example.com/rc.zip",
            },
            {
                "driver_id": "batch-driver-2",
                "mobile_number": "9876543210",
                "vehicle_class": "2 wheeler",
                "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
                "pan_zip_url": "https://s3.example.com/pan_mismatch.zip",
                "licence_zip_url": "https://s3.example.com/licence.zip",
                "rc_zip_url": "https://s3.example.com/rc.zip",
            },
            {
                "driver_id": "batch-driver-3",
                "mobile_number": "0000000000",
                "vehicle_class": "2 wheeler",
                "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
            },
        ]
    }
    resp = client.post("/api/v1/batch-verify", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_count"] == 3
    assert data["verified_count"] == 1
    assert data["rejected_count"] == 1
    assert data["error_count"] == 1

    by_id = {r["driver_id"]: r for r in data["results"]}
    assert by_id["batch-driver-1"]["status"] == "VERIFIED"
    assert by_id["batch-driver-2"]["status"] == "REJECTED"
    assert by_id["batch-driver-3"]["status"] == "ERROR"


def test_case_8_batch_size_boundaries(client: TestClient):
    """Case 8: Batch Size Boundary Enforcement (Empty batch and >50 batch -> HTTP 422)"""
    # Empty drivers list
    resp = client.post("/api/v1/batch-verify", json={"drivers": []})
    assert resp.status_code == 422

    # 51 drivers list
    single_req = {
        "driver_id": "driver-x",
        "mobile_number": "9876543210",
        "vehicle_class": "2 wheeler"
    }
    resp = client.post("/api/v1/batch-verify", json={"drivers": [single_req] * 51})
    assert resp.status_code == 422


def test_direct_file_upload_verification(client: TestClient, mock_e2e_environment):
    """Tests the new direct multipart image file upload endpoint."""
    img_data = dummy_image_bytes()
    files = [
        ("adhar_front", ("aadhaar.jpg", img_data, "image/jpeg")),
        ("pan_front", ("pan.jpg", img_data, "image/jpeg")),
        ("licence_front", ("dl.jpg", img_data, "image/jpeg")),
        ("rc_front", ("rc.jpg", img_data, "image/jpeg")),
    ]
    data = {
        "driver_id": "driver-direct-01",
        "mobile_number": "9876543210",
        "vehicle_class": "2 wheeler"
    }

    resp = client.post("/api/v1/verify-driver-files", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()
    assert res["driver_id"] == "driver-direct-01"
    assert res["status"] == "VERIFIED"
    assert res["name_verification"]["aadhaar_pan"]["match"] is True
    assert res["vehicle_verification"]["match"] is True

