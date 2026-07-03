"""USGS volcano notice polling and voice announcement selection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import httpx

from ..geo_hazard.fetch_cache import GeoFetchCache
from ..geo_hazard.position_health import (
    append_gps_health_details,
    missing_position_message,
    position_source_label,
)
from ..location.position import get_monitoring_position
from .parser import ParsedVolcano, color_rank, parse_volcano_notices

if TYPE_CHECKING:
    from ..core.config import AppConfig
    from ..location.mobile_counties import MobileCountyService

logger = logging.getLogger(__name__)

USGS_VONA_API = "https://volcanoes.usgs.gov/vsc/api/hansApi/vonas"
DISPLAY_REFRESH_MINUTES = 5


@dataclass(frozen=True)
class VolcanoNotice:
    """Volcano notice selected for announcement."""

    vnum: str
    name: str
    color_code: str
    distance_miles: Optional[int]
    announcement_key: str
    tts_text: str
    issued_utc: Optional[datetime]


class VolcanoService:
    """Fetch and filter USGS volcano notices near the monitoring position."""

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
        self._tracked_notices: List[Dict[str, Any]] = []
        self._last_fetch_ok_at: Optional[datetime] = None
        self._last_error_message: Optional[str] = None
        self._last_display_refresh_at: Optional[datetime] = None
        self._fetch_cache = GeoFetchCache.shared()

    def sync_http_client_user_agent(self) -> None:
        self._client.headers["User-Agent"] = self.config.nws.user_agent

    async def close(self) -> None:
        await self._client.aclose()

    def should_poll(self, now: Optional[datetime] = None) -> bool:
        if not self.config.volcano.enabled:
            return False
        now = now or datetime.now(timezone.utc)
        if self._last_poll_at is None:
            return True
        elapsed = (now - self._last_poll_at).total_seconds() / 60.0
        return elapsed >= self.config.volcano.poll_interval_minutes

    def get_position(self) -> Optional[Tuple[float, float]]:
        pos = self.config.geo_hazard_position
        return get_monitoring_position(
            use_gps_position=pos.use_gps_position,
            static_lat=pos.static_lat,
            static_lon=pos.static_lon,
            mobile_service=self.mobile_service,
        )

    def _cache_key(self) -> str:
        return f"usgs:vonas:{self.config.volcano.lookback_days}"

    async def fetch_notices(self) -> Optional[List[Dict[str, Any]]]:
        cache_key = self._cache_key()

        async def _fetch() -> Optional[List[Dict[str, Any]]]:
            return await self._fetch_notices_uncached()

        return await self._fetch_cache.get_or_fetch(cache_key, _fetch)

    async def _fetch_notices_uncached(self) -> Optional[List[Dict[str, Any]]]:
        days = self.config.volcano.lookback_days
        url = f"{USGS_VONA_API}/{days}"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            data = response.json()
            self._last_error_message = None
            if isinstance(data, list):
                return data
            return None
        except httpx.HTTPError as exc:
            logger.warning("USGS volcano fetch failed: %s", exc)
            self._last_error_message = f"USGS volcano fetch failed: {exc}"
            return None
        except ValueError as exc:
            logger.warning("USGS volcano response invalid: %s", exc)
            self._last_error_message = f"USGS volcano response invalid: {exc}"
            return None

    def _record_poll_error(self, state: Dict[str, Any], message: str) -> None:
        now = datetime.now(timezone.utc)
        self._last_error_message = message
        state["volcano_last_error_at"] = now.isoformat()
        state["volcano_last_error_message"] = message

    def _record_poll_success(self, state: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        self._last_fetch_ok_at = now
        self._last_error_message = None
        state["volcano_last_error_at"] = None
        state["volcano_last_error_message"] = None

    def _passes_filters(self, notice: ParsedVolcano) -> bool:
        vo = self.config.volcano
        if color_rank(notice.color_code) < color_rank(vo.min_color_code):
            return False
        if vo.observatories:
            obs = (notice.observatory or "").upper()
            allowed = {o.upper() for o in vo.observatories}
            if obs not in allowed:
                return False
        if notice.distance_miles is None:
            return False
        if notice.distance_miles > vo.max_distance_miles:
            return False
        return True

    def _already_announced(self, announcement_key: str, state: Dict[str, Any]) -> bool:
        announced = state.get("volcano_announced_notices") or []
        if not isinstance(announced, list):
            return False
        return announcement_key in announced

    def mark_announced(self, announcement_key: str, state: Dict[str, Any]) -> None:
        announced = state.get("volcano_announced_notices")
        if not isinstance(announced, list):
            announced = []
        if announcement_key not in announced:
            announced.append(announcement_key)
        state["volcano_announced_notices"] = announced[-500:]

    def _maybe_seed_announced_history(
        self,
        notices: List[ParsedVolcano],
        state: Dict[str, Any],
    ) -> None:
        if state.get("volcano_history_seeded"):
            return
        vo = self.config.volcano
        seeded = 0
        if not vo.announce_history_on_enable:
            for notice in notices:
                if self._passes_filters(notice):
                    self.mark_announced(notice.announcement_key, state)
                    seeded += 1
            if seeded:
                logger.info(
                    "Volcano: seeded %s existing notice(s) as announced "
                    "(announce_history_on_enable=false)",
                    seeded,
                )
        state["volcano_history_seeded"] = True

    def select_new_notices(
        self,
        notices: List[ParsedVolcano],
        state: Dict[str, Any],
    ) -> List[VolcanoNotice]:
        selected: List[VolcanoNotice] = []
        tracked: List[Dict[str, Any]] = []

        for notice in notices:
            within_filters = self._passes_filters(notice)
            announced = self._already_announced(notice.announcement_key, state)
            tracked.append(
                {
                    "vnum": notice.vnum,
                    "name": notice.name,
                    "color_code": notice.color_code,
                    "observatory": notice.observatory,
                    "notice_type": notice.notice_type,
                    "distance_miles": notice.distance_miles,
                    "issued_utc": notice.issued_utc.isoformat() if notice.issued_utc else None,
                    "within_range": within_filters,
                    "announced": announced,
                }
            )
            if not within_filters or announced:
                continue
            selected.append(
                VolcanoNotice(
                    vnum=notice.vnum,
                    name=notice.name,
                    color_code=notice.color_code,
                    distance_miles=notice.distance_miles,
                    announcement_key=notice.announcement_key,
                    tts_text=notice.tts_text,
                    issued_utc=notice.issued_utc,
                )
            )

        self._tracked_notices = tracked
        return selected

    async def check_health(self, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = state or {}
        vo = self.config.volcano
        details: Dict[str, Any] = {
            "min_color_code": vo.min_color_code,
            "max_distance_miles": vo.max_distance_miles,
            "lookback_days": vo.lookback_days,
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "tracked_notices": len(self._tracked_notices),
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

        data = await self.fetch_notices()
        if data is None:
            msg = self._last_error_message or "USGS volcano fetch failed"
            if state.get("volcano_last_error_message"):
                msg = str(state["volcano_last_error_message"])
            return {"ok": False, "message": msg, "details": details}

        notices = parse_volcano_notices(
            data, origin_lat=position[0], origin_lon=position[1]
        )
        details["notices_in_feed"] = len(notices)
        return {
            "ok": True,
            "message": f"USGS volcano feed OK ({len(notices)} notice(s) in lookback)",
            "details": details,
        }

    async def refresh_tracked_notices_if_stale(self, state: Dict[str, Any]) -> None:
        if not self.config.volcano.enabled:
            self._tracked_notices = []
            return

        now = datetime.now(timezone.utc)
        if self._last_display_refresh_at is not None:
            elapsed_min = (now - self._last_display_refresh_at).total_seconds() / 60.0
            if elapsed_min < DISPLAY_REFRESH_MINUTES:
                return

        position = self.get_position()
        if position is None:
            return

        data = await self.fetch_notices()
        self._last_display_refresh_at = datetime.now(timezone.utc)
        if data is None:
            return

        notices = parse_volcano_notices(
            data, origin_lat=position[0], origin_lon=position[1]
        )
        self.select_new_notices(notices, state)

    async def poll(self, state: Dict[str, Any]) -> List[VolcanoNotice]:
        if not self.config.volcano.enabled:
            self._tracked_notices = []
            return []

        position = self.get_position()
        if position is None:
            msg = "No position available (GPS or static lat/lon)"
            logger.warning("Volcano monitoring enabled but %s", msg)
            self._record_poll_error(state, msg)
            return []

        data = await self.fetch_notices()
        if data is None:
            self._record_poll_error(
                state,
                self._last_error_message or "USGS volcano fetch failed",
            )
            return []

        notices = parse_volcano_notices(
            data, origin_lat=position[0], origin_lon=position[1]
        )
        self._maybe_seed_announced_history(notices, state)
        selected = self.select_new_notices(notices, state)
        self._last_poll_at = datetime.now(timezone.utc)
        self._last_display_refresh_at = self._last_poll_at
        self._record_poll_success(state)

        vo = self.config.volcano
        if vo.announce_enabled:
            cap = vo.max_announcements_per_cycle
            if len(selected) > cap:
                logger.info(
                    "Volcano: deferring %s notice(s) to later poll cycles (cap=%s)",
                    len(selected) - cap,
                    cap,
                )
                selected = selected[:cap]
        if selected:
            logger.info(
                "Volcano: %s new notice(s) within %s miles (color>=%s)",
                len(selected),
                vo.max_distance_miles,
                vo.min_color_code,
            )
        return selected

    def get_status(self, state: Dict[str, Any]) -> Dict[str, Any]:
        position = self.get_position()
        vo = self.config.volcano
        return {
            "enabled": vo.enabled,
            "announce_enabled": vo.announce_enabled,
            "poll_interval_minutes": vo.poll_interval_minutes,
            "max_distance_miles": vo.max_distance_miles,
            "min_color_code": vo.min_color_code,
            "lookback_days": vo.lookback_days,
            "observatories": vo.observatories,
            "max_announcements_per_cycle": vo.max_announcements_per_cycle,
            "announce_history_on_enable": vo.announce_history_on_enable,
            "history_seeded": bool(state.get("volcano_history_seeded")),
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "position": ({"lat": position[0], "lon": position[1]} if position else None),
            "tracked_notices": self._tracked_notices,
            "announced_count": len(state.get("volcano_announced_notices") or []),
            "last_error_message": self._last_error_message,
            "last_fetch_ok_at": (
                self._last_fetch_ok_at.isoformat() if self._last_fetch_ok_at else None
            ),
        }
