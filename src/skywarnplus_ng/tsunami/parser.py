"""Parse NWS tsunami alerts from GeoJSON features."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..geo_hazard.tts import sanitize_for_tts

_TSUNAMI_EVENT_RE = re.compile(r"tsunami", re.IGNORECASE)
_LEVEL_RANK = {"watch": 1, "advisory": 2, "warning": 3, "statement": 0}


@dataclass(frozen=True)
class ParsedTsunami:
    """Tsunami alert parsed from an NWS feature."""

    alert_id: str
    event: str
    severity: str
    headline: str
    level: str
    announcement_key: str
    issued_utc: datetime
    tts_text: str


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def tsunami_level_from_event(event: str) -> str:
    text = (event or "").lower()
    if "warning" in text:
        return "warning"
    if "advisory" in text:
        return "advisory"
    if "watch" in text:
        return "watch"
    if "statement" in text:
        return "statement"
    return "unknown"


def level_rank(level: str) -> int:
    return _LEVEL_RANK.get((level or "").lower(), 0)


def is_tsunami_event(event: str) -> bool:
    return bool(_TSUNAMI_EVENT_RE.search(event or ""))


def is_tsunami_feature(feature: Dict[str, Any]) -> bool:
    props = feature.get("properties") if isinstance(feature, dict) else None
    if not isinstance(props, dict):
        return False
    event = str(props.get("event") or "")
    return is_tsunami_event(event)


def build_tsunami_tts(event: str, headline: str) -> str:
    parts: List[str] = []
    clean_event = sanitize_for_tts(event)
    clean_headline = sanitize_for_tts(headline)
    if clean_event:
        parts.append(clean_event + ".")
    if clean_headline and clean_headline.lower() != clean_event.lower():
        parts.append(clean_headline + ".")
    return " ".join(parts).strip()


def parse_tsunami_feature(feature: Dict[str, Any]) -> Optional[ParsedTsunami]:
    if not is_tsunami_feature(feature):
        return None

    props = feature.get("properties") or {}
    alert_id = str(props.get("id") or props.get("@id") or "").strip()
    if not alert_id:
        return None

    event = str(props.get("event") or "Tsunami Alert")
    severity = str(props.get("severity") or "")
    headline = str(props.get("headline") or event)
    level = tsunami_level_from_event(event)
    issued = (
        _parse_iso_datetime(props.get("sent"))
        or _parse_iso_datetime(props.get("effective"))
        or datetime.now(timezone.utc)
    )
    announcement_key = alert_id
    tts_text = build_tsunami_tts(event, headline)
    if not tts_text:
        return None

    return ParsedTsunami(
        alert_id=alert_id,
        event=event,
        severity=severity,
        headline=headline,
        level=level,
        announcement_key=announcement_key,
        issued_utc=issued,
        tts_text=tts_text,
    )


def parse_tsunami_features(
    features: List[Dict[str, Any]],
    *,
    min_level: str,
) -> List[ParsedTsunami]:
    min_rank = level_rank(min_level)
    parsed: List[ParsedTsunami] = []
    seen: set[str] = set()

    for feature in features:
        item = parse_tsunami_feature(feature)
        if item is None or item.announcement_key in seen:
            continue
        if level_rank(item.level) < min_rank:
            continue
        parsed.append(item)
        seen.add(item.announcement_key)

    parsed.sort(key=lambda t: t.issued_utc, reverse=True)
    return parsed
