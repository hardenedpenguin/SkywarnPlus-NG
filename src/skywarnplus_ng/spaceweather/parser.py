"""Parse NOAA SWPC space weather alerts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence

from ..geo_hazard.tts import sanitize_for_tts

_G_SCALE_RE = re.compile(r"\bG(\d)\b", re.IGNORECASE)
_R_SCALE_RE = re.compile(r"\bR(\d)\b", re.IGNORECASE)
_S_SCALE_RE = re.compile(r"\bS(\d)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedSpaceWeather:
    """Space weather alert parsed from SWPC alerts.json."""

    product_id: str
    title: str
    message: str
    message_type: str
    geomagnetic_scale: int
    radio_blackout_scale: int
    solar_radiation_scale: int
    announcement_key: str
    issued_utc: datetime
    tts_text: str


def _message_type_from_product_id(product_id: str) -> str:
    code = (product_id or "").upper()
    if code.startswith("SUM"):
        return "summary"
    if code.startswith("WAT"):
        return "watch"
    if code.startswith("WAR"):
        return "warning"
    if code.startswith("ALT"):
        return "alert"
    return "other"


def _parse_issue_datetime(date_str: str, time_str: str) -> datetime:
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _extract_scale(pattern: re.Pattern[str], text: str) -> int:
    match = pattern.search(text or "")
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def build_space_weather_tts(title: str, message: str) -> str:
    clean_title = sanitize_for_tts(title)
    clean_message = sanitize_for_tts(message)
    if clean_title and clean_message:
        snippet = clean_message[:240].strip()
        if len(clean_message) > 240:
            snippet += "."
        return f"{clean_title}. {snippet}"
    return clean_title or clean_message


def parse_swpc_alert_row(row: Sequence[Any]) -> Optional[ParsedSpaceWeather]:
    if not row or len(row) < 5:
        return None

    product_id = str(row[0] or "").strip()
    if not product_id:
        return None

    date_str = str(row[1] or "")
    time_str = str(row[2] or "")
    title = str(row[3] or "").strip()
    message = str(row[4] or "").strip()
    message_type = _message_type_from_product_id(product_id)
    issued = _parse_issue_datetime(date_str, time_str)
    announcement_key = f"{product_id}:{date_str}:{time_str}"

    geomagnetic_scale = _extract_scale(_G_SCALE_RE, f"{title} {message}")
    radio_blackout_scale = _extract_scale(_R_SCALE_RE, f"{title} {message}")
    solar_radiation_scale = _extract_scale(_S_SCALE_RE, f"{title} {message}")
    tts_text = build_space_weather_tts(title, message)
    if not tts_text:
        return None

    return ParsedSpaceWeather(
        product_id=product_id,
        title=title,
        message=message,
        message_type=message_type,
        geomagnetic_scale=geomagnetic_scale,
        radio_blackout_scale=radio_blackout_scale,
        solar_radiation_scale=solar_radiation_scale,
        announcement_key=announcement_key,
        issued_utc=issued,
        tts_text=tts_text,
    )


def parse_swpc_alerts(rows: List[Any]) -> List[ParsedSpaceWeather]:
    parsed: List[ParsedSpaceWeather] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, list):
            continue
        item = parse_swpc_alert_row(row)
        if item is None or item.announcement_key in seen:
            continue
        parsed.append(item)
        seen.add(item.announcement_key)
    parsed.sort(key=lambda a: a.issued_utc, reverse=True)
    return parsed
