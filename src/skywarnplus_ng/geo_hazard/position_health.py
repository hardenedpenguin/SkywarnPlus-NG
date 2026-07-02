"""GPS/static position details for geo-hazard health checks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

if TYPE_CHECKING:
    from ..location.mobile_counties import MobileCountyService


def position_source_label(
    *,
    use_gps_position: bool,
    static_lat: Optional[float],
    static_lon: Optional[float],
    mobile_service: Optional[MobileCountyService],
    gpsd_enabled: bool,
) -> str:
    if use_gps_position and mobile_service and mobile_service.get_position():
        if gpsd_enabled:
            return "gpsd"
        return "gpsd_fix"
    if static_lat is not None and static_lon is not None:
        return "static"
    return "none"


def append_gps_health_details(
    details: Dict[str, Any],
    *,
    use_gps_position: bool,
    gpsd_enabled: bool,
    mobile_service: Optional[MobileCountyService],
    position: Optional[Tuple[float, float]],
) -> None:
    if use_gps_position and gpsd_enabled and mobile_service:
        gps = mobile_service.get_status()
        details["gps_active"] = gps.get("active")
        details["gps_reason"] = gps.get("reason")
        details["gps_county"] = gps.get("county_code")
        if not position:
            details["position"] = None


def missing_position_message(
    *,
    use_gps_position: bool,
    gpsd_enabled: bool,
    mobile_service: Optional[MobileCountyService],
) -> str:
    if use_gps_position and gpsd_enabled and mobile_service:
        gps = mobile_service.get_status()
        reason = gps.get("reason") or "no fix"
        return f"No GPS position ({reason})"
    return "No position available (enable gpsd or set static lat/lon in Geo Hazard Position)"
