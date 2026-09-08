import os
import httpx
from typing import Optional
from src.core.config import settings
from src.core.logger import logger
from src.core.exceptions import DownloadException, SecurityViolationException

from src.core.security import validate_safe_url

class S3DownloadClient:
    """
    Secure client for streaming presigned S3 ZIP documents.
    Enforces HTTPS, SSRF defenses, size limits, and timeouts while guarding against URL/credential exposure in logs.
    """
    def __init__(
        self,
        timeout: Optional[int] = None,
        max_size_bytes: Optional[int] = None
    ):
        self.timeout = timeout or settings.DOWNLOAD_TIMEOUT
        self.max_size = max_size_bytes or settings.MAX_ZIP_SIZE

    async def download_file(self, url: str, destination_path: str, doc_name: str = "document") -> str:
        """
        Streams a presigned URL directly to a local destination file.
        Returns the absolute path to the downloaded file.
        """
        validate_safe_url(url, doc_name=doc_name)

        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        bytes_downloaded = 0

        logger.info(f"Starting download for {doc_name}")

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10.0)) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code == 403:
                        raise DownloadException(f"Access forbidden or expired presigned URL for {doc_name}", "URL_EXPIRED")
                    if response.status_code == 404:
                        raise DownloadException(f"Document not found at URL for {doc_name}", "DOCUMENT_NOT_FOUND")
                    if response.status_code != 200:
                        raise DownloadException(
                            f"Failed to download {doc_name}, HTTP status {response.status_code}",
                            f"HTTP_ERROR_{response.status_code}"
                        )

                    # Check Content-Length header if present
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > self.max_size:
                        raise SecurityViolationException(
                            f"{doc_name} exceeds maximum permitted download size ({self.max_size} bytes)",
                            "DOWNLOAD_SIZE_EXCEEDED"
                        )

                    with open(destination_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            bytes_downloaded += len(chunk)
                            if bytes_downloaded > self.max_size:
                                raise SecurityViolationException(
                                    f"{doc_name} exceeded maximum size during streaming ({self.max_size} bytes)",
                                    "DOWNLOAD_SIZE_EXCEEDED"
                                )
                            f.write(chunk)

            logger.info(f"Successfully downloaded {doc_name} ({bytes_downloaded} bytes)")
            return destination_path

        except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            logger.error(f"Timeout while downloading {doc_name}")
            raise DownloadException(f"Download timed out for {doc_name}", "DOWNLOAD_TIMEOUT") from e
        except httpx.RequestError as e:
            logger.error(f"Network error downloading {doc_name}: {type(e).__name__}")
            raise DownloadException(f"Network connection failed for {doc_name}", "NETWORK_ERROR") from e
