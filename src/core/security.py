import re
import ipaddress
import socket
from urllib.parse import urlparse
from typing import Optional
from src.core.exceptions import SecurityViolationException

def mask_aadhaar(aadhaar: Optional[str]) -> str:
    """Masks 12-digit Aadhaar number: e.g. 1234 5678 9012 -> XXXXXXXX9012"""
    if not aadhaar:
        return ""
    clean = re.sub(r"\D", "", aadhaar)
    if len(clean) == 12:
        return "X" * 8 + clean[-4:]
    return "XXXXXXXX" + clean[-4:] if len(clean) >= 4 else "XXXXXXXX"

def mask_pan(pan: Optional[str]) -> str:
    """Masks 10-character PAN: e.g. ABCDE1234F -> XXXXX1234X"""
    if not pan:
        return ""
    clean = pan.strip().upper()
    if len(clean) == 10:
        return "X" * 5 + clean[5:9] + "X"
    return "XXXXX" + clean[-4:] if len(clean) >= 4 else "XXXXX"

def mask_mobile(mobile: Optional[str]) -> str:
    """Masks 10-digit mobile number: e.g. 9876543210 -> XXXXXX3210"""
    if not mobile:
        return ""
    clean = re.sub(r"\D", "", mobile)
    if len(clean) >= 4:
        return "X" * (len(clean) - 4) + clean[-4:]
    return "XXXX"

def validate_safe_url(url: str, doc_name: str = "document") -> None:
    """
    Validates URL safety and defends against SSRF (Server-Side Request Forgery).
    1. Enforces HTTPS scheme.
    2. Prohibits localhost and loopback targets.
    3. Blocks private, link-local, and cloud metadata IP ranges (e.g. 169.254.169.254).
    """
    if not url:
        raise SecurityViolationException(f"Missing URL for {doc_name}", "MISSING_URL")

    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise SecurityViolationException(
            f"Insecure URL scheme for {doc_name}. Only HTTPS URLs are permitted.",
            "INSECURE_URL_SCHEME"
        )

    hostname = parsed.hostname
    if not hostname:
        raise SecurityViolationException(f"Invalid URL host for {doc_name}", "INVALID_URL_HOST")

    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "127.0.0.1", "::1"):
        raise SecurityViolationException(
            f"SSRF protection: loopback target {hostname} blocked for {doc_name}",
            "SSRF_LOOPBACK_BLOCKED"
        )

    # Check if host is direct IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise SecurityViolationException(
                f"SSRF protection: private or internal IP {hostname} blocked for {doc_name}",
                "SSRF_PRIVATE_IP_BLOCKED"
            )
    except ValueError:
        # Not a literal IP, hostname is a domain name (e.g. s3.amazonaws.com)
        pass
