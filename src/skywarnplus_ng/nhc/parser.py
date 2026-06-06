"""Parse NHC GIS RSS/XML cyclone feeds."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


@dataclass(frozen=True)
class ParsedCyclone:
    center: str
    type: str
    name: str
    wallet: str
    atcf: str
    datetime_raw: str
    movement: str
    pressure: str
    wind: str
    headline: str

    @property
    def advisory_key(self) -> str:
        return f"{self.atcf}_{self.datetime_raw}"


def _extract_tag(line: str, tag: str) -> str:
    start = line.find(">") + 1
    end = line.rfind("<")
    if start <= 0 or end <= start:
        return ""
    return line[start:end].strip()


def parse_nhc_cyclone_xml(xml_text: str) -> List[ParsedCyclone]:
    """
    Parse NHC GIS RSS XML using a line-oriented approach (tolerant of namespace quirks).
    """
    storms: List[ParsedCyclone] = []
    inside = False
    fields = {
        "center": "",
        "type": "",
        "name": "",
        "wallet": "",
        "atcf": "",
        "datetime_raw": "",
        "movement": "",
        "pressure": "",
        "wind": "",
        "headline": "",
    }

    for raw_line in xml_text.splitlines():
        line = raw_line.strip()
        if "<description>" in line:
            continue
        if "<nhc:Cyclone" in line or "<Cyclone" in line:
            inside = True
            continue
        if "</nhc:Cyclone>" in line or "</Cyclone>" in line:
            if fields["atcf"] or fields["name"]:
                storms.append(ParsedCyclone(**fields))
            inside = False
            fields = {key: "" for key in fields}
            continue
        if not inside:
            continue

        for tag, key in (
            ("center", "center"),
            ("type", "type"),
            ("name", "name"),
            ("wallet", "wallet"),
            ("atcf", "atcf"),
            ("datetime", "datetime_raw"),
            ("movement", "movement"),
            ("pressure", "pressure"),
            ("wind", "wind"),
            ("headline", "headline"),
        ):
            if f"<nhc:{tag}>" in line or f"<{tag}>" in line:
                fields[key] = _extract_tag(line, tag)

    return storms


def filter_active_cyclones(cyclones: List[ParsedCyclone]) -> List[ParsedCyclone]:
    active: List[ParsedCyclone] = []
    for cyclone in cyclones:
        wind_digits = re.search(r"(\d+)", cyclone.wind or "")
        wind_val = int(wind_digits.group(1)) if wind_digits else 0
        headline = (cyclone.headline or "").upper()
        ctype = (cyclone.type or "").upper()
        if wind_val == 0:
            continue
        if "DISSIPATED" in headline or "POST-TROPICAL" in headline:
            continue
        if "POST-TROPICAL" in ctype:
            continue
        active.append(cyclone)
    return active


def parse_cyclone_datetime(raw: str) -> Optional[datetime]:
    text = (raw or "").strip()
    if not text:
        return None
    if not re.search(r"\b\d{4}\b", text):
        text = f"{text} {datetime.now(timezone.utc).year}"
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        return datetime.strptime(text, "%I:%M %p %Z %a %b %d %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_cyclone_current(cyclone: ParsedCyclone, max_age_hours: int) -> bool:
    dt = parse_cyclone_datetime(cyclone.datetime_raw)
    if not dt:
        return False
    age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    return age_hours <= max_age_hours


def parse_coordinates(center: str) -> Optional[tuple[float, float]]:
    if not center or "," not in center:
        return None
    lat_str, lon_str = center.split(",", 1)
    try:
        return float(lat_str.strip()), float(lon_str.strip())
    except ValueError:
        return None


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    from math import asin, cos, radians, sin, sqrt

    r = 3959.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return int(round(2 * r * asin(sqrt(a))))


def clean_cyclone_headline(headline: str) -> str:
    text = (headline or "").replace("...", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if text.isupper():
        text = text.title()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def build_storm_summary(cyclone: ParsedCyclone) -> str:
    parts: List[str] = []
    if cyclone.center:
        parts.append(f"Located near {cyclone.center}.")
    if cyclone.wind:
        parts.append(f"Wind speed {cyclone.wind}.")
    if cyclone.movement:
        parts.append(f"Moving {cyclone.movement}.")
    return " ".join(parts)


def build_cyclone_tts_text(cyclone: ParsedCyclone) -> str:
    headline = clean_cyclone_headline(cyclone.headline)
    summary = build_storm_summary(cyclone)
    base = f"{cyclone.type} {cyclone.name}.".strip()
    if headline:
        return f"{base} {headline} {summary}".strip()
    return f"{base} {summary}".strip()


def is_hurricane(cyclone_type: str) -> bool:
    return "hurricane" in (cyclone_type or "").lower()
