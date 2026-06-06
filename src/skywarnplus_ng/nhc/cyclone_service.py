"""NHC tropical cyclone polling and announcement selection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import httpx

from .parser import (
    ParsedCyclone,
    build_cyclone_tts_text,
    filter_active_cyclones,
    haversine_miles,
    is_cyclone_current,
    is_hurricane,
    parse_coordinates,
    parse_nhc_cyclone_xml,
)

if TYPE_CHECKING:
    from ..core.config import AppConfig, NhcConfig
    from ..location.mobile_counties import MobileCountyService

logger = logging.getLogger(__name__)

NHC_BASE_URL = "https://www.nhc.noaa.gov"


@dataclass(frozen=True)
class CycloneAdvisory:
    """A cyclone advisory selected for announcement."""

    atcf: str
    name: str
    storm_type: str
    advisory_key: str
    distance_miles: int
    tts_text: str
    headline: str
    center: str
    wind: str
    movement: str


class NhcCycloneService:
    """Fetch and filter NHC cyclone advisories."""

    def __init__(
        self,
        config: AppConfig,
        mobile_service: Optional[MobileCountyService] = None,
    ) -> None:
        self.config = config
        self.mobile_service = mobile_service
        self._client = httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": config.nws.user_agent},
            follow_redirects=True,
        )
        self._last_poll_at: Optional[datetime] = None
        self._tracked_storms: List[Dict[str, Any]] = []

    async def close(self) -> None:
        await self._client.aclose()

    def should_poll(self, now: Optional[datetime] = None) -> bool:
        if not self.config.nhc.enabled:
            return False
        now = now or datetime.now(timezone.utc)
        if self._last_poll_at is None:
            return True
        elapsed = (now - self._last_poll_at).total_seconds() / 60.0
        return elapsed >= self.config.nhc.poll_interval_minutes

    def get_position(self) -> Optional[Tuple[float, float]]:
        nhc = self.config.nhc
        if nhc.use_gps_position and self.mobile_service:
            pos = self.mobile_service.get_position()
            if pos:
                return pos
        if nhc.static_lat is not None and nhc.static_lon is not None:
            return float(nhc.static_lat), float(nhc.static_lon)
        return None

    async def fetch_feed_xml(self) -> Optional[str]:
        path = self.config.nhc.feed_path.lstrip("/")
        url = f"{NHC_BASE_URL}/{path}"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            logger.warning("NHC feed fetch failed: %s", exc)
            return None

    def _already_announced(self, advisory_key: str, state: Dict[str, Any]) -> bool:
        announced = state.get("nhc_announced_advisories") or []
        if not isinstance(announced, list):
            return False
        return advisory_key in announced

    def mark_announced(self, advisory_key: str, state: Dict[str, Any]) -> None:
        announced = state.get("nhc_announced_advisories")
        if not isinstance(announced, list):
            announced = []
        if advisory_key not in announced:
            announced.append(advisory_key)
        # Keep list bounded
        state["nhc_announced_advisories"] = announced[-200:]

    def select_new_advisories(
        self,
        cyclones: List[ParsedCyclone],
        state: Dict[str, Any],
        position: Tuple[float, float],
    ) -> List[CycloneAdvisory]:
        nhc: NhcConfig = self.config.nhc
        lat, lon = position
        selected: List[CycloneAdvisory] = []
        tracked: List[Dict[str, Any]] = []

        for cyclone in filter_active_cyclones(cyclones):
            if not is_cyclone_current(cyclone, nhc.max_advisory_age_hours):
                continue
            if nhc.hurricanes_only and not is_hurricane(cyclone.type):
                continue
            coords = parse_coordinates(cyclone.center)
            if not coords:
                continue
            distance = haversine_miles(lat, lon, coords[0], coords[1])
            tracked.append(
                {
                    "name": cyclone.name,
                    "type": cyclone.type,
                    "atcf": cyclone.atcf,
                    "distance_miles": distance,
                    "advisory_key": cyclone.advisory_key,
                }
            )
            if distance > nhc.max_distance_miles:
                continue
            if self._already_announced(cyclone.advisory_key, state):
                continue

            selected.append(
                CycloneAdvisory(
                    atcf=cyclone.atcf,
                    name=cyclone.name,
                    storm_type=cyclone.type,
                    advisory_key=cyclone.advisory_key,
                    distance_miles=distance,
                    tts_text=build_cyclone_tts_text(cyclone),
                    headline=cyclone.headline,
                    center=cyclone.center,
                    wind=cyclone.wind,
                    movement=cyclone.movement,
                )
            )

        self._tracked_storms = tracked
        return selected

    async def poll(self, state: Dict[str, Any]) -> List[CycloneAdvisory]:
        self._last_poll_at = datetime.now(timezone.utc)
        if not self.config.nhc.enabled:
            self._tracked_storms = []
            return []

        position = self.get_position()
        if position is None:
            logger.warning("NHC enabled but no position available (GPS or static lat/lon)")
            return []

        xml_text = await self.fetch_feed_xml()
        if not xml_text:
            return []

        if "no tropical cyclones" in xml_text.lower():
            self._tracked_storms = []
            logger.debug("NHC feed reports no active tropical cyclones")
            return []

        cyclones = parse_nhc_cyclone_xml(xml_text)
        advisories = self.select_new_advisories(cyclones, state, position)
        if advisories:
            logger.info(
                "NHC: %s new advisory(ies) within %s miles",
                len(advisories),
                self.config.nhc.max_distance_miles,
            )
        return advisories

    def get_status(self, state: Dict[str, Any]) -> Dict[str, Any]:
        position = self.get_position()
        return {
            "enabled": self.config.nhc.enabled,
            "feed_path": self.config.nhc.feed_path,
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "position": (
                {"lat": position[0], "lon": position[1]} if position else None
            ),
            "tracked_storms": self._tracked_storms,
            "announced_count": len(state.get("nhc_announced_advisories") or []),
        }
