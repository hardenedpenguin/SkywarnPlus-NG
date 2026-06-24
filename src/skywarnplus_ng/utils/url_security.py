"""
Validate outbound webhook URLs to reduce SSRF risk (HTTPS, no private/loopback hosts).
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Tuple
from urllib.parse import urlparse


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def validate_public_https_webhook_url(url: str) -> Tuple[bool, str]:
    """
    Ensure URL is safe for server-side HTTP callbacks.

    - Empty / whitespace-only: allowed (optional field).
    - Must be https with a host.
    - Literal IPs: reject private, loopback, link-local, reserved, multicast.
    - Reject obvious local hostnames; block known cloud metadata names.
    - Resolve hostnames and reject addresses in private ranges.
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

    host_lower = host.lower().rstrip(".")
    blocked_names = (
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
    )
    if host_lower in blocked_names or host_lower.endswith(".local"):
        return False, "Webhook hostname is not allowed"

    try:
        ip = ipaddress.ip_address(host)
        if _is_blocked_ip(ip):
            return False, "Webhook URL must not target private, loopback, or non-public addresses"
        return True, ""
    except ValueError:
        pass

    try:
        addrinfo = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False, "Webhook hostname could not be resolved"

    for entry in addrinfo:
        resolved = entry[4][0]
        try:
            ip = ipaddress.ip_address(resolved)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            return False, "Webhook hostname resolves to a non-public address"

    return True, ""
