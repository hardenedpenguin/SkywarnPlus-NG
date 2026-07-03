"""Parse USGS volcano notices (VONA) from HANS API."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..geo_hazard.tts import sanitize_for_tts
from ..nhc.parser import haversine_miles

_PSN_RE = re.compile(
    r"PSN:\s*([NS])\s*(\d+(?:\.\d+)?)\s+([EW])\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_COLOR_RANK = {"green": 0, "yellow": 1, "orange": 2, "red": 3, "unassigned": -1}


@dataclass(frozen=True)
class ParsedVolcano:
    """Volcano notice parsed from USGS VONA feed."""

    vnum: str
    name: str
    color_code: str
    observatory: str
    notice_type: str
    notice_issued: str
    announcement_key: str
    lat: Optional[float]
    lon: Optional[float]
    distance_miles: Optional[int]
    issued_utc: Optional[datetime]
    tts_text: str


def color_rank(color: str) -> int:
    return _COLOR_RANK.get((color or "").lower(), -1)


def parse_pseudo_navy_coord(hemisphere: str, value: str) -> float:
    # USGS pseudo format: N1925 = 19°25' -> 19 + 25/60
    val_int = int(round(float(value)))
    whole_deg = val_int // 100
    minutes = val_int % 100
    decimal = whole_deg + minutes / 60.0
    if hemisphere.upper() in ("S", "W"):
        decimal = -decimal
    return decimal


def extract_pseudo_coords(text: str) -> Optional[tuple[float, float]]:
    match = _PSN_RE.search(text or "")
    if not match:
        return None
    lat = parse_pseudo_navy_coord(match.group(1), match.group(2))
    lon = parse_pseudo_navy_coord(match.group(3), match.group(4))
    return lat, lon


def _parse_notice_issued(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def build_volcano_tts(name: str, color_code: str, notice_type: str) -> str:
    clean_name = sanitize_for_tts(name)
    clean_color = sanitize_for_tts(color_code)
    clean_type = sanitize_for_tts(notice_type)
    parts = [f"Volcano notice for {clean_name}."]
    if clean_color:
        parts.append(f"Aviation color code {clean_color}.")
    if clean_type:
        parts.append(f"Notice type {clean_type}.")
    return " ".join(parts)


def parse_volcano_notice(
    item: Dict[str, Any],
    *,
    origin_lat: Optional[float] = None,
    origin_lon: Optional[float] = None,
) -> Optional[ParsedVolcano]:
    vnum = str(item.get("vnum") or "").strip()
    if not vnum:
        return None

    name = str(item.get("vName") or item.get("volcano_name") or "Unknown volcano")
    color_code = str(item.get("colorCode") or item.get("color_code") or "unassigned")
    observatory = str(item.get("obs") or item.get("observatory") or "")
    notice_type = str(item.get("noticeType") or item.get("notice_type") or "")
    notice_issued = str(item.get("noticeIssued") or item.get("notice_issued") or "")
    notice_html = str(item.get("noticeHtml") or item.get("notice_html") or "")

    coords = extract_pseudo_coords(notice_html)
    lat = coords[0] if coords else None
    lon = coords[1] if coords else None
    distance_miles: Optional[int] = None
    if lat is not None and lon is not None and origin_lat is not None and origin_lon is not None:
        distance_miles = haversine_miles(origin_lat, origin_lon, lat, lon)

    issued_utc = _parse_notice_issued(notice_issued)
    announcement_key = f"{vnum}:{notice_issued or notice_type}"
    tts_text = build_volcano_tts(name, color_code, notice_type)

    return ParsedVolcano(
        vnum=vnum,
        name=name,
        color_code=color_code,
        observatory=observatory,
        notice_type=notice_type,
        notice_issued=notice_issued,
        announcement_key=announcement_key,
        lat=lat,
        lon=lon,
        distance_miles=distance_miles,
        issued_utc=issued_utc,
        tts_text=tts_text,
    )


def parse_volcano_notices(
    items: List[Dict[str, Any]],
    *,
    origin_lat: Optional[float] = None,
    origin_lon: Optional[float] = None,
) -> List[ParsedVolcano]:
    parsed: List[ParsedVolcano] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        notice = parse_volcano_notice(item, origin_lat=origin_lat, origin_lon=origin_lon)
        if notice is None or notice.announcement_key in seen:
            continue
        parsed.append(notice)
        seen.add(notice.announcement_key)
    parsed.sort(
        key=lambda n: n.issued_utc or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return parsed
