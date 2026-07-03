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
_MESSAGE_TYPE_LINE_RE = re.compile(
    r"^(?:EXTENDED\s+)?(WATCH|WARNING|ALERT|SUMMARY)\s*:",
    re.IGNORECASE,
)


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


def _message_type_from_message(message: str) -> Optional[str]:
    for line in (message or "").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        match = _MESSAGE_TYPE_LINE_RE.match(line)
        if not match:
            continue
        kind = match.group(1).lower()
        if kind == "summary":
            return "summary"
        if kind == "watch":
            return "watch"
        if kind == "warning":
            return "warning"
        if kind == "alert":
            return "alert"
    return None


def _resolve_message_type(product_id: str, message: str) -> str:
    from_message = _message_type_from_message(message)
    if from_message:
        return from_message
    from_product = _message_type_from_product_id(product_id)
    if from_product != "other":
        return from_product
    return "other"


def _extract_title_from_message(message: str) -> str:
    for line in (message or "").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("Space Weather Message Code:"):
            continue
        if line.startswith("Serial Number:"):
            continue
        if line.startswith("Issue Time:"):
            continue
        if _MESSAGE_TYPE_LINE_RE.match(line):
            return line
    return ""


def _parse_issue_datetime(date_str: str, time_str: str = "") -> datetime:
    raw = f"{date_str} {time_str}".strip() if time_str else (date_str or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
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


def _build_parsed_space_weather(
    *,
    product_id: str,
    title: str,
    message: str,
    date_str: str,
    time_str: str,
    announcement_key: str,
) -> Optional[ParsedSpaceWeather]:
    if not product_id:
        return None

    title = title.strip()
    message = message.strip()
    if not title:
        title = _extract_title_from_message(message)
    message_type = _resolve_message_type(product_id, message)
    issued = _parse_issue_datetime(date_str, time_str)

    combined = f"{title} {message}"
    geomagnetic_scale = _extract_scale(_G_SCALE_RE, combined)
    radio_blackout_scale = _extract_scale(_R_SCALE_RE, combined)
    solar_radiation_scale = _extract_scale(_S_SCALE_RE, combined)
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


def parse_swpc_alert_row(row: Sequence[Any]) -> Optional[ParsedSpaceWeather]:
    if not row or len(row) < 5:
        return None

    product_id = str(row[0] or "").strip()
    date_str = str(row[1] or "")
    time_str = str(row[2] or "")
    title = str(row[3] or "")
    message = str(row[4] or "")
    announcement_key = f"{product_id}:{date_str}:{time_str}"
    return _build_parsed_space_weather(
        product_id=product_id,
        title=title,
        message=message,
        date_str=date_str,
        time_str=time_str,
        announcement_key=announcement_key,
    )


def parse_swpc_alert_dict(item: dict[str, Any]) -> Optional[ParsedSpaceWeather]:
    product_id = str(item.get("product_id") or "").strip()
    issue_datetime = str(item.get("issue_datetime") or "").strip()
    message = str(item.get("message") or "")
    if not product_id or not message:
        return None

    date_str = issue_datetime
    time_str = ""
    if " " in issue_datetime:
        date_str, time_str = issue_datetime.split(" ", 1)

    title = str(item.get("title") or "")
    announcement_key = f"{product_id}:{issue_datetime}"
    return _build_parsed_space_weather(
        product_id=product_id,
        title=title,
        message=message,
        date_str=date_str,
        time_str=time_str,
        announcement_key=announcement_key,
    )


def parse_swpc_alert_item(item: Any) -> Optional[ParsedSpaceWeather]:
    if isinstance(item, dict):
        return parse_swpc_alert_dict(item)
    if isinstance(item, list):
        return parse_swpc_alert_row(item)
    return None


def parse_swpc_alerts(rows: List[Any]) -> List[ParsedSpaceWeather]:
    parsed: List[ParsedSpaceWeather] = []
    seen: set[str] = set()
    for row in rows:
        item = parse_swpc_alert_item(row)
        if item is None or item.announcement_key in seen:
            continue
        parsed.append(item)
        seen.add(item.announcement_key)
    parsed.sort(key=lambda a: a.issued_utc, reverse=True)
    return parsed
