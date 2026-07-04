"""Mobile zone resolution using gpsd and NWS point lookup."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from .gpsd import GpsFix, poll_gpsd_fix

if TYPE_CHECKING:
    from ..api.nws_client import NWSClient
    from ..core.config import AppConfig, NodeConfig

logger = logging.getLogger(__name__)


def _valid_gps_fix(fix: GpsFix, config: AppConfig) -> bool:
    age_seconds = (datetime.now(timezone.utc) - fix.fix_time).total_seconds()
    if age_seconds > config.gpsd.stale_seconds:
        return False
    if (
        config.gpsd.min_accuracy_meters is not None
        and fix.accuracy_m is not None
        and fix.accuracy_m > config.gpsd.min_accuracy_meters
    ):
        return False
    return True


class MobileCountyService:
    """Resolve effective NWS zones for GPS-controlled nodes."""

    def __init__(self, config: AppConfig, nws_client: NWSClient) -> None:
        self.config = config
        self.nws_client = nws_client
        self._active_gps_zone: Optional[str] = None
        self._active_gps_zone_name: Optional[str] = None
        self._candidate_zone: Optional[str] = None
        self._candidate_polls: int = 0
        self._last_fix: Optional[GpsFix] = None
        self._last_refresh_at: Optional[datetime] = None
        self._gps_active: bool = False
        self._inactive_reason: Optional[str] = None
        self._position_source: Optional[str] = None

    @property
    def active_gps_county_code(self) -> Optional[str]:
        """Active GPS zone code (forecast zone when GPS is in use)."""
        return self._active_gps_zone

    @property
    def active_gps_county_name(self) -> Optional[str]:
        return self._active_gps_zone_name

    def is_gps_active(self) -> bool:
        return self._gps_active

    def get_position(self) -> Optional[tuple[float, float]]:
        """Return lat/lon from a fresh gpsd fix when available."""
        if not self._last_fix:
            return None
        if not _valid_gps_fix(self._last_fix, self.config):
            return None
        return self._last_fix.latitude, self._last_fix.longitude

    def _static_position(self) -> Optional[tuple[float, float]]:
        pos = self.config.geo_hazard_position
        if pos.static_lat is not None and pos.static_lon is not None:
            return float(pos.static_lat), float(pos.static_lon)
        return None

    def _position_monitoring_configured(self) -> bool:
        """True when a GPS-controlled node can resolve an NWS forecast zone."""
        if self.get_gps_controlled_node() is None:
            return False
        pos = self.config.geo_hazard_position
        if self.config.gpsd.enabled and pos.use_gps_position:
            return True
        return self._static_position() is not None

    def is_position_monitoring_configured(self) -> bool:
        """Public check for whether position-based NWS zone monitoring is configured."""
        return self._position_monitoring_configured()

    async def _resolve_monitoring_coordinates(
        self,
    ) -> tuple[Optional[tuple[float, float, str]], Optional[str]]:
        """
        Resolve coordinates for NWS forecast zone lookup.

        Prefers a fresh gpsd fix when enabled; falls back to Geo Hazard Position
        static latitude/longitude. Returns (coords, inactive_reason).
        """
        pos_cfg = self.config.geo_hazard_position
        if self.config.gpsd.enabled and pos_cfg.use_gps_position:
            fix = await poll_gpsd_fix(
                host=self.config.gpsd.host,
                port=self.config.gpsd.port,
                timeout=float(self.config.gpsd.connect_timeout_seconds),
            )
            if fix is None:
                static = self._static_position()
                if static:
                    return (static[0], static[1], "static"), None
                return None, "no_fix"

            if (datetime.now(timezone.utc) - fix.fix_time).total_seconds() > self.config.gpsd.stale_seconds:
                static = self._static_position()
                if static:
                    return (static[0], static[1], "static"), None
                return None, "stale"

            if (
                self.config.gpsd.min_accuracy_meters is not None
                and fix.accuracy_m is not None
                and fix.accuracy_m > self.config.gpsd.min_accuracy_meters
            ):
                static = self._static_position()
                if static:
                    return (static[0], static[1], "static"), None
                return None, "low_accuracy"

            self._last_fix = fix
            return (fix.latitude, fix.longitude, "gpsd"), None

        static = self._static_position()
        if static:
            return (static[0], static[1], "static"), None
        return None, "no_position"

    def _effective_gps_zone(self) -> Optional[str]:
        """Forecast zone used for polling; active zone, or candidate while switching."""
        if self._active_gps_zone:
            return self._active_gps_zone
        return self._candidate_zone

    def get_gps_controlled_node(self) -> Optional[int]:
        """Return the node number marked gps_controlled, if any."""
        for node in self.config.asterisk.nodes:
            if isinstance(node, int):
                continue
            node_config: Optional[NodeConfig]
            if hasattr(node, "gps_controlled"):
                node_config = node
            elif isinstance(node, dict):
                from ..core.config import NodeConfig

                node_config = NodeConfig(**node)
            else:
                continue
            if node_config.gps_controlled:
                return node_config.number
        return None

    async def refresh(self) -> None:
        """Update active NWS forecast zone from gpsd and/or static coordinates."""
        self._last_refresh_at = datetime.now(timezone.utc)

        if self.get_gps_controlled_node() is None:
            self._set_inactive("no_gps_node")
            return

        if not self._position_monitoring_configured():
            self._set_inactive("disabled")
            return

        resolved_coords, inactive_reason = await self._resolve_monitoring_coordinates()
        if not resolved_coords:
            self._set_inactive(inactive_reason or "no_position")
            return

        latitude, longitude, position_source = resolved_coords
        self._position_source = position_source
        zone_resolved = await self.nws_client.resolve_forecast_zone_from_coordinates(
            latitude, longitude
        )
        if not zone_resolved:
            self._set_inactive("zone_unresolved")
            return

        zone_code, zone_name = zone_resolved
        self._apply_hysteresis(zone_code, zone_name)
        effective = self._effective_gps_zone()
        if effective:
            self._gps_active = True
            if (
                self._candidate_zone
                and self._active_gps_zone
                and self._candidate_zone != self._active_gps_zone
            ):
                self._inactive_reason = "hysteresis_pending"
            else:
                self._inactive_reason = None
        else:
            self._gps_active = False
            self._inactive_reason = "hysteresis_pending"

    def _apply_hysteresis(self, zone_code: str, zone_name: str) -> None:
        threshold = max(1, int(self.config.gpsd.hysteresis_polls))

        # First acquisition: lock immediately (hysteresis is for zone switches while moving)
        if self._active_gps_zone is None:
            self._active_gps_zone = zone_code
            self._active_gps_zone_name = zone_name
            self._candidate_zone = zone_code
            self._candidate_polls = threshold
            logger.info("GPS forecast zone acquired: %s (%s)", zone_code, zone_name)
            return

        if zone_code == self._active_gps_zone:
            self._candidate_zone = zone_code
            self._candidate_polls = threshold
            self._active_gps_zone_name = zone_name
            return

        if zone_code == self._candidate_zone:
            self._candidate_polls += 1
        else:
            self._candidate_zone = zone_code
            self._candidate_polls = 1

        if self._candidate_polls >= threshold:
            if self._active_gps_zone != zone_code:
                logger.info(
                    "GPS forecast zone changed: %s -> %s (%s)",
                    self._active_gps_zone,
                    zone_code,
                    zone_name,
                )
            self._active_gps_zone = zone_code
            self._active_gps_zone_name = zone_name

    def _set_inactive(self, reason: str) -> None:
        if self._gps_active:
            logger.info(
                "GPS mobile county inactive (%s) for node %s",
                reason,
                self.get_gps_controlled_node(),
            )
        self._gps_active = False
        self._inactive_reason = reason
        self._active_gps_zone = None
        self._active_gps_zone_name = None
        self._candidate_zone = None
        self._candidate_polls = 0
        self._position_source = None

    def _enabled_county_codes(self) -> Set[str]:
        return {county.code for county in self.config.counties if county.enabled}

    def _node_is_gps_controlled(self, node_number: int) -> bool:
        node_config = self.config.asterisk.get_node_config(node_number)
        return bool(node_config and node_config.gps_controlled)

    def is_gps_only_node(self, node_number: int) -> bool:
        """True when the node uses GPS exclusively with no static county fallback."""
        return self._is_gps_only_node(node_number)

    def _is_gps_only_node(self, node_number: int) -> bool:
        """True when the node uses GPS exclusively with no static county fallback."""
        node_config = self.config.asterisk.get_node_config(node_number)
        if not node_config or not node_config.gps_controlled:
            return False
        if node_config.gps_only:
            return True
        return not node_config.counties

    def _static_counties_for_node(self, node_number: int) -> Optional[Set[str]]:
        """Static county set for a node. None means all enabled counties."""
        if self._is_gps_only_node(node_number):
            return set()
        static = self.config.asterisk.get_counties_for_node(node_number)
        enabled = self._enabled_county_codes()
        if static:
            return set(static) & enabled
        if enabled:
            return None
        return set()

    def get_fetch_counties(self) -> List[str]:
        """Zone/county codes to poll from NWS this cycle."""
        fetch: Set[str] = set()
        enabled = self._enabled_county_codes()

        for node_number in self.config.asterisk.get_nodes_list():
            if self._node_is_gps_controlled(node_number) and self.is_gps_active():
                effective = self._effective_gps_zone()
                if effective:
                    fetch.add(effective)
                continue

            static = self._static_counties_for_node(node_number)
            if static is None:
                fetch.update(enabled)
            else:
                fetch.update(static)

        return sorted(fetch)

    def get_effective_counties_for_node(self, node_number: int) -> Optional[Set[str]]:
        """
        Counties used for per-node alert display and announcements.

        Returns None when the node monitors all enabled counties (non-GPS mode).
        """
        if self._node_is_gps_controlled(node_number) and self.is_gps_active():
            effective = self._effective_gps_zone()
            if effective:
                return {effective}
        return self._static_counties_for_node(node_number)

    def get_nodes_for_counties(self, alert_county_codes: List[str]) -> List[int]:
        """Determine target nodes for an alert, honoring GPS forecast zone overrides."""
        if not alert_county_codes:
            return []

        alert_set = set(alert_county_codes)
        result: List[int] = []

        for node in self.config.asterisk.nodes:
            if isinstance(node, int):
                result.append(node)
                continue

            if hasattr(node, "number"):
                node_number = node.number
                node_counties = node.counties
                gps_controlled = bool(getattr(node, "gps_controlled", False))
            elif isinstance(node, dict):
                node_number = int(node.get("number", 0))
                node_counties = node.get("counties")
                gps_controlled = bool(node.get("gps_controlled", False))
            else:
                continue

            if gps_controlled:
                effective = self._effective_gps_zone()
                if self.is_gps_active() and effective:
                    if effective in alert_set:
                        result.append(node_number)
                elif self._is_gps_only_node(node_number):
                    continue
                elif node_counties:
                    if any(code in node_counties for code in alert_set):
                        result.append(node_number)
                else:
                    result.append(node_number)
            elif node_counties:
                if any(code in node_counties for code in alert_set):
                    result.append(node_number)
            else:
                result.append(node_number)

        return sorted(set(result))

    def get_monitored_county_codes(self) -> Set[str]:
        """All zone/county codes currently in use for alert filtering."""
        monitored = self._enabled_county_codes()
        effective = self._effective_gps_zone()
        if self.is_gps_active() and effective:
            monitored.add(effective)
        return monitored

    def get_status(self) -> Dict[str, Any]:
        """GPS state for dashboard and API consumers."""
        node = self.get_gps_controlled_node()
        effective_zone = self._effective_gps_zone()
        status: Dict[str, Any] = {
            "enabled": self._position_monitoring_configured(),
            "poll_counties": self.get_fetch_counties(),
            "controlled_node": node,
            "active": self.is_gps_active(),
            "reason": self._inactive_reason,
            "position_source": self._position_source,
            "zone_code": effective_zone,
            "zone_name": self._active_gps_zone_name,
            # Backward-compatible keys; values are forecast zones when GPS is active.
            "county_code": effective_zone,
            "county_name": self._active_gps_zone_name,
            "candidate_zone": self._candidate_zone,
            "candidate_polls": self._candidate_polls,
            "hysteresis_threshold": max(1, int(self.config.gpsd.hysteresis_polls)),
            "last_refresh_at": (
                self._last_refresh_at.isoformat() if self._last_refresh_at else None
            ),
        }
        if self._last_fix:
            status.update(
                {
                    "last_fix_at": self._last_fix.fix_time.isoformat(),
                    "latitude": self._last_fix.latitude,
                    "longitude": self._last_fix.longitude,
                    "accuracy_m": self._last_fix.accuracy_m,
                    "mode": self._last_fix.mode,
                }
            )
        elif self._position_source == "static":
            static = self._static_position()
            if static:
                status.update({"latitude": static[0], "longitude": static[1]})
        if node is not None:
            effective = self.get_effective_counties_for_node(node)
            status["gps_only"] = self._is_gps_only_node(node)
            status["effective_counties"] = sorted(effective) if effective is not None else None
        return status
