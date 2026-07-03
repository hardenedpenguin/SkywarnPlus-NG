"""USGS earthquake polling and voice announcement selection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx

from ..geo_hazard.fetch_cache import GeoFetchCache
from ..geo_hazard.position_health import (
    append_gps_health_details,
    missing_position_message,
    position_source_label,
)
from ..geo_hazard.tts import sanitize_for_tts
from ..location.position import get_monitoring_position
from .parser import ParsedEarthquake, parse_earthquake_collection

if TYPE_CHECKING:
    from ..core.config import AppConfig, EarthquakeConfig
    from ..location.mobile_counties import MobileCountyService

logger = logging.getLogger(__name__)

USGS_EVENT_API = "https://earthquake.usgs.gov/fdsnws/event/1/query"
DISPLAY_REFRESH_MINUTES = 5


@dataclass(frozen=True)
class EarthquakeEvent:
    """Earthquake selected for announcement."""

    event_id: str
    magnitude: float
    place: str
    distance_miles: int
    announcement_key: str
    tts_text: str
    time_utc: datetime


class UsgsEarthquakeService:
    """Fetch and filter USGS earthquakes near the monitoring position."""

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
        self._tracked_events: List[Dict[str, Any]] = []
        self._last_fetch_ok_at: Optional[datetime] = None
        self._last_error_message: Optional[str] = None
        self._last_display_refresh_at: Optional[datetime] = None
        self._fetch_cache = GeoFetchCache.shared()

    def sync_http_client_user_agent(self) -> None:
        self._client.headers["User-Agent"] = self.config.nws.user_agent

    def _cache_key(self, position: Tuple[float, float]) -> str:
        eq = self.config.earthquake
        lat, lon = position
        max_km = round(eq.max_distance_miles * 1.60934, 1)
        return f"usgs:{lat:.4f}:{lon:.4f}:{eq.lookback_hours}:{eq.min_magnitude}:{max_km}"

    async def close(self) -> None:
        await self._client.aclose()

    def should_poll(self, now: Optional[datetime] = None) -> bool:
        if not self.config.earthquake.enabled:
            return False
        now = now or datetime.now(timezone.utc)
        if self._last_poll_at is None:
            return True
        elapsed = (now - self._last_poll_at).total_seconds() / 60.0
        return elapsed >= self.config.earthquake.poll_interval_minutes

    def get_position(self) -> Optional[Tuple[float, float]]:
        pos = self.config.geo_hazard_position
        return get_monitoring_position(
            use_gps_position=pos.use_gps_position,
            static_lat=pos.static_lat,
            static_lon=pos.static_lon,
            mobile_service=self.mobile_service,
        )

    def _build_query_url(self, position: Tuple[float, float]) -> str:
        eq: EarthquakeConfig = self.config.earthquake
        lat, lon = position
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=eq.lookback_hours)
        max_km = round(eq.max_distance_miles * 1.60934, 1)
        params = {
            "format": "geojson",
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "maxradiuskm": str(max_km),
            "minmagnitude": str(eq.min_magnitude),
            "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "orderby": "time",
            "limit": "100",
        }
        return f"{USGS_EVENT_API}?{urlencode(params)}"

    async def fetch_events_geojson(self, position: Tuple[float, float]) -> Optional[dict[str, Any]]:
        cache_key = self._cache_key(position)

        async def _fetch() -> Optional[dict[str, Any]]:
            return await self._fetch_events_geojson_uncached(position)

        return await self._fetch_cache.get_or_fetch(cache_key, _fetch)

    async def _fetch_events_geojson_uncached(
        self, position: Tuple[float, float]
    ) -> Optional[dict[str, Any]]:
        url = self._build_query_url(position)
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            data = response.json()
            self._last_error_message = None
            if isinstance(data, dict):
                return data
            return None
        except httpx.HTTPError as exc:
            logger.warning("USGS earthquake fetch failed: %s", exc)
            self._last_error_message = f"USGS earthquake fetch failed: {exc}"
            return None
        except ValueError as exc:
            logger.warning("USGS earthquake response invalid: %s", exc)
            self._last_error_message = f"USGS earthquake response invalid: {exc}"
            return None

    def _record_poll_error(self, state: Dict[str, Any], message: str) -> None:
        now = datetime.now(timezone.utc)
        self._last_error_message = message
        state["usgs_last_error_at"] = now.isoformat()
        state["usgs_last_error_message"] = message

    def _record_poll_success(self, state: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        self._last_fetch_ok_at = now
        self._last_error_message = None
        state["usgs_last_error_at"] = None
        state["usgs_last_error_message"] = None

    def _event_within_age(self, event: ParsedEarthquake, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        max_age = timedelta(hours=self.config.earthquake.max_event_age_hours)
        return (now - event.time_utc) <= max_age

    def _passes_filters(self, event: ParsedEarthquake) -> bool:
        eq = self.config.earthquake
        if event.magnitude < eq.min_magnitude:
            return False
        if event.distance_miles > eq.max_distance_miles:
            return False
        if not self._event_within_age(event):
            return False
        threshold = eq.ignore_automatic_below
        if threshold is not None and event.status == "automatic" and event.magnitude < threshold:
            return False
        return True

    def _already_announced(self, announcement_key: str, state: Dict[str, Any]) -> bool:
        announced = state.get("usgs_announced_events") or []
        if not isinstance(announced, list):
            return False
        return announcement_key in announced

    def mark_announced(self, announcement_key: str, state: Dict[str, Any]) -> None:
        announced = state.get("usgs_announced_events")
        if not isinstance(announced, list):
            announced = []
        if announcement_key not in announced:
            announced.append(announcement_key)
        state["usgs_announced_events"] = announced[-500:]

    def _maybe_seed_announced_history(
        self,
        events: List[ParsedEarthquake],
        state: Dict[str, Any],
    ) -> None:
        if state.get("usgs_history_seeded"):
            return
        eq = self.config.earthquake
        seeded = 0
        if not eq.announce_history_on_enable:
            for event in events:
                if self._passes_filters(event):
                    self.mark_announced(event.announcement_key, state)
                    seeded += 1
            if seeded:
                logger.info(
                    "USGS: seeded %s existing earthquake(s) as announced "
                    "(announce_history_on_enable=false)",
                    seeded,
                )
        state["usgs_history_seeded"] = True

    def select_new_events(
        self,
        events: List[ParsedEarthquake],
        state: Dict[str, Any],
    ) -> List[EarthquakeEvent]:
        selected: List[EarthquakeEvent] = []
        tracked: List[Dict[str, Any]] = []

        for event in sorted(events, key=lambda e: e.time_utc, reverse=True):
            within_filters = self._passes_filters(event)
            announced = self._already_announced(event.announcement_key, state)
            tracked.append(
                {
                    "event_id": event.event_id,
                    "magnitude": event.magnitude,
                    "place": event.place,
                    "distance_miles": event.distance_miles,
                    "time_utc": event.time_utc.isoformat(),
                    "status": event.status,
                    "within_range": within_filters,
                    "announced": announced,
                }
            )
            if not within_filters or announced:
                continue
            selected.append(
                EarthquakeEvent(
                    event_id=event.event_id,
                    magnitude=event.magnitude,
                    place=sanitize_for_tts(event.place),
                    distance_miles=event.distance_miles,
                    announcement_key=event.announcement_key,
                    tts_text=event.tts_text,
                    time_utc=event.time_utc,
                )
            )

        self._tracked_events = tracked
        return selected

    async def check_health(self, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = state or {}
        details: Dict[str, Any] = {
            "min_magnitude": self.config.earthquake.min_magnitude,
            "max_distance_miles": self.config.earthquake.max_distance_miles,
            "max_event_age_hours": self.config.earthquake.max_event_age_hours,
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "tracked_events": len(self._tracked_events),
        }

        pos = self.config.geo_hazard_position
        position = self.get_position()
        if position:
            details["position"] = {"lat": position[0], "lon": position[1]}
            details["position_source"] = position_source_label(
                use_gps_position=pos.use_gps_position,
                static_lat=pos.static_lat,
                static_lon=pos.static_lon,
                mobile_service=self.mobile_service,
                gpsd_enabled=self.config.gpsd.enabled,
            )
            append_gps_health_details(
                details,
                use_gps_position=pos.use_gps_position,
                gpsd_enabled=self.config.gpsd.enabled,
                mobile_service=self.mobile_service,
                position=position,
            )
        else:
            details["position"] = None
            details["position_source"] = "none"
            append_gps_health_details(
                details,
                use_gps_position=pos.use_gps_position,
                gpsd_enabled=self.config.gpsd.enabled,
                mobile_service=self.mobile_service,
                position=None,
            )
            return {
                "ok": False,
                "message": missing_position_message(
                    use_gps_position=pos.use_gps_position,
                    gpsd_enabled=self.config.gpsd.enabled,
                    mobile_service=self.mobile_service,
                ),
                "details": details,
            }

        data = await self.fetch_events_geojson(position)
        if not data:
            msg = self._last_error_message or "USGS earthquake fetch failed"
            if state.get("usgs_last_error_message"):
                msg = str(state["usgs_last_error_message"])
            return {"ok": False, "message": msg, "details": details}

        events = parse_earthquake_collection(data, origin_lat=position[0], origin_lon=position[1])
        details["events_in_feed"] = len(events)
        return {
            "ok": True,
            "message": f"USGS feed OK ({len(events)} event(s) in lookback window)",
            "details": details,
        }

    async def refresh_tracked_events_if_stale(self, state: Dict[str, Any]) -> None:
        if not self.config.earthquake.enabled:
            self._tracked_events = []
            return

        now = datetime.now(timezone.utc)
        if self._last_display_refresh_at is not None:
            elapsed_min = (now - self._last_display_refresh_at).total_seconds() / 60.0
            if elapsed_min < DISPLAY_REFRESH_MINUTES:
                return

        position = self.get_position()
        if position is None:
            return

        data = await self.fetch_events_geojson(position)
        self._last_display_refresh_at = datetime.now(timezone.utc)
        if not data:
            return

        events = parse_earthquake_collection(data, origin_lat=position[0], origin_lon=position[1])
        self.select_new_events(events, state)

    async def poll(self, state: Dict[str, Any]) -> List[EarthquakeEvent]:
        if not self.config.earthquake.enabled:
            self._tracked_events = []
            return []

        position = self.get_position()
        if position is None:
            msg = "No position available (GPS or static lat/lon)"
            logger.warning("USGS earthquakes enabled but %s", msg)
            self._record_poll_error(state, msg)
            return []

        data = await self.fetch_events_geojson(position)
        if not data:
            self._record_poll_error(
                state,
                self._last_error_message or "USGS earthquake fetch failed",
            )
            return []

        events = parse_earthquake_collection(data, origin_lat=position[0], origin_lon=position[1])
        self._maybe_seed_announced_history(events, state)
        selected = self.select_new_events(events, state)
        self._last_poll_at = datetime.now(timezone.utc)
        self._last_display_refresh_at = self._last_poll_at
        self._record_poll_success(state)
        eq = self.config.earthquake
        if eq.announce_enabled:
            cap = eq.max_announcements_per_cycle
            if len(selected) > cap:
                logger.info(
                    "USGS: deferring %s earthquake(s) to later poll cycles (cap=%s)",
                    len(selected) - cap,
                    cap,
                )
                selected = selected[:cap]
        if selected:
            logger.info(
                "USGS: %s new earthquake(s) within %s miles (M>=%s)",
                len(selected),
                self.config.earthquake.max_distance_miles,
                self.config.earthquake.min_magnitude,
            )
        return selected

    def get_status(self, state: Dict[str, Any]) -> Dict[str, Any]:
        position = self.get_position()
        eq = self.config.earthquake
        return {
            "enabled": eq.enabled,
            "announce_enabled": eq.announce_enabled,
            "poll_interval_minutes": eq.poll_interval_minutes,
            "min_magnitude": eq.min_magnitude,
            "max_distance_miles": eq.max_distance_miles,
            "lookback_hours": eq.lookback_hours,
            "max_event_age_hours": eq.max_event_age_hours,
            "max_announcements_per_cycle": eq.max_announcements_per_cycle,
            "announce_history_on_enable": eq.announce_history_on_enable,
            "history_seeded": bool(state.get("usgs_history_seeded")),
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "position": ({"lat": position[0], "lon": position[1]} if position else None),
            "tracked_events": self._tracked_events,
            "announced_count": len(state.get("usgs_announced_events") or []),
            "last_error_message": self._last_error_message,
            "last_fetch_ok_at": (
                self._last_fetch_ok_at.isoformat() if self._last_fetch_ok_at else None
            ),
        }
