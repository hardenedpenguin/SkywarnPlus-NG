"""NWS tsunami polling and voice announcement selection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..geo_hazard.position_health import (
    append_gps_health_details,
    missing_position_message,
    position_source_label,
)
from ..location.position import get_monitoring_position
from .parser import ParsedTsunami, level_rank, parse_tsunami_features

if TYPE_CHECKING:
    from ..api.nws_client import NWSClient
    from ..core.config import AppConfig
    from ..location.mobile_counties import MobileCountyService

logger = logging.getLogger(__name__)

DISPLAY_REFRESH_MINUTES = 5


@dataclass(frozen=True)
class TsunamiAlert:
    """Tsunami alert selected for announcement."""

    alert_id: str
    event: str
    level: str
    headline: str
    announcement_key: str
    tts_text: str
    issued_utc: datetime


class TsunamiService:
    """Fetch and filter NWS tsunami alerts at the monitoring position."""

    def __init__(
        self,
        config: AppConfig,
        nws_client: NWSClient,
        mobile_service: MobileCountyService | None = None,
    ) -> None:
        self.config = config
        self.nws_client = nws_client
        self.mobile_service = mobile_service
        self._last_poll_at: datetime | None = None
        self._tracked_alerts: list[dict[str, Any]] = []
        self._last_fetch_ok_at: datetime | None = None
        self._last_error_message: str | None = None
        self._last_display_refresh_at: datetime | None = None

    def should_poll(self, now: datetime | None = None) -> bool:
        if not self.config.tsunami.enabled:
            return False
        now = now or datetime.now(UTC)
        if self._last_poll_at is None:
            return True
        elapsed = (now - self._last_poll_at).total_seconds() / 60.0
        return elapsed >= self.config.tsunami.poll_interval_minutes

    def get_position(self) -> tuple[float, float] | None:
        pos = self.config.geo_hazard_position
        return get_monitoring_position(
            use_gps_position=pos.use_gps_position,
            static_lat=pos.static_lat,
            static_lon=pos.static_lon,
            mobile_service=self.mobile_service,
        )

    def _record_poll_error(self, state: dict[str, Any], message: str) -> None:
        now = datetime.now(UTC)
        self._last_error_message = message
        state["tsunami_last_error_at"] = now.isoformat()
        state["tsunami_last_error_message"] = message

    def _record_poll_success(self, state: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        self._last_fetch_ok_at = now
        self._last_error_message = None
        state["tsunami_last_error_at"] = None
        state["tsunami_last_error_message"] = None

    def _passes_filters(self, alert: ParsedTsunami) -> bool:
        ts = self.config.tsunami
        min_rank = level_rank(ts.min_level)
        return level_rank(alert.level) >= min_rank

    def _already_announced(self, announcement_key: str, state: dict[str, Any]) -> bool:
        announced = state.get("tsunami_announced_alerts") or []
        if not isinstance(announced, list):
            return False
        return announcement_key in announced

    def mark_announced(self, announcement_key: str, state: dict[str, Any]) -> None:
        announced = state.get("tsunami_announced_alerts")
        if not isinstance(announced, list):
            announced = []
        if announcement_key not in announced:
            announced.append(announcement_key)
        state["tsunami_announced_alerts"] = announced[-500:]

    def _maybe_seed_announced_history(
        self,
        alerts: list[ParsedTsunami],
        state: dict[str, Any],
    ) -> None:
        if state.get("tsunami_history_seeded"):
            return
        ts = self.config.tsunami
        seeded = 0
        if not ts.announce_history_on_enable:
            for alert in alerts:
                if self._passes_filters(alert):
                    self.mark_announced(alert.announcement_key, state)
                    seeded += 1
            if seeded:
                logger.info(
                    "Tsunami: seeded %s existing alert(s) as announced "
                    "(announce_history_on_enable=false)",
                    seeded,
                )
        state["tsunami_history_seeded"] = True

    def select_new_alerts(
        self,
        alerts: list[ParsedTsunami],
        state: dict[str, Any],
    ) -> list[TsunamiAlert]:
        selected: list[TsunamiAlert] = []
        tracked: list[dict[str, Any]] = []

        for alert in alerts:
            within_filters = self._passes_filters(alert)
            announced = self._already_announced(alert.announcement_key, state)
            tracked.append(
                {
                    "alert_id": alert.alert_id,
                    "event": alert.event,
                    "level": alert.level,
                    "headline": alert.headline,
                    "severity": alert.severity,
                    "issued_utc": alert.issued_utc.isoformat(),
                    "within_range": within_filters,
                    "announced": announced,
                }
            )
            if not within_filters or announced:
                continue
            selected.append(
                TsunamiAlert(
                    alert_id=alert.alert_id,
                    event=alert.event,
                    level=alert.level,
                    headline=alert.headline,
                    announcement_key=alert.announcement_key,
                    tts_text=alert.tts_text,
                    issued_utc=alert.issued_utc,
                )
            )

        self._tracked_alerts = tracked
        return selected

    async def fetch_features_at_position(
        self, position: tuple[float, float]
    ) -> list[dict[str, Any]] | None:
        try:
            features = await self.nws_client.fetch_active_alert_features_at_point(
                position[0], position[1]
            )
            self._last_error_message = None
            return features
        except Exception as exc:
            logger.warning("NWS tsunami fetch failed: %s", exc)
            self._last_error_message = f"NWS tsunami fetch failed: {exc}"
            return None

    async def check_health(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = state or {}
        ts = self.config.tsunami
        details: dict[str, Any] = {
            "min_level": ts.min_level,
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "tracked_alerts": len(self._tracked_alerts),
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

        features = await self.fetch_features_at_position(position)
        if features is None:
            msg = self._last_error_message or "NWS tsunami fetch failed"
            if state.get("tsunami_last_error_message"):
                msg = str(state["tsunami_last_error_message"])
            return {"ok": False, "message": msg, "details": details}

        alerts = parse_tsunami_features(features, min_level=ts.min_level)
        details["alerts_in_feed"] = len(alerts)
        return {
            "ok": True,
            "message": f"NWS tsunami feed OK ({len(alerts)} alert(s) at position)",
            "details": details,
        }

    async def refresh_tracked_alerts_if_stale(self, state: dict[str, Any]) -> None:
        if not self.config.tsunami.enabled:
            self._tracked_alerts = []
            return

        now = datetime.now(UTC)
        if self._last_display_refresh_at is not None:
            elapsed_min = (now - self._last_display_refresh_at).total_seconds() / 60.0
            if elapsed_min < DISPLAY_REFRESH_MINUTES:
                return

        position = self.get_position()
        if position is None:
            return

        features = await self.fetch_features_at_position(position)
        self._last_display_refresh_at = datetime.now(UTC)
        if features is None:
            return

        alerts = parse_tsunami_features(features, min_level=self.config.tsunami.min_level)
        self.select_new_alerts(alerts, state)

    async def poll(self, state: dict[str, Any]) -> list[TsunamiAlert]:
        if not self.config.tsunami.enabled:
            self._tracked_alerts = []
            return []

        position = self.get_position()
        if position is None:
            msg = "No position available (GPS or static lat/lon)"
            logger.warning("Tsunami monitoring enabled but %s", msg)
            self._record_poll_error(state, msg)
            return []

        features = await self.fetch_features_at_position(position)
        if features is None:
            self._record_poll_error(
                state,
                self._last_error_message or "NWS tsunami fetch failed",
            )
            return []

        alerts = parse_tsunami_features(features, min_level=self.config.tsunami.min_level)
        self._maybe_seed_announced_history(alerts, state)
        selected = self.select_new_alerts(alerts, state)
        self._last_poll_at = datetime.now(UTC)
        self._last_display_refresh_at = self._last_poll_at
        self._record_poll_success(state)

        ts = self.config.tsunami
        if ts.announce_enabled:
            cap = ts.max_announcements_per_cycle
            if len(selected) > cap:
                logger.info(
                    "Tsunami: deferring %s alert(s) to later poll cycles (cap=%s)",
                    len(selected) - cap,
                    cap,
                )
                selected = selected[:cap]
        if selected:
            logger.info(
                "Tsunami: %s new alert(s) at position (min level=%s)",
                len(selected),
                ts.min_level,
            )
        return selected

    def get_status(self, state: dict[str, Any]) -> dict[str, Any]:
        position = self.get_position()
        ts = self.config.tsunami
        return {
            "enabled": ts.enabled,
            "announce_enabled": ts.announce_enabled,
            "poll_interval_minutes": ts.poll_interval_minutes,
            "min_level": ts.min_level,
            "max_announcements_per_cycle": ts.max_announcements_per_cycle,
            "announce_history_on_enable": ts.announce_history_on_enable,
            "history_seeded": bool(state.get("tsunami_history_seeded")),
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "position": ({"lat": position[0], "lon": position[1]} if position else None),
            "tracked_alerts": self._tracked_alerts,
            "announced_count": len(state.get("tsunami_announced_alerts") or []),
            "last_error_message": self._last_error_message,
            "last_fetch_ok_at": (
                self._last_fetch_ok_at.isoformat() if self._last_fetch_ok_at else None
            ),
        }
