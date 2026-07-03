"""NIFC WFIGS wildfire polling and voice announcement selection."""

from __future__ import annotations

import logging
import re
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
from .parser import (
    ParsedWildfire,
    is_prescribed_fire,
    parse_wildfire_collection,
)

if TYPE_CHECKING:
    from ..core.config import AppConfig, WildfireConfig
    from ..location.mobile_counties import MobileCountyService

logger = logging.getLogger(__name__)

WFIGS_FEATURE_SERVER = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query"
)
DISPLAY_REFRESH_MINUTES = 5


@dataclass(frozen=True)
class WildfireIncident:
    """Wildfire incident selected for announcement."""

    incident_id: str
    name: str
    acres: float
    distance_miles: int
    announcement_key: str
    tts_text: str


class WfigsWildfireService:
    """Fetch and filter NIFC wildfire perimeters near the monitoring position."""

    def __init__(
        self,
        config: AppConfig,
        mobile_service: Optional[MobileCountyService] = None,
    ) -> None:
        self.config = config
        self.mobile_service = mobile_service
        self._client = httpx.AsyncClient(
            timeout=45,
            headers={"User-Agent": config.nws.user_agent},
            follow_redirects=True,
        )
        self._last_poll_at: Optional[datetime] = None
        self._tracked_incidents: List[Dict[str, Any]] = []
        self._last_fetch_ok_at: Optional[datetime] = None
        self._last_error_message: Optional[str] = None
        self._last_display_refresh_at: Optional[datetime] = None
        self._fetch_cache = GeoFetchCache.shared()

    def sync_http_client_user_agent(self) -> None:
        self._client.headers["User-Agent"] = self.config.nws.user_agent

    def _cache_key(self, position: Tuple[float, float]) -> str:
        wf = self.config.wildfire
        lat, lon = position
        max_km = round(wf.max_distance_miles * 1.60934, 1)
        return f"wfigs:{lat:.4f}:{lon:.4f}:{max_km}:{wf.min_acres}"

    async def close(self) -> None:
        await self._client.aclose()

    def should_poll(self, now: Optional[datetime] = None) -> bool:
        if not self.config.wildfire.enabled:
            return False
        now = now or datetime.now(timezone.utc)
        if self._last_poll_at is None:
            return True
        elapsed = (now - self._last_poll_at).total_seconds() / 60.0
        return elapsed >= self.config.wildfire.poll_interval_minutes

    def get_position(self) -> Optional[Tuple[float, float]]:
        pos = self.config.geo_hazard_position
        return get_monitoring_position(
            use_gps_position=pos.use_gps_position,
            static_lat=pos.static_lat,
            static_lon=pos.static_lon,
            mobile_service=self.mobile_service,
        )

    def _build_query_url(self, position: Tuple[float, float]) -> str:
        wf: WildfireConfig = self.config.wildfire
        lat, lon = position
        max_km = round(wf.max_distance_miles * 1.60934, 1)
        params = {
            "where": "1=1",
            "outFields": (
                "poly_IncidentName,poly_GISAcres,attr_PercentContained,"
                "attr_FireDiscoveryDateTime,poly_FeatureCategory,poly_IrwinID,"
                "attr_IncidentTypeKind"
            ),
            "geometry": f"{lon:.6f},{lat:.6f}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": str(max_km),
            "units": "esriSRUnit_Kilometer",
            "f": "geojson",
            "returnGeometry": "true",
            "resultRecordCount": "200",
        }
        return f"{WFIGS_FEATURE_SERVER}?{urlencode(params)}"

    async def fetch_incidents_geojson(
        self, position: Tuple[float, float]
    ) -> Optional[dict[str, Any]]:
        cache_key = self._cache_key(position)

        async def _fetch() -> Optional[dict[str, Any]]:
            return await self._fetch_incidents_geojson_uncached(position)

        return await self._fetch_cache.get_or_fetch(cache_key, _fetch)

    async def _fetch_incidents_geojson_uncached(
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
            logger.warning("WFIGS wildfire fetch failed: %s", exc)
            self._last_error_message = f"WFIGS wildfire fetch failed: {exc}"
            return None
        except ValueError as exc:
            logger.warning("WFIGS wildfire response invalid: %s", exc)
            self._last_error_message = f"WFIGS wildfire response invalid: {exc}"
            return None

    def _record_poll_error(self, state: Dict[str, Any], message: str) -> None:
        now = datetime.now(timezone.utc)
        self._last_error_message = message
        state["wildfire_last_error_at"] = now.isoformat()
        state["wildfire_last_error_message"] = message

    def _record_poll_success(self, state: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        self._last_fetch_ok_at = now
        self._last_error_message = None
        state["wildfire_last_error_at"] = None
        state["wildfire_last_error_message"] = None

    def _incident_within_discovery_age(
        self,
        incident: ParsedWildfire,
        now: Optional[datetime] = None,
    ) -> bool:
        if incident.discovery_utc is None:
            return True
        now = now or datetime.now(timezone.utc)
        max_age = timedelta(hours=self.config.wildfire.max_discovery_age_hours)
        return (now - incident.discovery_utc) <= max_age

    def _passes_filters(self, incident: ParsedWildfire) -> bool:
        wf = self.config.wildfire
        if incident.acres < wf.min_acres:
            return False
        if incident.distance_miles > wf.max_distance_miles:
            return False
        if not self._incident_within_discovery_age(incident):
            return False
        if wf.exclude_prescribed and is_prescribed_fire(
            incident_type_kind=incident.incident_type_kind,
            feature_category=incident.feature_category,
        ):
            return False
        return True

    def _already_announced(self, announcement_key: str, state: Dict[str, Any]) -> bool:
        announced = state.get("wildfire_announced_incidents") or []
        if not isinstance(announced, list):
            return False
        return announcement_key in announced

    def mark_announced(self, announcement_key: str, state: Dict[str, Any]) -> None:
        announced = state.get("wildfire_announced_incidents")
        if not isinstance(announced, list):
            announced = []
        if announcement_key not in announced:
            announced.append(announcement_key)
        state["wildfire_announced_incidents"] = announced[-500:]

    def _maybe_seed_announced_history(
        self,
        incidents: List[ParsedWildfire],
        state: Dict[str, Any],
    ) -> None:
        if state.get("wildfire_history_seeded"):
            return
        wf = self.config.wildfire
        seeded = 0
        if not wf.announce_history_on_enable:
            for incident in incidents:
                if self._passes_filters(incident):
                    self.mark_announced(incident.announcement_key, state)
                    seeded += 1
            if seeded:
                logger.info(
                    "WFIGS: seeded %s existing wildfire incident(s) as announced "
                    "(announce_history_on_enable=false)",
                    seeded,
                )
        state["wildfire_history_seeded"] = True

    @staticmethod
    def _safe_audio_prefix(incident_id: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", incident_id).strip("_").lower()
        return f"wildfire_{slug[:40] or 'incident'}"

    def select_new_incidents(
        self,
        incidents: List[ParsedWildfire],
        state: Dict[str, Any],
    ) -> List[WildfireIncident]:
        selected: List[WildfireIncident] = []
        tracked: List[Dict[str, Any]] = []

        for incident in sorted(incidents, key=lambda i: i.acres, reverse=True):
            within_filters = self._passes_filters(incident)
            announced = self._already_announced(incident.announcement_key, state)
            tracked.append(
                {
                    "incident_id": incident.incident_id,
                    "name": incident.name,
                    "acres": incident.acres,
                    "distance_miles": incident.distance_miles,
                    "percent_contained": incident.percent_contained,
                    "within_range": within_filters,
                    "announced": announced,
                }
            )
            if not within_filters or announced:
                continue
            selected.append(
                WildfireIncident(
                    incident_id=incident.incident_id,
                    name=sanitize_for_tts(incident.name),
                    acres=incident.acres,
                    distance_miles=incident.distance_miles,
                    announcement_key=incident.announcement_key,
                    tts_text=incident.tts_text,
                )
            )

        self._tracked_incidents = tracked
        return selected

    async def check_health(self, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = state or {}
        details: Dict[str, Any] = {
            "min_acres": self.config.wildfire.min_acres,
            "max_distance_miles": self.config.wildfire.max_distance_miles,
            "max_discovery_age_hours": self.config.wildfire.max_discovery_age_hours,
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "tracked_incidents": len(self._tracked_incidents),
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

        data = await self.fetch_incidents_geojson(position)
        if not data:
            msg = self._last_error_message or "WFIGS wildfire fetch failed"
            if state.get("wildfire_last_error_message"):
                msg = str(state["wildfire_last_error_message"])
            return {"ok": False, "message": msg, "details": details}

        incidents = parse_wildfire_collection(data, origin_lat=position[0], origin_lon=position[1])
        details["incidents_in_feed"] = len(incidents)
        return {
            "ok": True,
            "message": f"WFIGS feed OK ({len(incidents)} incident(s) in search radius)",
            "details": details,
        }

    async def refresh_tracked_incidents_if_stale(self, state: Dict[str, Any]) -> None:
        if not self.config.wildfire.enabled:
            self._tracked_incidents = []
            return

        now = datetime.now(timezone.utc)
        if self._last_display_refresh_at is not None:
            elapsed_min = (now - self._last_display_refresh_at).total_seconds() / 60.0
            if elapsed_min < DISPLAY_REFRESH_MINUTES:
                return

        position = self.get_position()
        if position is None:
            return

        data = await self.fetch_incidents_geojson(position)
        self._last_display_refresh_at = datetime.now(timezone.utc)
        if not data:
            return

        incidents = parse_wildfire_collection(data, origin_lat=position[0], origin_lon=position[1])
        self.select_new_incidents(incidents, state)

    async def poll(self, state: Dict[str, Any]) -> List[WildfireIncident]:
        if not self.config.wildfire.enabled:
            self._tracked_incidents = []
            return []

        position = self.get_position()
        if position is None:
            msg = "No position available (GPS or static lat/lon)"
            logger.warning("Wildfire monitoring enabled but %s", msg)
            self._record_poll_error(state, msg)
            return []

        data = await self.fetch_incidents_geojson(position)
        if not data:
            self._record_poll_error(
                state,
                self._last_error_message or "WFIGS wildfire fetch failed",
            )
            return []

        incidents = parse_wildfire_collection(data, origin_lat=position[0], origin_lon=position[1])
        self._maybe_seed_announced_history(incidents, state)
        selected = self.select_new_incidents(incidents, state)
        self._last_poll_at = datetime.now(timezone.utc)
        self._last_display_refresh_at = self._last_poll_at
        self._record_poll_success(state)
        wf = self.config.wildfire
        if wf.announce_enabled:
            cap = wf.max_announcements_per_cycle
            if len(selected) > cap:
                logger.info(
                    "WFIGS: deferring %s wildfire incident(s) to later poll cycles (cap=%s)",
                    len(selected) - cap,
                    cap,
                )
                selected = selected[:cap]
        if selected:
            logger.info(
                "WFIGS: %s new wildfire incident(s) within %s miles (>=%s acres)",
                len(selected),
                self.config.wildfire.max_distance_miles,
                self.config.wildfire.min_acres,
            )
        return selected

    def get_status(self, state: Dict[str, Any]) -> Dict[str, Any]:
        position = self.get_position()
        wf = self.config.wildfire
        return {
            "enabled": wf.enabled,
            "announce_enabled": wf.announce_enabled,
            "poll_interval_minutes": wf.poll_interval_minutes,
            "min_acres": wf.min_acres,
            "max_distance_miles": wf.max_distance_miles,
            "exclude_prescribed": wf.exclude_prescribed,
            "max_discovery_age_hours": wf.max_discovery_age_hours,
            "max_announcements_per_cycle": wf.max_announcements_per_cycle,
            "announce_history_on_enable": wf.announce_history_on_enable,
            "history_seeded": bool(state.get("wildfire_history_seeded")),
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "position": ({"lat": position[0], "lon": position[1]} if position else None),
            "tracked_incidents": self._tracked_incidents,
            "announced_count": len(state.get("wildfire_announced_incidents") or []),
            "last_error_message": self._last_error_message,
            "last_fetch_ok_at": (
                self._last_fetch_ok_at.isoformat() if self._last_fetch_ok_at else None
            ),
        }

    def audio_prefix_for(self, incident_id: str) -> str:
        return self._safe_audio_prefix(incident_id)
