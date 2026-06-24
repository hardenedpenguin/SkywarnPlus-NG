"""TTS text normalization for external hazard feed strings."""

from __future__ import annotations

import html
import re


def sanitize_for_tts(text: str, *, max_length: int = 200) -> str:
    """Normalize place names and headlines for spoken announcements."""
    cleaned = html.unescape(str(text or ""))
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned.isupper() and len(cleaned) > 4:
        cleaned = cleaned.title()
    if len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 1].rstrip() + "…"
    return cleaned or "unknown location"
