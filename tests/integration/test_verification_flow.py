import os
import io
import pytest
import pyzipper
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.schemas.document_schemas import OCRResult
from PIL import Image

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
def mock_pipeline_environment():
    password = "9876543210"
    img_data = dummy_image_bytes()

    # Pre-generate valid encrypted zip bytes for each doc
    zips = {
        "aadhaar": create_in_memory_encrypted_zip("aadhaar.jpg", img_data, password),
        "pan": create_in_memory_encrypted_zip("pan.jpg", img_data, password),
        "licence": create_in_memory_encrypted_zip("dl.jpg", img_data, password),
        "rc": create_in_memory_encrypted_zip("rc.jpg", img_data, password),
    }

    # Mock S3 Download to stream these pre-generated zips
    async def mock_download_file(self, url: str, destination_path: str, doc_name: str = "document"):
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        if "bad_url" in url:
            from src.core.exceptions import DownloadException
            raise DownloadException("Failed to download", "DOWNLOAD_ERROR")

        data = zips.get(doc_name, b"")
        with open(destination_path, "wb") as f:
            f.write(data)
        return destination_path

    # Mock Vision AI client to return realistic OCR text based on document type
    async def mock_extract_text(self, file_path: str):
        path_lower = file_path.lower()
        if "aadhaar" in path_lower:
            return OCRResult(raw_text="GOVERNMENT OF INDIA\nPARIKSHIT PANCHAL\nDOB: 12/05/1995\n1234 5678 9012")
        elif "pan" in path_lower:
            if "mismatch" in path_lower or "driver-2" in path_lower:
                return OCRResult(raw_text="INCOME TAX DEPARTMENT\nAMIT SHARMA\nABCDE1234F")
            return OCRResult(raw_text="INCOME TAX DEPARTMENT\nPARIKSHIT PANCHAL\nABCDE1234F")
        elif "licence" in path_lower or "dl" in path_lower:
            return OCRResult(raw_text="UNION OF INDIA DRIVING LICENCE\nDL NO: MH-12-20180054321\nName: PARIKSHIT PANCHAL\nAuthorisation to Drive: MCWG")
        elif "rc" in path_lower:
            return OCRResult(raw_text="CERTIFICATE OF REGISTRATION\nREGN NO: MH12AB1234\nOwner Name: PARIKSHIT PANCHAL\nClass of Vehicle: MCWG")
        return OCRResult(raw_text="UNKNOWN TEXT")

    with patch("src.clients.s3_download_client.S3DownloadClient.download_file", new=mock_download_file), \
         patch("src.clients.vision_ai_client.VisionAIClient.extract_text_from_file", new=mock_extract_text):
        yield

def test_full_single_driver_verification_verified(client: TestClient, mock_pipeline_environment):
    payload = {
        "driver_id": "driver-success-01",
        "mobile_number": "9876543210",
        "vehicle_class": "2 wheeler",
        "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
        "pan_zip_url": "https://s3.example.com/pan.zip",
        "licence_zip_url": "https://s3.example.com/licence.zip",
        "rc_zip_url": "https://s3.example.com/rc.zip"
    }

    response = client.post("/api/v1/verify-driver", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["driver_id"] == "driver-success-01"
    assert data["status"] == "VERIFIED"
    assert len(data["rejection_reasons"]) == 0
    assert data["name_verification"]["aadhaar_pan"]["match"] is True
    assert data["name_verification"]["aadhaar_licence"]["match"] is True
    assert data["vehicle_verification"]["match"] is True

def test_full_single_driver_verification_rejected(client: TestClient, mock_pipeline_environment):
    # Driver with PAN name mismatch
    payload = {
        "driver_id": "driver-2-mismatch",
        "mobile_number": "9876543210",
        "vehicle_class": "2 wheeler",
        "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
        "pan_zip_url": "https://s3.example.com/pan_mismatch.zip",
        "licence_zip_url": "https://s3.example.com/licence.zip",
        "rc_zip_url": "https://s3.example.com/rc.zip"
    }

    response = client.post("/api/v1/verify-driver", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["driver_id"] == "driver-2-mismatch"
    assert data["status"] == "REJECTED"
    assert "AADHAAR_PAN_NAME_MISMATCH" in data["rejection_reasons"]

def test_full_batch_verification_simultaneous(client: TestClient, mock_pipeline_environment):
    # 3 drivers simultaneously: Verified, Rejected, and Error (bad password)
    payload = {
        "drivers": [
            {
                "driver_id": "driver-1",
                "mobile_number": "9876543210",
                "vehicle_class": "2 wheeler",
                "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
                "pan_zip_url": "https://s3.example.com/pan.zip",
                "licence_zip_url": "https://s3.example.com/licence.zip",
                "rc_zip_url": "https://s3.example.com/rc.zip"
            },
            {
                "driver_id": "driver-2",
                "mobile_number": "9876543210",
                "vehicle_class": "2 wheeler",
                "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip",
                "pan_zip_url": "https://s3.example.com/pan_mismatch.zip",
                "licence_zip_url": "https://s3.example.com/licence.zip",
                "rc_zip_url": "https://s3.example.com/rc.zip"
            },
            {
                "driver_id": "driver-3",
                "mobile_number": "0000000000",  # WRONG password -> produces ERROR
                "vehicle_class": "2 wheeler",
                "aadhaar_zip_url": "https://s3.example.com/aadhaar.zip"
            }
        ]
    }

    response = client.post("/api/v1/batch-verify", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["total_count"] == 3
    assert data["verified_count"] == 1
    assert data["rejected_count"] == 1
    assert data["error_count"] == 1

    results_by_id = {r["driver_id"]: r for r in data["results"]}
    assert results_by_id["driver-1"]["status"] == "VERIFIED"
    assert results_by_id["driver-2"]["status"] == "REJECTED"
    assert results_by_id["driver-3"]["status"] == "ERROR"
    assert "INVALID_ZIP_PASSWORD" in str(results_by_id["driver-3"]["rejection_reasons"])
