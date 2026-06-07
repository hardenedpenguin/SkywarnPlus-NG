"""Mobile county resolution using gpsd and NWS point lookup."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from .gpsd import GpsFix, poll_gpsd_fix

if TYPE_CHECKING:
    from ..api.nws_client import NWSClient
    from ..core.config import AppConfig, NodeConfig

logger = logging.getLogger(__name__)


class MobileCountyService:
    """Resolve effective counties for GPS-controlled nodes."""

    def __init__(self, config: AppConfig, nws_client: NWSClient) -> None:
        self.config = config
        self.nws_client = nws_client
        self._active_gps_county: Optional[str] = None
        self._active_gps_county_name: Optional[str] = None
        self._candidate_county: Optional[str] = None
        self._candidate_polls: int = 0
        self._last_fix: Optional[GpsFix] = None
        self._last_refresh_at: Optional[datetime] = None
        self._gps_active: bool = False
        self._inactive_reason: Optional[str] = None

    @property
    def active_gps_county_code(self) -> Optional[str]:
        return self._active_gps_county

    @property
    def active_gps_county_name(self) -> Optional[str]:
        return self._active_gps_county_name

    def is_gps_active(self) -> bool:
        return self._gps_active

    def get_position(self) -> Optional[tuple[float, float]]:
        """Return the current gpsd fix lat/lon when the fix is fresh and usable."""
        if not self._last_fix:
            return None
        age_seconds = (datetime.now(timezone.utc) - self._last_fix.fix_time).total_seconds()
        if age_seconds > self.config.gpsd.stale_seconds:
            return None
        if (
            self.config.gpsd.min_accuracy_meters is not None
            and self._last_fix.accuracy_m is not None
            and self._last_fix.accuracy_m > self.config.gpsd.min_accuracy_meters
        ):
            return None
        return self._last_fix.latitude, self._last_fix.longitude

    def _effective_gps_county(self) -> Optional[str]:
        """County used for polling; active county, or candidate while switching."""
        if self._active_gps_county:
            return self._active_gps_county
        return self._candidate_county

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
        """Poll gpsd and update active GPS county state."""
        self._last_refresh_at = datetime.now(timezone.utc)

        if not self.config.gpsd.enabled:
            self._set_inactive("disabled")
            return

        if self.get_gps_controlled_node() is None:
            self._set_inactive("no_gps_node")
            return

        fix = await poll_gpsd_fix(
            host=self.config.gpsd.host,
            port=self.config.gpsd.port,
            timeout=float(self.config.gpsd.connect_timeout_seconds),
        )
        if fix is None:
            self._set_inactive("no_fix")
            return

        age_seconds = (datetime.now(timezone.utc) - fix.fix_time).total_seconds()
        if age_seconds > self.config.gpsd.stale_seconds:
            self._set_inactive("stale")
            return

        if (
            self.config.gpsd.min_accuracy_meters is not None
            and fix.accuracy_m is not None
            and fix.accuracy_m > self.config.gpsd.min_accuracy_meters
        ):
            self._set_inactive("low_accuracy")
            return

        self._last_fix = fix
        resolved = await self.nws_client.resolve_county_from_coordinates(
            fix.latitude, fix.longitude
        )
        if not resolved:
            self._set_inactive("county_unresolved")
            return

        county_code, county_name = resolved
        self._apply_hysteresis(county_code, county_name)
        effective = self._effective_gps_county()
        if effective:
            self._gps_active = True
            if (
                self._candidate_county
                and self._active_gps_county
                and self._candidate_county != self._active_gps_county
            ):
                self._inactive_reason = "hysteresis_pending"
            else:
                self._inactive_reason = None
        else:
            self._gps_active = False
            self._inactive_reason = "hysteresis_pending"

    def _apply_hysteresis(self, county_code: str, county_name: str) -> None:
        threshold = max(1, int(self.config.gpsd.hysteresis_polls))

        # First acquisition: lock immediately (hysteresis is for county switches while moving)
        if self._active_gps_county is None:
            self._active_gps_county = county_code
            self._active_gps_county_name = county_name
            self._candidate_county = county_code
            self._candidate_polls = threshold
            logger.info("GPS county acquired: %s (%s)", county_code, county_name)
            return

        if county_code == self._active_gps_county:
            self._candidate_county = county_code
            self._candidate_polls = threshold
            self._active_gps_county_name = county_name
            return

        if county_code == self._candidate_county:
            self._candidate_polls += 1
        else:
            self._candidate_county = county_code
            self._candidate_polls = 1

        if self._candidate_polls >= threshold:
            if self._active_gps_county != county_code:
                logger.info(
                    "GPS county changed: %s -> %s (%s)",
                    self._active_gps_county,
                    county_code,
                    county_name,
                )
            self._active_gps_county = county_code
            self._active_gps_county_name = county_name

    def _set_inactive(self, reason: str) -> None:
        if self._gps_active:
            logger.info(
                "GPS mobile county inactive (%s) for node %s",
                reason,
                self.get_gps_controlled_node(),
            )
        self._gps_active = False
        self._inactive_reason = reason
        self._active_gps_county = None
        self._active_gps_county_name = None
        self._candidate_county = None
        self._candidate_polls = 0

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
        """County codes to poll from NWS this cycle."""
        fetch: Set[str] = set()
        enabled = self._enabled_county_codes()

        for node_number in self.config.asterisk.get_nodes_list():
            if self._node_is_gps_controlled(node_number) and self.is_gps_active():
                effective = self._effective_gps_county()
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
            effective = self._effective_gps_county()
            if effective:
                return {effective}
        return self._static_counties_for_node(node_number)

    def get_nodes_for_counties(self, alert_county_codes: List[str]) -> List[int]:
        """Determine target nodes for an alert, honoring GPS overrides."""
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
                effective = self._effective_gps_county()
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
        """All county codes currently in use for alert filtering."""
        monitored = self._enabled_county_codes()
        effective = self._effective_gps_county()
        if self.is_gps_active() and effective:
            monitored.add(effective)
        return monitored

    def get_status(self) -> Dict[str, Any]:
        """GPS state for dashboard and API consumers."""
        node = self.get_gps_controlled_node()
        status: Dict[str, Any] = {
            "enabled": self.config.gpsd.enabled,
            "poll_counties": self.get_fetch_counties(),
            "controlled_node": node,
            "active": self.is_gps_active(),
            "reason": self._inactive_reason,
            "county_code": self._effective_gps_county(),
            "county_name": self._active_gps_county_name,
            "candidate_county": self._candidate_county,
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
        if node is not None:
            effective = self.get_effective_counties_for_node(node)
            status["gps_only"] = self._is_gps_only_node(node)
            status["effective_counties"] = sorted(effective) if effective is not None else None
        return status
