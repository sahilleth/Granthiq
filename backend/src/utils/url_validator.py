"""
SSRF Protection - Validates URLs before server-side requests.

Only enforced in production to avoid blocking localhost URLs in development.
"""

import ipaddress
from urllib.parse import urlparse

from loguru import logger

from src.config import get_settings

# Private/reserved IP ranges that should never be accessed server-side in production
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

# Cloud metadata endpoints
_BLOCKED_HOSTS = {
    "metadata.google.internal",
    "metadata.goog",
}

_ALLOWED_SCHEMES = {"http", "https"}


def validate_url_for_ssrf(url: str) -> None:
    """Validate a URL is safe for server-side fetching.

    Raises ValueError if the URL targets a private/internal network.
    Skipped entirely in development environment.
    """
    settings = get_settings()
    if settings.environment != "production":
        return

    parsed = urlparse(url)

    # Block non-HTTP schemes (file://, ftp://, gopher://, etc.)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed. Use http or https.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must include a hostname.")

    # Block known metadata hostnames
    if hostname.lower() in _BLOCKED_HOSTS:
        raise ValueError("Access to internal metadata services is not allowed.")

    # Resolve hostname to IP and check against blocked ranges
    try:
        addr = ipaddress.ip_address(hostname)
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                logger.warning(f"SSRF blocked: URL {url} resolves to private IP {addr}")
                raise ValueError("URL targets a private or reserved IP address.")
    except ValueError as e:
        if "private" in str(e).lower() or "reserved" in str(e).lower():
            raise
        # hostname is a domain name, not an IP — allow it through
        # DNS resolution happens at request time; we block known-bad hosts above
        pass
