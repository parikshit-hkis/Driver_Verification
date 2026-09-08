import os
import zipfile
from typing import List, Optional
try:
    import pyzipper
    HAS_PYZIPPER = True
except ImportError:
    HAS_PYZIPPER = False

from src.core.config import settings
from src.core.logger import logger
from src.core.exceptions import (
    ZipExtractionException,
    InvalidZipPasswordException,
    SecurityViolationException
)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}

class ZipExtractor:
    """
    Safely extracts password-protected ZIP archives containing driver documents.
    Supports both ZipCrypto and modern AES encryption via pyzipper.
    Protects against Zip Slip (path traversal), ZIP bombs, and incorrect passwords.
    """
    def __init__(
        self,
        max_files: Optional[int] = None,
        max_extracted_size: Optional[int] = None
    ):
        self.max_files = max_files or settings.MAX_FILES_PER_ZIP
        self.max_size = max_extracted_size or settings.MAX_EXTRACTED_SIZE

    def extract_zip(
        self,
        zip_path: str,
        password: str,
        target_dir: str,
        doc_source: str = "document"
    ) -> List[str]:
        """
        Extracts valid images/PDFs from a password-protected ZIP file into target_dir.
        Uses driver's mobile_number as password.
        Returns list of absolute paths to extracted document files.
        """
        if not os.path.exists(zip_path):
            raise ZipExtractionException(f"ZIP file not found: {zip_path}", "FILE_NOT_FOUND")

        # Check if it's a valid ZIP
        is_valid_zip = False
        if HAS_PYZIPPER:
            is_valid_zip = pyzipper.is_zipfile(zip_path)
        if not is_valid_zip:
            is_valid_zip = zipfile.is_zipfile(zip_path)

        if not is_valid_zip:
            raise ZipExtractionException(f"Corrupted or invalid ZIP file for {doc_source}", "INVALID_ZIP_ARCHIVE")

        os.makedirs(target_dir, exist_ok=True)
        abs_target_dir = os.path.realpath(target_dir)

        extracted_files: List[str] = []
        total_extracted_bytes = 0
        total_files = 0
        password_bytes = password.strip().encode("utf-8")

        zip_opener = pyzipper.AESZipFile if HAS_PYZIPPER else zipfile.ZipFile

        try:
            with zip_opener(zip_path, "r") as zf:
                # Set password on the zip object
                if hasattr(zf, "setpassword"):
                    zf.setpassword(password_bytes)

                infolist = zf.infolist()
                if len(infolist) == 0:
                    raise ZipExtractionException(f"ZIP archive is empty for {doc_source}", "EMPTY_ZIP")

                for member in infolist:
                    if member.is_dir():
                        continue

                    total_files += 1
                    if total_files > self.max_files:
                        raise SecurityViolationException(
                            f"ZIP archive contains too many files ({total_files} > {self.max_files})",
                            "MAX_FILES_EXCEEDED"
                        )

                    # Zip Slip (path traversal) defense
                    target_file_path = os.path.realpath(os.path.join(target_dir, member.filename))
                    if not target_file_path.startswith(abs_target_dir + os.sep) and target_file_path != abs_target_dir:
                        raise SecurityViolationException(
                            f"Zip Slip / directory traversal attempt detected in member: {member.filename}",
                            "PATH_TRAVERSAL_DETECTED"
                        )

                    # Check file extension
                    _, ext = os.path.splitext(member.filename.lower())
                    if ext not in ALLOWED_EXTENSIONS:
                        logger.info(f"Skipping unsupported file inside ZIP: {member.filename}")
                        continue

                    total_extracted_bytes += member.file_size
                    if total_extracted_bytes > self.max_size:
                        raise SecurityViolationException(
                            f"Extracted files exceed size limit ({total_extracted_bytes} > {self.max_size} bytes)",
                            "MAX_SIZE_EXCEEDED"
                        )

                    # Extract file with password
                    try:
                        os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                        with zf.open(member, mode="r", pwd=password_bytes) as source_file, \
                             open(target_file_path, "wb") as dest_file:
                            dest_file.write(source_file.read())
                        extracted_files.append(target_file_path)
                    except (RuntimeError, zipfile.BadZipFile) as e:
                        err_str = str(e).lower()
                        if "bad password" in err_str or "password required" in err_str or "crc" in err_str:
                            logger.error(f"Invalid password for {doc_source} ZIP archive")
                            raise InvalidZipPasswordException(f"Incorrect password for {doc_source} ZIP archive") from e
                        raise ZipExtractionException(f"Corrupted entry {member.filename} in {doc_source} ZIP", "CORRUPTED_ENTRY") from e

        except (zipfile.BadZipFile, zipfile.LargeZipFile) as e:
            logger.error(f"Failed to read ZIP archive for {doc_source}: {e}")
            raise ZipExtractionException(f"Corrupted or invalid ZIP archive for {doc_source}", "BAD_ZIP_FILE") from e

        if not extracted_files:
            raise ZipExtractionException(
                f"No supported document files (.jpg, .png, .pdf) found in {doc_source} ZIP archive",
                "NO_VALID_DOCUMENTS_FOUND"
            )

        logger.info(f"Extracted {len(extracted_files)} files for {doc_source}")
        return extracted_files
