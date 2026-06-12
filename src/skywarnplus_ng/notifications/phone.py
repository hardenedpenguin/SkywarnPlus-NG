"""
Phone number normalization and validation (E.164).
"""

from __future__ import annotations

import re
from typing import Optional

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def normalize_phone_number(value: Optional[str]) -> Optional[str]:
    """
    Normalize a phone number to E.164 when possible.

    US numbers without a country code (10 digits) are assumed +1.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    if text.startswith("00"):
        text = "+" + text[2:]

    digits_only = re.sub(r"\D", "", text)
    if text.startswith("+"):
        candidate = "+" + digits_only
    elif len(digits_only) == 10:
        candidate = "+1" + digits_only
    elif len(digits_only) == 11 and digits_only.startswith("1"):
        candidate = "+" + digits_only
    else:
        return None

    if _E164_RE.match(candidate):
        return candidate
    return None


def validate_phone_number(value: Optional[str]) -> tuple[bool, str]:
    """Return (ok, error_message). Empty is allowed (optional field)."""
    if value is None or not str(value).strip():
        return True, ""
    if normalize_phone_number(value):
        return True, ""
    return False, "Phone must be a valid E.164 number (e.g. +15551234567)"
