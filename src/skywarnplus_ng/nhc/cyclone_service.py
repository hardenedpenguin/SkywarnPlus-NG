"""NHC tropical cyclone polling and announcement selection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import httpx

from ..geo_hazard.fetch_cache import GeoFetchCache
from ..geo_hazard.position_health import position_source_label
from ..location.position import get_monitoring_position
from .parser import (
    ParsedCyclone,
    build_cyclone_tts_text,
    filter_active_cyclones,
    haversine_miles,
    is_cyclone_current,
    is_hurricane,
    normalize_cyclone_movement,
    parse_coordinates,
    parse_nhc_cyclone_xml,
)

if TYPE_CHECKING:
    from ..core.config import AppConfig, NhcConfig
    from ..location.mobile_counties import MobileCountyService

logger = logging.getLogger(__name__)

NHC_BASE_URL = "https://www.nhc.noaa.gov"
NHC_BASIN_FEEDS = ("/gis-at.xml", "/gis-ep.xml", "/gis-cp.xml")
# Throttle dashboard/status refreshes separately from voice-announcement polls
DISPLAY_REFRESH_MINUTES = 5


def resolve_nhc_feed_paths(feed_path: str) -> List[str]:
    """Resolve configured feed path into one or more NHC GIS RSS paths."""
    raw = (feed_path or "").strip()
    if not raw:
        return ["/gis-at.xml"]
    lowered = raw.lower()
    if lowered in {"all", "*", "/gis-all", "/gis-all.xml", "gis-all.xml"}:
        return list(NHC_BASIN_FEEDS)
    if "," in raw:
        paths: List[str] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            if not part.startswith("/"):
                part = f"/{part}"
            paths.append(part)
        return paths or ["/gis-at.xml"]
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return [raw]


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
        self._last_fetch_ok_at: Optional[datetime] = None
        self._last_error_message: Optional[str] = None
        self._last_display_refresh_at: Optional[datetime] = None
        self._fetch_cache = GeoFetchCache.shared()

    def sync_http_client_user_agent(self) -> None:
        self._client.headers["User-Agent"] = self.config.nws.user_agent

    def _feed_cache_key(self, path: str) -> str:
        return f"nhc:{path.lstrip('/')}"

    def feed_paths(self) -> List[str]:
        return resolve_nhc_feed_paths(self.config.nhc.feed_path)

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
        pos = self.config.geo_hazard_position
        return get_monitoring_position(
            use_gps_position=pos.use_gps_position,
            static_lat=pos.static_lat,
            static_lon=pos.static_lon,
            mobile_service=self.mobile_service,
        )

    async def fetch_feed_xml(self, path: Optional[str] = None) -> Optional[str]:
        feed_path = path or self.feed_paths()[0]
        cache_key = self._feed_cache_key(feed_path)

        async def _fetch() -> Optional[str]:
            return await self._fetch_feed_xml_uncached(feed_path)

        return await self._fetch_cache.get_or_fetch(cache_key, _fetch)

    async def _fetch_feed_xml_uncached(self, path: str) -> Optional[str]:
        url = f"{NHC_BASE_URL}/{path.lstrip('/')}"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            self._last_error_message = None
            return response.text
        except httpx.HTTPError as exc:
            logger.warning("NHC feed fetch failed (%s): %s", path, exc)
            self._last_error_message = f"NHC feed fetch failed ({path}): {exc}"
            return None

    async def fetch_cyclones(self) -> Optional[List[ParsedCyclone]]:
        """
        Fetch and parse configured NHC basin feed(s).

        Returns ``None`` when every configured feed fails. Returns an empty
        list when feeds are reachable but report no active cyclones.
        """
        storms: List[ParsedCyclone] = []
        any_success = False
        last_error: Optional[str] = None

        for path in self.feed_paths():
            xml_text = await self.fetch_feed_xml(path)
            if xml_text is None:
                last_error = self._last_error_message
                continue
            any_success = True
            if "no tropical cyclones" in xml_text.lower():
                continue
            storms.extend(parse_nhc_cyclone_xml(xml_text))

        if not any_success:
            if last_error:
                self._last_error_message = last_error
            return None

        self._last_error_message = None
        # Deduplicate by ATCF + advisory datetime if feeds overlap.
        seen: set[str] = set()
        unique: List[ParsedCyclone] = []
        for cyclone in storms:
            key = cyclone.advisory_key
            if key in seen:
                continue
            seen.add(key)
            unique.append(cyclone)
        return unique

    def _position_source(self) -> str:
        pos = self.config.geo_hazard_position
        return position_source_label(
            use_gps_position=pos.use_gps_position,
            static_lat=pos.static_lat,
            static_lon=pos.static_lon,
            mobile_service=self.mobile_service,
            gpsd_enabled=self.config.gpsd.enabled,
        )

    def _record_poll_error(self, state: Dict[str, Any], message: str) -> None:
        now = datetime.now(timezone.utc)
        self._last_error_message = message
        state["nhc_last_error_at"] = now.isoformat()
        state["nhc_last_error_message"] = message

    def _record_poll_success(self, state: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        self._last_fetch_ok_at = now
        self._last_error_message = None
        state["nhc_last_error_at"] = None
        state["nhc_last_error_message"] = None

    async def check_health(self, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Live health probe for dashboard (feed reachability + position when GPS-backed).
        """
        state = state or {}
        details: Dict[str, Any] = {
            "feed_path": self.config.nhc.feed_path,
            "feed_paths": self.feed_paths(),
            "use_gps_position": self.config.geo_hazard_position.use_gps_position,
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "last_fetch_ok_at": (
                self._last_fetch_ok_at.isoformat() if self._last_fetch_ok_at else None
            ),
            "tracked_storms": len(self._tracked_storms),
        }

        position = self.get_position()
        if position:
            details["position"] = {"lat": position[0], "lon": position[1]}
            details["position_source"] = self._position_source()
        else:
            details["position"] = None
            details["position_source"] = "none"

        if (
            self.config.geo_hazard_position.use_gps_position
            and self.config.gpsd.enabled
            and self.mobile_service
        ):
            gps = self.mobile_service.get_status()
            details["gps_active"] = gps.get("active")
            details["gps_reason"] = gps.get("reason")
            details["gps_county"] = gps.get("county_code")
            if not position:
                return {
                    "ok": False,
                    "message": f"No GPS position for NHC ({gps.get('reason') or 'no fix'})",
                    "details": details,
                }

        if not position:
            return {
                "ok": False,
                "message": "No position available (enable gpsd or set static lat/lon)",
                "details": details,
            }

        cyclones = await self.fetch_cyclones()
        if cyclones is None:
            msg = self._last_error_message or "NHC feed fetch failed"
            if state.get("nhc_last_error_message"):
                msg = str(state["nhc_last_error_message"])
            return {"ok": False, "message": msg, "details": details}

        details["feed_reachable"] = True
        active = filter_active_cyclones(cyclones)
        details["active_storms"] = len(active)
        if not active:
            message = "NHC feed OK (no active tropical cyclones)"
        else:
            message = f"NHC feed OK ({len(active)} active storm(s) in feed)"

        return {"ok": True, "message": message, "details": details}

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
            coords = parse_coordinates(cyclone.center)
            if not coords:
                continue
            distance = haversine_miles(lat, lon, coords[0], coords[1])
            within_range = distance <= nhc.max_distance_miles
            announced = self._already_announced(cyclone.advisory_key, state)
            current = is_cyclone_current(cyclone, nhc.max_advisory_age_hours)
            movement = normalize_cyclone_movement(cyclone.movement, cyclone.headline)
            tracked.append(
                {
                    "name": cyclone.name,
                    "type": cyclone.type,
                    "atcf": cyclone.atcf,
                    "distance_miles": distance,
                    "advisory_key": cyclone.advisory_key,
                    "wind": cyclone.wind,
                    "movement": movement,
                    "pressure": cyclone.pressure,
                    "headline": cyclone.headline,
                    "datetime": cyclone.datetime_raw,
                    "center": cyclone.center,
                    "within_range": within_range,
                    "announced": announced,
                    "advisory_current": current,
                }
            )
            # Age / hurricane filters apply to voice only — keep dashboard complete.
            if not current:
                continue
            if nhc.hurricanes_only and not is_hurricane(cyclone.type):
                continue
            if not within_range:
                continue
            if announced:
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
                    movement=movement,
                )
            )

        tracked.sort(key=lambda item: item.get("distance_miles") or 0)
        self._tracked_storms = tracked
        return selected

    async def refresh_tracked_storms_if_stale(self, state: Dict[str, Any]) -> None:
        """Refresh in-memory storm list for dashboard (throttled; does not affect poll cadence)."""
        if not self.config.nhc.enabled:
            self._tracked_storms = []
            return

        now = datetime.now(timezone.utc)
        if self._last_display_refresh_at is not None:
            elapsed_min = (now - self._last_display_refresh_at).total_seconds() / 60.0
            if elapsed_min < DISPLAY_REFRESH_MINUTES:
                return

        position = self.get_position()
        if position is None:
            return

        cyclones = await self.fetch_cyclones()
        self._last_display_refresh_at = datetime.now(timezone.utc)
        if cyclones is None:
            return

        self.select_new_advisories(cyclones, state, position)

    async def poll(self, state: Dict[str, Any]) -> List[CycloneAdvisory]:
        if not self.config.nhc.enabled:
            self._tracked_storms = []
            return []

        position = self.get_position()
        if position is None:
            msg = "No position available (GPS or static lat/lon)"
            logger.warning("NHC enabled but %s", msg)
            self._record_poll_error(state, msg)
            return []

        cyclones = await self.fetch_cyclones()
        if cyclones is None:
            self._record_poll_error(
                state,
                self._last_error_message or "NHC feed fetch failed",
            )
            return []

        advisories = self.select_new_advisories(cyclones, state, position)
        self._last_poll_at = datetime.now(timezone.utc)
        self._last_display_refresh_at = self._last_poll_at
        self._record_poll_success(state)
        if not cyclones:
            logger.debug("NHC feed reports no active tropical cyclones")
            return []
        cap = self.config.nhc.max_announcements_per_cycle
        if len(advisories) > cap:
            logger.info(
                "NHC: deferring %s advisory(ies) to later poll cycles (cap=%s)",
                len(advisories) - cap,
                cap,
            )
            advisories = advisories[:cap]
        if advisories:
            logger.info(
                "NHC: %s new advisory(ies) within %s miles",
                len(advisories),
                self.config.nhc.max_distance_miles,
            )
        return advisories

    def get_status(self, state: Dict[str, Any]) -> Dict[str, Any]:
        position = self.get_position()
        nhc = self.config.nhc
        return {
            "enabled": nhc.enabled,
            "feed_path": nhc.feed_path,
            "feed_paths": self.feed_paths(),
            "poll_interval_minutes": nhc.poll_interval_minutes,
            "max_distance_miles": nhc.max_distance_miles,
            "max_announcements_per_cycle": nhc.max_announcements_per_cycle,
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "position": ({"lat": position[0], "lon": position[1]} if position else None),
            "tracked_storms": self._tracked_storms,
            "announced_count": len(state.get("nhc_announced_advisories") or []),
            "last_error_message": self._last_error_message,
            "last_fetch_ok_at": (
                self._last_fetch_ok_at.isoformat() if self._last_fetch_ok_at else None
            ),
        }
