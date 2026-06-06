"""Voice announcement policy: quiet hours and announcement hold."""

from __future__ import annotations

import logging
from datetime import datetime, time
from typing import TYPE_CHECKING, Any, Dict, Optional
from zoneinfo import ZoneInfo

from ..core.models import AlertSeverity, WeatherAlert

if TYPE_CHECKING:
    from ..core.config import AlertConfig

logger = logging.getLogger(__name__)


def _parse_hhmm(value: str) -> Optional[time]:
    try:
        hour_str, minute_str = value.strip().split(":", 1)
        return time(hour=int(hour_str), minute=int(minute_str))
    except (ValueError, AttributeError):
        return None


def _in_quiet_window(now_local: datetime, start: time, end: time) -> bool:
    current = now_local.time()
    if start <= end:
        return start <= current < end
    # Overnight window (e.g. 22:00 -> 06:00)
    return current >= start or current < end


class PlaybackPolicy:
    """Decide whether voice announcements should play."""

    def __init__(self, alert_config: AlertConfig) -> None:
        self.config = alert_config

    def _local_now(self, now: datetime) -> datetime:
        tz_name = self.config.quiet_hours.timezone
        if tz_name:
            try:
                return now.astimezone(ZoneInfo(tz_name))
            except Exception:
                logger.warning("Invalid quiet_hours.timezone %r; using system local", tz_name)
        return now.astimezone()

    def is_quiet_hours_active(self, now: Optional[datetime] = None) -> bool:
        qh = self.config.quiet_hours
        if not qh.enabled:
            return False
        start = _parse_hhmm(qh.start)
        end = _parse_hhmm(qh.end)
        if not start or not end:
            return False
        now = now or datetime.now().astimezone()
        return _in_quiet_window(self._local_now(now), start, end)

    def announcement_signature(self, alert: WeatherAlert) -> str:
        counties = ",".join(sorted(alert.county_codes or []))
        return f"{alert.event}|{counties}"

    def is_on_announcement_hold(
        self,
        alert: WeatherAlert,
        state: Dict[str, Any],
        now: Optional[datetime] = None,
    ) -> bool:
        hold_minutes = int(self.config.announcement_hold_minutes or 0)
        if hold_minutes <= 0:
            return False
        cooldown = state.get("announcement_cooldown") or {}
        if not isinstance(cooldown, dict):
            return False
        signature = self.announcement_signature(alert)
        last_raw = cooldown.get(signature)
        if not last_raw:
            return False
        now = now or datetime.now().astimezone()
        try:
            last_at = datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
        except ValueError:
            return False
        elapsed = (now - last_at).total_seconds() / 60.0
        return elapsed < hold_minutes

    def record_announcement(
        self,
        alert: WeatherAlert,
        state: Dict[str, Any],
        now: Optional[datetime] = None,
    ) -> None:
        hold_minutes = int(self.config.announcement_hold_minutes or 0)
        if hold_minutes <= 0:
            return
        cooldown = state.get("announcement_cooldown")
        if not isinstance(cooldown, dict):
            cooldown = {}
        now = now or datetime.now().astimezone()
        cooldown[self.announcement_signature(alert)] = now.isoformat()
        state["announcement_cooldown"] = cooldown

    def should_announce_voice(
        self,
        alert: WeatherAlert,
        state: Dict[str, Any],
        now: Optional[datetime] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Return (allowed, skip_reason).

        skip_reason is a short code for logging/status when not allowed.
        """
        now = now or datetime.now().astimezone()
        if self.is_quiet_hours_active(now):
            if self.config.quiet_hours.allow_severe and alert.severity in (
                AlertSeverity.SEVERE,
                AlertSeverity.EXTREME,
            ):
                pass
            else:
                return False, "quiet_hours"

        if self.is_on_announcement_hold(alert, state, now):
            return False, "announcement_hold"

        return True, None

    def should_announce_cyclone(self, now: Optional[datetime] = None) -> tuple[bool, Optional[str]]:
        """Cyclone advisories respect quiet hours but not county hold signatures."""
        now = now or datetime.now().astimezone()
        if self.is_quiet_hours_active(now):
            return False, "quiet_hours"
        return True, None

    def get_status(self, state: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or datetime.now().astimezone()
        return {
            "quiet_hours_active": self.is_quiet_hours_active(now),
            "announcement_hold_minutes": self.config.announcement_hold_minutes,
            "quiet_hours": {
                "enabled": self.config.quiet_hours.enabled,
                "start": self.config.quiet_hours.start,
                "end": self.config.quiet_hours.end,
                "allow_severe": self.config.quiet_hours.allow_severe,
            },
            "cooldown_entries": len(state.get("announcement_cooldown") or {}),
        }
