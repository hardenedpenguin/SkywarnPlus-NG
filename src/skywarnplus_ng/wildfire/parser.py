"""Parse WFIGS wildfire GeoJSON and build TTS text."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from ..nhc.parser import haversine_miles

PRESCRIBED_TYPE_KINDS = frozenset({"rx", "prescribed"})


@dataclass(frozen=True)
class ParsedWildfire:
    incident_id: str
    name: str
    acres: float
    percent_contained: Optional[int]
    discovery_utc: Optional[datetime]
    incident_type_kind: str
    feature_category: str
    latitude: float
    longitude: float
    distance_miles: int
    announcement_key: str

    @property
    def tts_text(self) -> str:
        acres_str = f"{int(round(self.acres)):,}" if self.acres >= 100 else f"{self.acres:.0f}"
        contained_part = ""
        if self.percent_contained is not None:
            contained_part = f", {self.percent_contained} percent contained"
        return (
            f"Wildfire alert: {self.name}, {acres_str} acres, "
            f"{self.distance_miles} miles from your position{contained_part}."
        )


def _parse_discovery_time(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            ms = float(value)
            if ms > 1e12:
                return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
            return datetime.fromtimestamp(ms, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def geometry_centroid(geometry: dict[str, Any]) -> Optional[Tuple[float, float]]:
    if not isinstance(geometry, dict):
        return None
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or not coords:
        return None

    ring: list[Any]
    if gtype == "Point" and len(coords) >= 2:
        return float(coords[1]), float(coords[0])
    if gtype == "Polygon":
        ring = coords[0]
    elif gtype == "MultiPolygon" and coords and isinstance(coords[0], list):
        ring = coords[0][0]
    else:
        return None

    if not isinstance(ring, list) or not ring:
        return None
    try:
        lats = [float(point[1]) for point in ring]
        lons = [float(point[0]) for point in ring]
    except (IndexError, TypeError, ValueError):
        return None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def is_prescribed_fire(*, incident_type_kind: str, feature_category: str) -> bool:
    kind = (incident_type_kind or "").strip().lower()
    if kind in PRESCRIBED_TYPE_KINDS:
        return True
    category = (feature_category or "").lower()
    return "prescribed" in category


def parse_wildfire_feature(
    feature: dict[str, Any],
    *,
    origin_lat: float,
    origin_lon: float,
) -> Optional[ParsedWildfire]:
    if not isinstance(feature, dict):
        return None

    props = feature.get("properties")
    geom = feature.get("geometry")
    if not isinstance(props, dict) or not isinstance(geom, dict):
        return None

    centroid = geometry_centroid(geom)
    if centroid is None:
        return None
    lat, lon = centroid

    try:
        acres = float(props.get("poly_GISAcres") or props.get("GISAcres") or 0)
    except (TypeError, ValueError):
        acres = 0.0

    name = str(
        props.get("poly_IncidentName")
        or props.get("IncidentName")
        or props.get("poly_IncidentNameShort")
        or "Unknown fire"
    ).strip()
    incident_id = str(
        props.get("poly_IrwinID") or props.get("IrwinID") or feature.get("id") or name
    )
    incident_type_kind = str(
        props.get("attr_IncidentTypeKind") or props.get("IncidentTypeKind") or ""
    )
    feature_category = str(props.get("poly_FeatureCategory") or props.get("FeatureCategory") or "")

    percent_raw = props.get("attr_PercentContained")
    if percent_raw is None:
        percent_raw = props.get("PercentContained")
    percent_contained: Optional[int] = None
    if percent_raw is not None and str(percent_raw).strip() != "":
        try:
            percent_contained = int(float(percent_raw))
        except (TypeError, ValueError):
            percent_contained = None

    discovery_utc = _parse_discovery_time(
        props.get("attr_FireDiscoveryDateTime") or props.get("FireDiscoveryDateTime")
    )
    distance = haversine_miles(origin_lat, origin_lon, lat, lon)
    announcement_key = incident_id

    return ParsedWildfire(
        incident_id=incident_id,
        name=name,
        acres=acres,
        percent_contained=percent_contained,
        discovery_utc=discovery_utc,
        incident_type_kind=incident_type_kind,
        feature_category=feature_category,
        latitude=lat,
        longitude=lon,
        distance_miles=distance,
        announcement_key=announcement_key,
    )


def parse_wildfire_collection(
    data: dict[str, Any],
    *,
    origin_lat: float,
    origin_lon: float,
) -> list[ParsedWildfire]:
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return []

    parsed: list[ParsedWildfire] = []
    for feature in features:
        incident = parse_wildfire_feature(feature, origin_lat=origin_lat, origin_lon=origin_lon)
        if incident:
            parsed.append(incident)
    return parsed
