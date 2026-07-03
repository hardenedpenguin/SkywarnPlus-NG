"""NOAA SWPC space weather polling and voice announcement selection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import httpx

from ..geo_hazard.fetch_cache import GeoFetchCache
from .parser import ParsedSpaceWeather, parse_swpc_alerts

if TYPE_CHECKING:
    from ..core.config import AppConfig

logger = logging.getLogger(__name__)

SWPC_ALERTS_URL = "https://services.swpc.noaa.gov/products/alerts.json"
DISPLAY_REFRESH_MINUTES = 5
DISPLAY_TRACKED_LIMIT = 5


@dataclass(frozen=True)
class SpaceWeatherAlert:
    """Space weather alert selected for announcement."""

    product_id: str
    title: str
    message_type: str
    geomagnetic_scale: int
    radio_blackout_scale: int
    announcement_key: str
    tts_text: str
    issued_utc: datetime


class SwpcSpaceWeatherService:
    """Fetch and filter NOAA SWPC space weather alerts."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client = httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": config.nws.user_agent},
            follow_redirects=True,
        )
        self._last_poll_at: Optional[datetime] = None
        self._tracked_alerts: List[Dict[str, Any]] = []
        self._last_fetch_ok_at: Optional[datetime] = None
        self._last_error_message: Optional[str] = None
        self._last_display_refresh_at: Optional[datetime] = None
        self._fetch_cache = GeoFetchCache.shared()

    def sync_http_client_user_agent(self) -> None:
        self._client.headers["User-Agent"] = self.config.nws.user_agent

    async def close(self) -> None:
        await self._client.aclose()

    def should_poll(self, now: Optional[datetime] = None) -> bool:
        if not self.config.space_weather.enabled:
            return False
        now = now or datetime.now(timezone.utc)
        if self._last_poll_at is None:
            return True
        elapsed = (now - self._last_poll_at).total_seconds() / 60.0
        return elapsed >= self.config.space_weather.poll_interval_minutes

    def _record_poll_error(self, state: Dict[str, Any], message: str) -> None:
        now = datetime.now(timezone.utc)
        self._last_error_message = message
        state["spaceweather_last_error_at"] = now.isoformat()
        state["spaceweather_last_error_message"] = message

    def _record_poll_success(self, state: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        self._last_fetch_ok_at = now
        self._last_error_message = None
        state["spaceweather_last_error_at"] = None
        state["spaceweather_last_error_message"] = None

    def _passes_filters(self, alert: ParsedSpaceWeather) -> bool:
        sw = self.config.space_weather
        message_type = alert.message_type
        if message_type == "summary" and not sw.announce_summaries:
            return False
        if message_type == "watch" and not sw.announce_watches:
            return False
        if message_type == "warning" and not sw.announce_warnings:
            return False
        if message_type == "alert" and not sw.announce_alerts:
            return False
        if message_type == "other":
            return False
        if sw.min_geomagnetic_scale > 0 and alert.geomagnetic_scale < sw.min_geomagnetic_scale:
            return False
        if sw.min_radio_blackout_scale > 0 and alert.radio_blackout_scale < sw.min_radio_blackout_scale:
            return False
        if sw.min_solar_radiation_scale > 0 and alert.solar_radiation_scale < sw.min_solar_radiation_scale:
            return False
        return True

    def _already_announced(self, announcement_key: str, state: Dict[str, Any]) -> bool:
        announced = state.get("spaceweather_announced_alerts") or []
        if not isinstance(announced, list):
            return False
        return announcement_key in announced

    def mark_announced(self, announcement_key: str, state: Dict[str, Any]) -> None:
        announced = state.get("spaceweather_announced_alerts")
        if not isinstance(announced, list):
            announced = []
        if announcement_key not in announced:
            announced.append(announcement_key)
        state["spaceweather_announced_alerts"] = announced[-500:]

    def select_new_alerts(
        self,
        alerts: List[ParsedSpaceWeather],
        state: Dict[str, Any],
    ) -> List[SpaceWeatherAlert]:
        selected: List[SpaceWeatherAlert] = []
        tracked: List[Dict[str, Any]] = []
        recent_alerts = alerts[:DISPLAY_TRACKED_LIMIT]

        for alert in recent_alerts:
            within_filters = self._passes_filters(alert)
            announced = self._already_announced(alert.announcement_key, state)
            tracked.append(
                {
                    "product_id": alert.product_id,
                    "title": alert.title,
                    "message_type": alert.message_type,
                    "geomagnetic_scale": alert.geomagnetic_scale,
                    "radio_blackout_scale": alert.radio_blackout_scale,
                    "solar_radiation_scale": alert.solar_radiation_scale,
                    "issued_utc": alert.issued_utc.isoformat(),
                    "within_range": within_filters,
                    "announced": announced,
                }
            )
            if not within_filters or announced:
                continue
            selected.append(
                SpaceWeatherAlert(
                    product_id=alert.product_id,
                    title=alert.title,
                    message_type=alert.message_type,
                    geomagnetic_scale=alert.geomagnetic_scale,
                    radio_blackout_scale=alert.radio_blackout_scale,
                    announcement_key=alert.announcement_key,
                    tts_text=alert.tts_text,
                    issued_utc=alert.issued_utc,
                )
            )

        self._tracked_alerts = tracked
        return selected

    async def fetch_alerts_json(self) -> Optional[list[Any]]:
        cache_key = "swpc:alerts.json"

        async def _fetch() -> Optional[list[Any]]:
            return await self._fetch_alerts_json_uncached()

        return await self._fetch_cache.get_or_fetch(cache_key, _fetch)

    async def _fetch_alerts_json_uncached(self) -> Optional[list[Any]]:
        try:
            response = await self._client.get(SWPC_ALERTS_URL)
            response.raise_for_status()
            data = response.json()
            self._last_error_message = None
            if isinstance(data, list):
                return data
            return None
        except httpx.HTTPError as exc:
            logger.warning("SWPC alerts fetch failed: %s", exc)
            self._last_error_message = f"SWPC alerts fetch failed: {exc}"
            return None
        except ValueError as exc:
            logger.warning("SWPC alerts response invalid: %s", exc)
            self._last_error_message = f"SWPC alerts response invalid: {exc}"
            return None

    async def check_health(self, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = state or {}
        sw = self.config.space_weather
        details: Dict[str, Any] = {
            "min_geomagnetic_scale": sw.min_geomagnetic_scale,
            "min_radio_blackout_scale": sw.min_radio_blackout_scale,
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "tracked_alerts": len(self._tracked_alerts),
        }

        data = await self.fetch_alerts_json()
        if data is None:
            msg = self._last_error_message or "SWPC alerts fetch failed"
            if state.get("spaceweather_last_error_message"):
                msg = str(state["spaceweather_last_error_message"])
            return {"ok": False, "message": msg, "details": details}

        alerts = parse_swpc_alerts(data)
        details["alerts_in_feed"] = len(alerts)
        return {
            "ok": True,
            "message": f"SWPC feed OK ({len(alerts)} alert(s) in feed)",
            "details": details,
        }

    async def refresh_tracked_alerts_if_stale(self, state: Dict[str, Any]) -> None:
        if not self.config.space_weather.enabled:
            self._tracked_alerts = []
            return

        now = datetime.now(timezone.utc)
        if self._last_display_refresh_at is not None:
            elapsed_min = (now - self._last_display_refresh_at).total_seconds() / 60.0
            if elapsed_min < DISPLAY_REFRESH_MINUTES:
                return

        data = await self.fetch_alerts_json()
        self._last_display_refresh_at = datetime.now(timezone.utc)
        if data is None:
            return

        alerts = parse_swpc_alerts(data)
        self.select_new_alerts(alerts, state)

    async def poll(self, state: Dict[str, Any]) -> List[SpaceWeatherAlert]:
        if not self.config.space_weather.enabled:
            self._tracked_alerts = []
            return []

        data = await self.fetch_alerts_json()
        if data is None:
            self._record_poll_error(
                state,
                self._last_error_message or "SWPC alerts fetch failed",
            )
            return []

        alerts = parse_swpc_alerts(data)
        selected = self.select_new_alerts(alerts, state)
        self._last_poll_at = datetime.now(timezone.utc)
        self._last_display_refresh_at = self._last_poll_at
        self._record_poll_success(state)

        sw = self.config.space_weather
        if sw.announce_enabled:
            cap = sw.max_announcements_per_cycle
            if len(selected) > cap:
                logger.info(
                    "SWPC: deferring %s alert(s) to later poll cycles (cap=%s)",
                    len(selected) - cap,
                    cap,
                )
                selected = selected[:cap]
        if selected:
            logger.info("SWPC: %s new space weather alert(s)", len(selected))
        return selected

    def get_status(self, state: Dict[str, Any]) -> Dict[str, Any]:
        sw = self.config.space_weather
        return {
            "enabled": sw.enabled,
            "announce_enabled": sw.announce_enabled,
            "poll_interval_minutes": sw.poll_interval_minutes,
            "min_geomagnetic_scale": sw.min_geomagnetic_scale,
            "min_radio_blackout_scale": sw.min_radio_blackout_scale,
            "min_solar_radiation_scale": sw.min_solar_radiation_scale,
            "announce_watches": sw.announce_watches,
            "announce_warnings": sw.announce_warnings,
            "announce_alerts": sw.announce_alerts,
            "announce_summaries": sw.announce_summaries,
            "max_announcements_per_cycle": sw.max_announcements_per_cycle,
            "display_tracked_limit": DISPLAY_TRACKED_LIMIT,
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "tracked_alerts": self._tracked_alerts,
            "announced_count": len(state.get("spaceweather_announced_alerts") or []),
            "last_error_message": self._last_error_message,
            "last_fetch_ok_at": (
                self._last_fetch_ok_at.isoformat() if self._last_fetch_ok_at else None
            ),
        }
