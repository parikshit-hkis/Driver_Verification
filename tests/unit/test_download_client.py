import pytest
import os
import httpx
from unittest.mock import patch, MagicMock
from src.clients.s3_download_client import S3DownloadClient
from src.core.exceptions import DownloadException, SecurityViolationException

@pytest.mark.asyncio
async def test_insecure_http_scheme_rejected(tmp_path):
    client = S3DownloadClient()
    dest = str(tmp_path / "test.zip")
    with pytest.raises(SecurityViolationException) as exc_info:
        await client.download_file("http://insecure-example.com/file.zip", dest)
    assert "INSECURE_URL_SCHEME" in exc_info.value.error_code

@pytest.mark.asyncio
async def test_missing_url_rejected(tmp_path):
    client = S3DownloadClient()
    dest = str(tmp_path / "test.zip")
    with pytest.raises(SecurityViolationException) as exc_info:
        await client.download_file("", dest)
    assert "MISSING_URL" in exc_info.value.error_code

@pytest.mark.asyncio
async def test_ssrf_loopback_and_metadata_blocked(tmp_path):
    client = S3DownloadClient()
    dest = str(tmp_path / "test.zip")

    # Localhost
    with pytest.raises(SecurityViolationException) as exc_info:
        await client.download_file("https://localhost/file.zip", dest)
    assert "SSRF_LOOPBACK_BLOCKED" in exc_info.value.error_code

    # 127.0.0.1
    with pytest.raises(SecurityViolationException) as exc_info:
        await client.download_file("https://127.0.0.1/file.zip", dest)
    assert "SSRF_LOOPBACK_BLOCKED" in exc_info.value.error_code

    # AWS metadata endpoint (169.254.169.254)
    with pytest.raises(SecurityViolationException) as exc_info:
        await client.download_file("https://169.254.169.254/latest/meta-data/", dest)
    assert "SSRF_PRIVATE_IP_BLOCKED" in exc_info.value.error_code

    # Private IP 10.0.0.1
    with pytest.raises(SecurityViolationException) as exc_info:
        await client.download_file("https://10.0.0.1/file.zip", dest)
    assert "SSRF_PRIVATE_IP_BLOCKED" in exc_info.value.error_code

@pytest.mark.asyncio
async def test_content_length_exceeded(tmp_path):
    client = S3DownloadClient(max_size_bytes=100)
    dest = str(tmp_path / "test.zip")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-length": "5000"}

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value.__aenter__.return_value = mock_response
        with pytest.raises(SecurityViolationException) as exc_info:
            await client.download_file("https://example.com/file.zip", dest)
        assert "DOWNLOAD_SIZE_EXCEEDED" in exc_info.value.error_code

@pytest.mark.asyncio
async def test_successful_download_streaming(tmp_path):
    client = S3DownloadClient()
    dest = str(tmp_path / "downloaded.zip")
    sample_content = b"PK\x03\x04mock_zip_content"

    async def mock_aiter_bytes(chunk_size=65536):
        yield sample_content

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-length": str(len(sample_content))}
    mock_response.aiter_bytes = mock_aiter_bytes

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value.__aenter__.return_value = mock_response
        result_path = await client.download_file("https://example.com/file.zip", dest)
        assert os.path.exists(result_path)
        with open(result_path, "rb") as f:
            assert f.read() == sample_content
