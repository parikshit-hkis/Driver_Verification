from typing import Optional, List

class VerificationServiceException(Exception):
    """Base exception for the verification service."""
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "INTERNAL_ERROR"

class DownloadException(VerificationServiceException):
    """Raised when document download fails."""
    def __init__(self, message: str, error_code: str = "DOWNLOAD_FAILED"):
        super().__init__(message, error_code)

class ZipExtractionException(VerificationServiceException):
    """Raised when password-protected ZIP extraction fails."""
    def __init__(self, message: str, error_code: str = "ZIP_EXTRACTION_FAILED"):
        super().__init__(message, error_code)

class InvalidZipPasswordException(ZipExtractionException):
    """Raised specifically when an incorrect password is provided."""
    def __init__(self, message: str = "Incorrect ZIP archive password"):
        super().__init__(message, "INVALID_ZIP_PASSWORD")

class SecurityViolationException(VerificationServiceException):
    """Raised when path traversal (Zip Slip) or file size limits are breached."""
    def __init__(self, message: str, error_code: str = "SECURITY_VIOLATION"):
        super().__init__(message, error_code)

class VisionApiException(VerificationServiceException):
    """Raised when Google Cloud Vision OCR fails."""
    def __init__(self, message: str, error_code: str = "VISION_API_FAILED"):
        super().__init__(message, error_code)
