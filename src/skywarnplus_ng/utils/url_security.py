"""
Validate outbound webhook URLs to reduce SSRF risk (HTTPS, no private/loopback hosts).
"""

from __future__ import annotations

import ipaddress
from typing import Tuple
from urllib.parse import urlparse


def validate_public_https_webhook_url(url: str) -> Tuple[bool, str]:
    """
    Ensure URL is safe for server-side HTTP callbacks.

    - Empty / whitespace-only: allowed (optional field).
    - Must be https with a host.
    - Literal IPs: reject private, loopback, link-local, reserved, multicast.
    - Reject obvious local hostnames; block known cloud metadata names.
    """
    if url is None:
        return True, ""
    text = str(url).strip()
    if not text:
        return True, ""

    try:
        parsed = urlparse(text)
    except Exception:
        return False, "Invalid webhook URL"

    if parsed.scheme.lower() != "https":
        return False, "Webhook URL must use https://"

    host = parsed.hostname
    if not host:
        return False, "Webhook URL must include a hostname"

    host_lower = host.lower()
    blocked_names = (
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
    )
    if host_lower in blocked_names:
        return False, "Webhook hostname is not allowed"

    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False, "Webhook URL must not target private, loopback, or non-public addresses"
    except ValueError:
        pass

    return True, ""
