"""Parse USGS earthquake GeoJSON and build TTS text."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from ..nhc.parser import haversine_miles


@dataclass(frozen=True)
class ParsedEarthquake:
    event_id: str
    magnitude: float
    place: str
    latitude: float
    longitude: float
    depth_km: float
    time_utc: datetime
    status: str
    tsunami: bool
    distance_miles: int
    announcement_key: str

    @property
    def tts_text(self) -> str:
        mag = self.magnitude
        mag_str = f"{mag:.1f}" if mag < 10 else f"{mag:.0f}"
        depth_part = ""
        if self.depth_km and self.depth_km >= 1:
            depth_part = f", depth {int(round(self.depth_km))} kilometers"
        tsunami_part = " Tsunami information is available for this event." if self.tsunami else ""
        return (
            f"Earthquake magnitude {mag_str}, {self.distance_miles} miles from your position, "
            f"{self.place}{depth_part}.{tsunami_part}"
        ).strip()


def _parse_time_ms(value: Any) -> Optional[datetime]:
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def parse_earthquake_feature(
    feature: dict[str, Any],
    *,
    origin_lat: float,
    origin_lon: float,
) -> Optional[ParsedEarthquake]:
    if not isinstance(feature, dict):
        return None
    event_id = str(feature.get("id") or "").strip()
    if not event_id:
        return None

    props = feature.get("properties")
    geom = feature.get("geometry")
    if not isinstance(props, dict) or not isinstance(geom, dict):
        return None

    coords = geom.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        return None

    try:
        lon = float(coords[0])
        lat = float(coords[1])
        depth_km = float(coords[2]) if len(coords) > 2 else 0.0
    except (TypeError, ValueError):
        return None

    try:
        magnitude = float(props.get("mag"))
    except (TypeError, ValueError):
        return None

    place = str(props.get("place") or props.get("title") or "unknown location").strip()
    time_utc = _parse_time_ms(props.get("time"))
    if time_utc is None:
        return None

    status = str(props.get("status") or "").lower()
    tsunami = bool(int(props.get("tsunami") or 0))
    distance = haversine_miles(origin_lat, origin_lon, lat, lon)

    return ParsedEarthquake(
        event_id=event_id,
        magnitude=magnitude,
        place=place,
        latitude=lat,
        longitude=lon,
        depth_km=depth_km,
        time_utc=time_utc,
        status=status,
        tsunami=tsunami,
        distance_miles=distance,
        announcement_key=event_id,
    )


def parse_earthquake_collection(
    data: dict[str, Any],
    *,
    origin_lat: float,
    origin_lon: float,
) -> list[ParsedEarthquake]:
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return []

    parsed: list[ParsedEarthquake] = []
    for feature in features:
        event = parse_earthquake_feature(feature, origin_lat=origin_lat, origin_lon=origin_lon)
        if event:
            parsed.append(event)
    return parsed
