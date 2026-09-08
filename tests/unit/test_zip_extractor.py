import os
import pytest
import pyzipper
from src.extraction.zip_extractor import ZipExtractor
from src.utils.temp_manager import TempDirectoryContext
from src.core.exceptions import (
    ZipExtractionException,
    InvalidZipPasswordException,
    SecurityViolationException
)

def create_encrypted_zip(zip_path: str, filename: str, content: bytes, password: str, encryption=pyzipper.WZ_AES):
    with pyzipper.AESZipFile(zip_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=encryption) as zf:
        zf.setpassword(password.encode("utf-8"))
        zf.writestr(filename, content)

def test_successful_password_extraction(tmp_path):
    zip_path = str(tmp_path / "protected.zip")
    extract_dir = str(tmp_path / "extracted")
    password = "9876543210"
    content = b"fake-aadhaar-image-bytes"

    create_encrypted_zip(zip_path, "aadhaar_front.jpg", content, password)

    extractor = ZipExtractor()
    extracted_files = extractor.extract_zip(zip_path, password, extract_dir, doc_source="aadhaar")

    assert len(extracted_files) == 1
    assert os.path.exists(extracted_files[0])
    with open(extracted_files[0], "rb") as f:
        assert f.read() == content

def test_invalid_password_raises_exception(tmp_path):
    zip_path = str(tmp_path / "protected.zip")
    extract_dir = str(tmp_path / "extracted")
    correct_password = "9876543210"
    wrong_password = "0000000000"

    create_encrypted_zip(zip_path, "aadhaar.jpg", b"secret-doc", correct_password)

    extractor = ZipExtractor()
    with pytest.raises(InvalidZipPasswordException):
        extractor.extract_zip(zip_path, wrong_password, extract_dir, doc_source="aadhaar")

def test_zip_slip_path_traversal_blocked(tmp_path):
    zip_path = str(tmp_path / "evil.zip")
    extract_dir = str(tmp_path / "extracted")
    password = "1234567890"

    # Create zip with malicious relative traversal path using AES encryption
    create_encrypted_zip(zip_path, "../../evil.jpg", b"malicious payload", password)

    extractor = ZipExtractor()
    with pytest.raises(SecurityViolationException) as exc_info:
        extractor.extract_zip(zip_path, password, extract_dir)
    assert "PATH_TRAVERSAL_DETECTED" in exc_info.value.error_code

def test_corrupted_or_non_zip_raises_exception(tmp_path):
    fake_zip = str(tmp_path / "not_a_zip.zip")
    with open(fake_zip, "w") as f:
        f.write("This is plain text, not a zip file.")

    extractor = ZipExtractor()
    with pytest.raises(ZipExtractionException) as exc_info:
        extractor.extract_zip(fake_zip, "1234567890", str(tmp_path / "out"))
    assert "INVALID_ZIP_ARCHIVE" in exc_info.value.error_code

def test_max_files_exceeded_blocked(tmp_path):
    zip_path = str(tmp_path / "bomb.zip")
    password = "1234567890"

    with pyzipper.AESZipFile(zip_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(password.encode("utf-8"))
        for i in range(5):
            zf.writestr(f"file_{i}.jpg", b"data")

    extractor = ZipExtractor(max_files=3)
    with pytest.raises(SecurityViolationException) as exc_info:
        extractor.extract_zip(zip_path, password, str(tmp_path / "out"))
    assert "MAX_FILES_EXCEEDED" in exc_info.value.error_code

def test_temp_directory_context_cleanup():
    driver_id = "test-cleanup-driver"
    temp_path = None
    with TempDirectoryContext(driver_id) as temp_dir:
        temp_path = temp_dir
        assert os.path.exists(temp_path)
        test_file = os.path.join(temp_path, "dummy.txt")
        with open(test_file, "w") as f:
            f.write("hello")
        assert os.path.exists(test_file)

    # After context exit, directory should be removed
    assert not os.path.exists(temp_path)
