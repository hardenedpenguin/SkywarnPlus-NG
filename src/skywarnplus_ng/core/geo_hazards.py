"""
Geo-hazard voice announcements (NHC, USGS, wildfire, tsunami, space weather, volcano).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, TypedDict

from ..nhc.cyclone_service import CycloneAdvisory
from ..spaceweather.swpc_service import SpaceWeatherAlert
from ..tsunami.tsunami_service import TsunamiAlert
from ..usgs.earthquake_service import EarthquakeEvent
from ..volcano.volcano_service import VolcanoNotice
from ..wildfire.wfigs_service import WildfireIncident
from .state import (
    ANNOUNCEMENT_RETRY_BASE_SECONDS,
    ANNOUNCEMENT_RETRY_MAX_ATTEMPTS,
    ANNOUNCEMENT_RETRY_MAX_SECONDS,
)

if TYPE_CHECKING:
    from ..asterisk.manager import AsteriskManager
    from ..audio.manager import AudioManager
    from ..nhc.cyclone_service import NhcCycloneService
    from ..playback.policy import PlaybackPolicy
    from ..spaceweather.swpc_service import SwpcSpaceWeatherService
    from ..tsunami.tsunami_service import TsunamiService
    from ..usgs.earthquake_service import UsgsEarthquakeService
    from ..volcano.volcano_service import VolcanoService
    from ..wildfire.wfigs_service import WfigsWildfireService
    from .config import AppConfig

logger = logging.getLogger(__name__)


# Config field holding each feed's maximum item age, in hours.
_MAX_AGE_SETTINGS = {
    "nhc": "max_advisory_age_hours",
    "earthquake": "max_event_age_hours",
    "wildfire": "max_discovery_age_hours",
}


def _hazard_time(item: Any) -> datetime | None:
    """When a geo-hazard item was issued or observed, if the feed provides it."""
    for attr in ("issued_utc", "time_utc", "discovery_utc"):
        value = getattr(item, attr, None)
        if isinstance(value, datetime):
            return value
    return None


class GeoHazardSpeech(TypedDict):
    """What to say for a geo-hazard item, and how to name its audio file."""

    tts_text: str
    audio_prefix: str
    label: str


class GeoHazardAnnouncerMixin:
    """Polls geo-hazard feeds, voices new items, and retries nodes that missed playback."""

    # Provided by SkywarnPlusApplication.
    config: AppConfig
    state: dict[str, Any]
    playback_policy: PlaybackPolicy | None
    audio_manager: AudioManager | None
    asterisk_manager: AsteriskManager | None
    tsunami_service: TsunamiService | None
    nhc_service: NhcCycloneService | None
    earthquake_service: UsgsEarthquakeService | None
    wildfire_service: WfigsWildfireService | None
    space_weather_service: SwpcSpaceWeatherService | None
    volcano_service: VolcanoService | None

    if TYPE_CHECKING:

        def _announcement_delivery_configured(self) -> bool: ...

        def _persist_announced_state(self) -> None: ...

        async def _notify_geo_hazard_broadcast(self, *, title: str, message: str) -> None: ...

    async def _handle_nhc_advisories(self) -> None:
        """Poll NHC feed and announce new tropical cyclone advisories within range."""
        await self._handle_geo_hazard_feed(
            kind="nhc",
            service=self.nhc_service,
            key=lambda a: a.advisory_key,
            describe=lambda a: f"NHC advisory {a.advisory_key} ({a.name})",
            speech=self._cyclone_speech,
            title=lambda a: f"Tropical Cyclone: {a.name}",
        )

    async def _handle_earthquake_events(self) -> None:
        """Poll USGS and announce new earthquakes within range."""
        await self._handle_geo_hazard_feed(
            kind="earthquake",
            service=self.earthquake_service,
            key=lambda e: e.announcement_key,
            describe=lambda e: f"earthquake {e.event_id} (M{e.magnitude})",
            speech=self._earthquake_speech,
            title=lambda e: f"Earthquake M{e.magnitude}",
        )

    async def _handle_wildfire_incidents(self) -> None:
        """Poll WFIGS and announce new wildfire incidents within range."""
        await self._handle_geo_hazard_feed(
            kind="wildfire",
            service=self.wildfire_service,
            key=lambda i: i.announcement_key,
            describe=lambda i: f"wildfire {i.incident_id} ({i.name})",
            speech=self._wildfire_speech,
            title=lambda i: f"Wildfire: {i.name}",
        )

    async def _handle_tsunami_alerts(self) -> None:
        """Poll NWS and announce new tsunami alerts at the monitoring position."""
        await self._handle_geo_hazard_feed(
            kind="tsunami",
            service=self.tsunami_service,
            key=lambda a: a.announcement_key,
            describe=lambda a: f"tsunami {a.alert_id} ({a.event})",
            speech=self._tsunami_speech,
            title=lambda a: f"Tsunami: {a.event}",
        )

    async def _handle_space_weather_alerts(self) -> None:
        """Poll SWPC and announce new space weather alerts."""
        await self._handle_geo_hazard_feed(
            kind="space_weather",
            service=self.space_weather_service,
            key=lambda a: a.announcement_key,
            describe=lambda a: f"space weather {a.product_id} ({a.title})",
            speech=self._space_weather_speech,
            title=lambda a: f"Space Weather: {a.title}",
        )

    async def _handle_volcano_notices(self) -> None:
        """Poll USGS and announce new volcano notices within range."""
        await self._handle_geo_hazard_feed(
            kind="volcano",
            service=self.volcano_service,
            key=lambda n: n.announcement_key,
            describe=lambda n: f"volcano {n.vnum} ({n.name})",
            speech=self._volcano_speech,
            title=lambda n: f"Volcano: {n.name}",
        )

    async def _handle_geo_hazard_feed(
        self,
        *,
        kind: str,
        service: Any,
        key: Callable[[Any], str],
        describe: Callable[[Any], str],
        speech: Callable[[Any], GeoHazardSpeech],
        title: Callable[[Any], str],
    ) -> None:
        """
        Poll one geo-hazard feed and voice its new items.

        Items voiced on at least one node are marked announced (a complete failure is offered
        again by the service on its next poll); nodes that missed playback are queued for
        retry by ``_retry_geo_hazard_nodes``.
        """
        if not service or not hasattr(self, "state") or self.state is None:
            return
        if not service.should_poll():
            return

        items = await service.poll(self.state)
        self._persist_announced_state()
        for item in items:
            item_key = key(item)
            # Read the setting per item: the operator may disable voice while the feed polls.
            if not self._geo_hazard_voice_enabled(kind):
                service.mark_announced(item_key, self.state)
                self._persist_announced_state()
                continue
            if self.playback_policy:
                allowed, reason = self.playback_policy.should_announce_geo_hazard()
                if not allowed:
                    log_fn = logger.debug if reason == "quiet_hours" else logger.info
                    log_fn("Skipping %s: %s", describe(item), reason)
                    continue
            spoken = speech(item)
            played = await self._announce_position_hazard(**spoken)
            if not played:
                continue
            service.mark_announced(item_key, self.state)
            self._schedule_geo_hazard_node_retry(
                kind, item_key, spoken, played, issued_at=_hazard_time(item)
            )
            self._persist_announced_state()
            await self._notify_geo_hazard_broadcast(title=title(item), message=spoken["tts_text"])

    def _geo_hazard_voice_enabled(self, kind: str) -> bool:
        """True while a geo-hazard type is still enabled for voice announcements."""
        section = getattr(self.config, kind, None)
        if section is None or not getattr(section, "enabled", False):
            return False
        return bool(getattr(section, "announce_enabled", True))

    def _geo_hazard_still_current(self, entry: dict[str, Any], now: datetime) -> bool:
        """
        True while a queued geo-hazard is within its feed's maximum age.

        Mirrors the age filters the services apply when polling (for example
        ``nhc.max_advisory_age_hours``), using the current configuration.
        """
        setting = _MAX_AGE_SETTINGS.get(str(entry.get("kind")))
        raw = entry.get("issued_at")
        if not setting or not raw:
            return True
        section = getattr(self.config, str(entry.get("kind")), None)
        max_age_hours = getattr(section, setting, None)
        if not isinstance(max_age_hours, int | float) or max_age_hours <= 0:
            return True
        try:
            issued_at = datetime.fromisoformat(str(raw))
        except ValueError:
            return True
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=UTC)
        return now - issued_at <= timedelta(hours=max_age_hours)

    def _schedule_geo_hazard_node_retry(
        self,
        kind: str,
        item_key: str,
        spoken: GeoHazardSpeech,
        played: list[int],
        issued_at: datetime | None = None,
    ) -> None:
        """
        Queue nodes that missed a geo-hazard announcement for a later retry.

        Args:
            issued_at: When the hazard was issued/observed; retries stop once it is older
                than the feed's configured maximum age
        """
        targets = self.config.asterisk.get_nodes_list()
        pending = sorted(n for n in targets if n not in set(played))
        if not pending:
            return
        retries = self.state.get("geo_hazard_retries")
        if not isinstance(retries, dict):
            retries = {}
            self.state["geo_hazard_retries"] = retries
        retries[f"{kind}:{item_key}"] = {
            "kind": kind,
            **spoken,
            "pending_nodes": pending,
            "delivered_nodes": sorted(played),
            "attempts": 1,
            "issued_at": issued_at.isoformat() if issued_at else None,
            "next_retry_at": (
                datetime.now(UTC) + timedelta(seconds=ANNOUNCEMENT_RETRY_BASE_SECONDS)
            ).isoformat(),
        }
        logger.warning(
            "%s missed on nodes %s; retrying in %ss",
            spoken["label"],
            pending,
            ANNOUNCEMENT_RETRY_BASE_SECONDS,
        )

    async def _retry_geo_hazard_nodes(self) -> None:
        """Re-voice geo-hazard announcements on nodes that missed them, with backoff."""
        if not hasattr(self, "state") or self.state is None:
            return
        retries = self.state.get("geo_hazard_retries")
        if not isinstance(retries, dict) or not retries:
            return
        now = datetime.now(UTC)
        changed = False
        for retry_key, entry in list(retries.items()):
            if not isinstance(entry, dict):
                retries.pop(retry_key, None)
                changed = True
                continue
            try:
                due_at = datetime.fromisoformat(str(entry.get("next_retry_at")))
            except ValueError:
                due_at = now
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=UTC)
            if due_at > now:
                continue
            changed = True
            current = set(self.config.asterisk.get_nodes_list())
            pending = [int(n) for n in entry.get("pending_nodes") or [] if int(n) in current]
            drop_reason = None
            if not pending:
                drop_reason = "no pending nodes remain configured"
            elif not self._announcement_delivery_configured():
                drop_reason = "voice delivery is not configured"
            elif not self._geo_hazard_voice_enabled(str(entry.get("kind"))):
                drop_reason = "announcements disabled"
            elif not self._geo_hazard_still_current(entry, now):
                drop_reason = "no longer current"
            elif self.playback_policy:
                allowed, reason = self.playback_policy.should_announce_geo_hazard()
                if not allowed:
                    # Geo hazards are not replayed after quiet hours; stop retrying.
                    drop_reason = reason or "policy"
            if drop_reason:
                logger.info("Dropping retry for %s: %s", entry.get("label"), drop_reason)
                retries.pop(retry_key, None)
                continue

            attempts = int(entry.get("attempts", 1)) + 1
            logger.info(
                "Retrying %s on nodes %s (attempt %s)", entry.get("label"), pending, attempts
            )
            played = await self._announce_position_hazard(
                tts_text=str(entry.get("tts_text", "")),
                audio_prefix=str(entry.get("audio_prefix", "geo")),
                label=str(entry.get("label", retry_key)),
                only_nodes=pending,
            )
            remaining = [n for n in pending if n not in set(played)]
            if not remaining:
                retries.pop(retry_key, None)
                continue
            if attempts >= ANNOUNCEMENT_RETRY_MAX_ATTEMPTS:
                logger.error(
                    "Giving up on %s for nodes %s after %s attempts",
                    entry.get("label"),
                    remaining,
                    attempts,
                )
                retries.pop(retry_key, None)
                continue
            delay = min(
                ANNOUNCEMENT_RETRY_BASE_SECONDS * (2 ** (attempts - 1)),
                ANNOUNCEMENT_RETRY_MAX_SECONDS,
            )
            entry["attempts"] = attempts
            entry["pending_nodes"] = remaining
            entry["delivered_nodes"] = sorted(set(entry.get("delivered_nodes") or []) | set(played))
            entry["next_retry_at"] = (now + timedelta(seconds=delay)).isoformat()
        if changed:
            self._persist_announced_state()

    async def _announce_position_hazard(
        self,
        *,
        tts_text: str,
        audio_prefix: str,
        label: str,
        only_nodes: list[int] | None = None,
    ) -> list[int]:
        """
        Announce a geo hazard (cyclone, earthquake, wildfire, ...) on all configured nodes.

        Args:
            only_nodes: Restrict playback to these nodes (used when retrying missed nodes)

        Returns:
            Node numbers where playback started (empty if it failed everywhere)
        """
        logger.info("Announcing %s", label)

        if not self.audio_manager:
            logger.warning("Audio manager not available - skipping %s", label)
            return []
        if not self.asterisk_manager or not self.config.asterisk.enabled:
            logger.warning("Asterisk not available - skipping %s", label)
            return []
        nodes = self.config.asterisk.get_nodes_list()
        if only_nodes is not None:
            allowed = set(only_nodes)
            nodes = [n for n in nodes if n in allowed]
        if not nodes:
            logger.warning("No Asterisk nodes configured - skipping %s", label)
            return []

        try:
            audio_path = await asyncio.to_thread(
                self.audio_manager.generate_spoken_audio,
                tts_text,
                prefix=audio_prefix,
            )
            if not audio_path or not audio_path.exists() or audio_path.stat().st_size == 0:
                logger.error("Failed to generate audio for %s", label)
                return []

            successful_nodes = await self.asterisk_manager.play_audio_on_nodes(audio_path, nodes)
            if successful_nodes:
                logger.info(
                    "%s audio playing on %s nodes: %s",
                    label,
                    len(successful_nodes),
                    successful_nodes,
                )
                if self.config.asterisk.audio_delay > 0:
                    await asyncio.sleep(self.config.asterisk.audio_delay / 1000.0)
                return list(successful_nodes)

            logger.error("Failed to play audio on any nodes for %s", label)
            return []
        except Exception as e:
            logger.error("Error announcing %s: %s", label, e, exc_info=True)
            return []

    @staticmethod
    def _speech(tts_text: str, audio_prefix: str, label: str) -> GeoHazardSpeech:
        return GeoHazardSpeech(tts_text=tts_text, audio_prefix=audio_prefix, label=label)

    def _earthquake_speech(self, event: EarthquakeEvent) -> GeoHazardSpeech:
        return self._speech(
            event.tts_text,
            f"usgs_{event.event_id.replace('.', '_')[:40]}",
            f"earthquake M{event.magnitude} ({event.distance_miles} mi)",
        )

    def _wildfire_speech(self, incident: WildfireIncident) -> GeoHazardSpeech:
        prefix = (
            self.wildfire_service.audio_prefix_for(incident.incident_id)
            if self.wildfire_service
            else f"wildfire_{incident.incident_id[:40]}"
        )
        return self._speech(
            incident.tts_text, prefix, f"wildfire {incident.name} ({incident.distance_miles} mi)"
        )

    def _tsunami_speech(self, alert: TsunamiAlert) -> GeoHazardSpeech:
        safe_id = re.sub(r"[^A-Za-z0-9_]", "_", alert.alert_id)[:40]
        return self._speech(alert.tts_text, f"tsunami_{safe_id}", f"tsunami {alert.event}")

    def _space_weather_speech(self, alert: SpaceWeatherAlert) -> GeoHazardSpeech:
        return self._speech(
            alert.tts_text,
            f"swpc_{alert.product_id.lower()[:40]}",
            f"space weather {alert.title}",
        )

    def _volcano_speech(self, notice: VolcanoNotice) -> GeoHazardSpeech:
        dist = notice.distance_miles if notice.distance_miles is not None else "?"
        return self._speech(
            notice.tts_text, f"volcano_{notice.vnum[:40]}", f"volcano {notice.name} ({dist} mi)"
        )

    def _cyclone_speech(self, advisory: CycloneAdvisory) -> GeoHazardSpeech:
        return self._speech(
            advisory.tts_text,
            f"nhc_{advisory.atcf}",
            f"NHC advisory {advisory.storm_type} {advisory.name} ({advisory.distance_miles} mi)",
        )
