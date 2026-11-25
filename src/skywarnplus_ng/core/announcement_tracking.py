"""
NWS voice announcement outcomes, delivery retries, and quiet-hours catch-up.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..database.manager import DatabaseError
from ..tsunami.parser import is_tsunami_event
from .models import AlertSeverity, WeatherAlert
from .state import (
    ANNOUNCEMENT_RETRY_MAX_ATTEMPTS,
    FAIL_DELIVERY_NOT_CONFIGURED,
    FAIL_NO_MATCHING_NODE,
    FAIL_PLAYBACK,
    SKIP_ALREADY_ANNOUNCED,
    SKIP_BLOCKED_EVENT,
    SKIP_EXPIRED,
    SKIP_GEO_HAZARD_TSUNAMI,
    SKIP_QUIET_HOURS,
    SKIP_VOICE_DISABLED,
)

if TYPE_CHECKING:
    from ..api.nws_client import NWSClient
    from ..asterisk.manager import AsteriskManager
    from ..audio.manager import AudioManager
    from ..database.manager import DatabaseManager
    from ..location.mobile_counties import MobileCountyService
    from ..playback.policy import PlaybackPolicy
    from ..tsunami.tsunami_service import TsunamiService
    from .config import AppConfig
    from .state import ApplicationState

logger = logging.getLogger(__name__)


class AnnouncementTrackingMixin:
    """Records announcement outcomes and re-voices alerts that failed or were held."""

    # Provided by SkywarnPlusApplication.
    config: AppConfig
    state: dict[str, Any]
    playback_policy: PlaybackPolicy | None
    audio_manager: AudioManager | None
    asterisk_manager: AsteriskManager | None
    tsunami_service: TsunamiService | None
    state_manager: ApplicationState
    nws_client: NWSClient | None
    database_manager: DatabaseManager | None
    mobile_county_service: MobileCountyService | None
    _last_announce_failure: str | None
    _last_announce_targets: list[int] | None

    if TYPE_CHECKING:

        async def _announce_alert(
            self, alert: WeatherAlert, only_nodes: list[int] | None = None
        ) -> list[int]: ...

        def _announce_skip_reason(self, alert: WeatherAlert) -> str | None: ...

        def _matches_pattern(self, text: str, pattern: str) -> bool: ...

    def _announcement_delivery_configured(self) -> bool:
        """True when voice delivery is set up, so a failed attempt is worth retrying."""
        return bool(
            self.audio_manager
            and self.asterisk_manager
            and self.config.asterisk.enabled
            and self.config.asterisk.nodes
        )

    def _target_nodes_for_alert(self, alert: WeatherAlert) -> list[int]:
        """Nodes that should voice this alert based on its counties."""
        county_codes_list = getattr(alert, "county_codes", []) or []
        if self.mobile_county_service:
            return list(self.mobile_county_service.get_nodes_for_counties(county_codes_list))
        return list(self.config.get_nodes_for_counties(county_codes_list))

    def _record_announcement_outcome(
        self,
        alert: WeatherAlert,
        successful_nodes: list[int],
        attempted_nodes: list[int] | None = None,
    ) -> None:
        """
        Record what happened to an announcement attempt and schedule retries for missed nodes.

        Without the retry, an alert whose first announcement failed (TTS error, missing audio,
        Asterisk unavailable) is stored in state and never voiced on later polls.

        Args:
            attempted_nodes: Nodes the caller asked to play on. The nodes ``_announce_alert``
                actually attempted take precedence when known.
        """
        failure_reason = getattr(self, "_last_announce_failure", None) or FAIL_PLAYBACK
        if not self._announcement_delivery_configured():
            self.state_manager.clear_announcement_retry(self.state, alert.id)
            self._set_skipped_outcome(alert, FAIL_DELIVERY_NOT_CONFIGURED)
            return
        if not successful_nodes and failure_reason == SKIP_EXPIRED:
            self.state_manager.clear_announcement_retry(self.state, alert.id)
            previous = self.state_manager.get_announcement_outcome(self.state, alert.id) or {}
            if previous.get("status") != "skipped" and previous.get("played_nodes"):
                # Keep nodes that already played; the rest expired before their retry.
                self._set_delivery_outcome(alert, {}, SKIP_EXPIRED)
            else:
                self._set_skipped_outcome(alert, SKIP_EXPIRED)
            return
        played_targets = getattr(self, "_last_announce_targets", None)
        if played_targets is not None:
            targets = list(played_targets)
        elif attempted_nodes is not None:
            targets = list(attempted_nodes)
        else:
            targets = self._target_nodes_for_alert(alert)
        pending = sorted(set(targets) - set(successful_nodes))
        gave_up = False
        if pending:
            scheduled = self.state_manager.schedule_announcement_retry(
                self.state, alert.id, pending, delivered_nodes=successful_nodes
            )
            gave_up = not scheduled
        else:
            self.state_manager.clear_announcement_retry(self.state, alert.id)
        node_results = {str(int(n)): "played" for n in successful_nodes}
        node_results.update({str(int(n)): "failed" for n in pending})
        reason = FAIL_NO_MATCHING_NODE if not targets else failure_reason
        self._set_delivery_outcome(alert, node_results, reason, gave_up=gave_up)

    def _set_delivery_outcome(
        self,
        alert: WeatherAlert,
        node_results: dict[str, str],
        failure_reason: str,
        gave_up: bool = False,
    ) -> None:
        """Merge per-node results into the alert's outcome and derive its overall status."""
        previous = self.state_manager.get_announcement_outcome(self.state, alert.id) or {}
        nodes = dict(previous.get("nodes") or {}) if previous.get("status") != "skipped" else {}
        for node, result in node_results.items():
            # A node that already played stays "played"
            if nodes.get(node) != "played":
                nodes[node] = result
        played = sorted(int(n) for n, r in nodes.items() if r == "played")
        failed = sorted(int(n) for n, r in nodes.items() if r != "played")
        if played and not failed:
            status, reason = "played", None
        elif played:
            status, reason = "partial", failure_reason
        else:
            status, reason = "failed", failure_reason
        outcome: dict[str, Any] = {
            "status": status,
            "reason": reason,
            "nodes": nodes,
            "played_nodes": played,
            "failed_nodes": failed,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        retry = self.state_manager.get_announcement_retry(self.state, alert.id)
        if retry:
            outcome["retry"] = {
                "attempt": int(retry.get("attempts", 0)),
                "max_attempts": ANNOUNCEMENT_RETRY_MAX_ATTEMPTS,
                "next_retry_at": retry.get("next_retry_at"),
            }
        if gave_up:
            outcome["gave_up"] = True
        self.state_manager.set_announcement_outcome(self.state, alert.id, outcome)

    def _set_skipped_outcome(self, alert: WeatherAlert, reason: str, held: bool = False) -> None:
        """Record that an alert was intentionally not voiced (policy or configuration)."""
        outcome: dict[str, Any] = {
            "status": "skipped",
            "reason": reason,
            "nodes": {},
            "played_nodes": [],
            "failed_nodes": [],
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if held:
            outcome["held"] = True
        self.state_manager.set_announcement_outcome(self.state, alert.id, outcome)

    def _quiet_hours_catchup_enabled(self) -> bool:
        """True when alerts skipped for quiet hours should be voiced once they end."""
        return bool(self.config.alerts.quiet_hours.announce_held_on_end)

    def _note_skipped_announcement(self, alert: WeatherAlert, reason: str) -> None:
        """Record a skipped announcement; quiet-hours skips are held for catch-up."""
        if reason == SKIP_QUIET_HOURS and self._quiet_hours_catchup_enabled():
            self.state_manager.hold_for_quiet_hours(self.state, alert.id)
            self._set_skipped_outcome(alert, reason, held=True)
            return
        self._set_skipped_outcome(alert, reason)

    async def _store_announcement_result(
        self, alert: WeatherAlert, delivered_nodes: list[int] | None
    ) -> None:
        """
        Update the stored alert row with the latest announcement result and outcome.

        Args:
            delivered_nodes: Nodes that played on this attempt. Merged with every node that
                has played so far; ``None`` keeps the stored list.
        """
        if not self.database_manager:
            return
        outcome = self.state_manager.get_announcement_outcome(self.state, alert.id)
        if delivered_nodes is not None:
            delivered_nodes = sorted(
                {int(n) for n in delivered_nodes}
                | {int(n) for n in (outcome or {}).get("played_nodes") or []}
            )
        try:
            await self.database_manager.store_alert(
                alert=alert,
                announced=alert.id in self.state.get("last_sayalert", []),
                script_executed=alert.id in self.state.get("alertscript_alerts", []),
                announcement_nodes=delivered_nodes,
                announcement_outcome=outcome,
            )
        except DatabaseError as e:
            logger.error("Failed to update alert %s in database: %s", alert.id, e)

    async def _announce_held_alerts(self, active_alerts: list[WeatherAlert]) -> None:
        """
        Voice alerts that were held during quiet hours once quiet hours have ended.

        Without this, an alert that arrives during quiet hours (and is not allowed through as
        Severe/Extreme) is never voiced, even if it is still in effect the next morning.
        """
        held = self.state_manager.get_quiet_hours_held(self.state)
        if not held:
            return
        if not self._quiet_hours_catchup_enabled():
            for alert_id in held:
                self.state_manager.release_quiet_hours_hold(self.state, alert_id)
                outcome = self.state_manager.get_announcement_outcome(self.state, alert_id)
                if outcome and outcome.get("held"):
                    outcome.pop("held", None)
            return
        if self.playback_policy and self.playback_policy.is_quiet_hours_active():
            return

        by_id = {alert.id: alert for alert in active_alerts}
        due = [by_id[alert_id] for alert_id in held if alert_id in by_id]
        if due:
            logger.info("Quiet hours ended; announcing %d held alert(s)", len(due))
        for alert_id in held:
            if alert_id not in by_id:
                # Not active this poll; expiry handling prunes the hold.
                continue
            alert = by_id[alert_id]
            self.state_manager.release_quiet_hours_hold(self.state, alert_id)
            if self.nws_client and not self.nws_client.filter_active_alerts(
                [alert], time_type=self.config.alerts.time_type
            ):
                # Expired since this poll's fetch; never voice it late.
                continue
            skip_reason = self._announce_skip_reason(alert)
            if skip_reason == SKIP_ALREADY_ANNOUNCED:
                continue
            if skip_reason is not None:
                # Blocked, voice disabled, or on announcement hold since it was held.
                self._set_skipped_outcome(alert, skip_reason)
                await self._store_announcement_result(alert, None)
                continue
            logger.info("Announcing alert held during quiet hours: %s (%s)", alert.event, alert_id)
            announcement_nodes = await self._announce_alert(alert)
            if announcement_nodes:
                self.state_manager.mark_alert_announced(self.state, alert_id)
                if self.playback_policy:
                    self.playback_policy.record_announcement(alert, self.state)
            self._record_announcement_outcome(alert, announcement_nodes)
            await self._store_announcement_result(alert, announcement_nodes or None)

    def _record_node_delivery(
        self, attempted_nodes: list[int], successful_nodes: list[int]
    ) -> None:
        """AsteriskManager observer: track per-node playback health in state."""
        if getattr(self, "state", None) is None:
            return
        self.state_manager.record_node_delivery(self.state, attempted_nodes, successful_nodes)

    def _retry_allowed_now(self, alert: WeatherAlert) -> tuple[bool, bool]:
        """
        Decide whether a pending retry may run this poll.

        Returns:
            (allowed, keep_pending). keep_pending is False when the alert should no longer be
            voiced at all (announcements disabled or event blocked).
        """
        if not self.config.alerts.say_alert:
            self._set_skipped_outcome(alert, SKIP_VOICE_DISABLED)
            return False, False
        for blocked_event in self.config.filtering.say_alert_blocked:
            if self._matches_pattern(alert.event, blocked_event):
                self._set_skipped_outcome(alert, SKIP_BLOCKED_EVENT)
                return False, False
        if self.config.tsunami.enabled and self.tsunami_service and is_tsunami_event(alert.event):
            self._set_skipped_outcome(alert, SKIP_GEO_HAZARD_TSUNAMI)
            return False, False
        if self.playback_policy and self.playback_policy.is_quiet_hours_active():
            allow_severe = self.config.alerts.quiet_hours.allow_severe and alert.severity in (
                AlertSeverity.SEVERE,
                AlertSeverity.EXTREME,
            )
            if not allow_severe:
                return False, True
        return True, True

    async def _retry_failed_announcements(self, active_alerts: list[WeatherAlert]) -> None:
        """Retry voice announcements whose earlier delivery failed and whose backoff elapsed."""
        due = self.state_manager.get_due_announcement_retries(self.state)
        if not due:
            return
        by_id = {alert.id: alert for alert in active_alerts}
        for alert_id, entry in due.items():
            alert = by_id.get(alert_id)
            if alert is None:
                # Not active this poll; expiry handling prunes the entry.
                continue
            if self.nws_client and not self.nws_client.filter_active_alerts(
                [alert], time_type=self.config.alerts.time_type
            ):
                # Expired (or cancelled) since this poll's fetch; never voice it late.
                self.state_manager.clear_announcement_retry(self.state, alert_id)
                continue
            allowed, keep_pending = self._retry_allowed_now(alert)
            if not allowed:
                if not keep_pending:
                    self.state_manager.clear_announcement_retry(self.state, alert_id)
                continue
            current_targets = set(self._target_nodes_for_alert(alert))
            pending = [
                int(n) for n in entry.get("pending_nodes") or [] if int(n) in current_targets
            ]
            if not pending:
                self.state_manager.clear_announcement_retry(self.state, alert_id)
                delivered = sorted({int(n) for n in entry.get("delivered_nodes") or []})
                if delivered:
                    # Delivered nodes may include ones merged in from an alias of this alert.
                    self._set_delivery_outcome(
                        alert, {str(n): "played" for n in delivered}, FAIL_PLAYBACK
                    )
                    await self._store_announcement_result(alert, delivered)
                continue
            logger.info(
                "Retrying voice announcement for %s (%s) on nodes %s (attempt %s)",
                alert.event,
                alert_id,
                pending,
                int(entry.get("attempts", 0)) + 1,
            )
            successful = await self._announce_alert(alert, only_nodes=pending)
            self._record_announcement_outcome(alert, successful, attempted_nodes=pending)
            if successful:
                first_success = alert_id not in self.state.get("last_sayalert", [])
                self.state_manager.mark_alert_announced(self.state, alert_id)
                if first_success and self.playback_policy:
                    self.playback_policy.record_announcement(alert, self.state)
            # Store every attempt, so Alert History shows failed and given-up retries too.
            delivered = sorted(set(entry.get("delivered_nodes") or []) | set(successful))
            await self._store_announcement_result(alert, delivered or None)
