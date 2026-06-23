"""Resolve lat/lon for position-based hazard monitoring."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from .mobile_counties import MobileCountyService


def get_monitoring_position(
    *,
    use_gps_position: bool,
    static_lat: Optional[float],
    static_lon: Optional[float],
    mobile_service: Optional[MobileCountyService],
) -> Optional[Tuple[float, float]]:
    """GPS fix when enabled, else static coordinates."""
    if use_gps_position and mobile_service:
        pos = mobile_service.get_position()
        if pos:
            return pos
    if static_lat is not None and static_lon is not None:
        return float(static_lat), float(static_lon)
    return None
