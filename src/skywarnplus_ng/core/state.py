"""
State management for SkywarnPlus-NG.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Any
from collections import OrderedDict

from .models import WeatherAlert

logger = logging.getLogger(__name__)

TRACKING_LIST_MAX = 2000


class ApplicationState:
    """Manages persistent application state."""

    def __init__(self, state_file: Path):
        """
        Initialize state manager.

        Args:
            state_file: Path to the state file (JSON)
        """
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> Dict[str, Any]:
        """
        Load state from file.

        Returns:
            State dictionary with default values if file doesn't exist
        """
        if not self.state_file.exists():
            logger.info(f"State file {self.state_file} not found, creating default state")
            return self._get_default_state()

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)

            # Ensure required keys exist
            for key, default_value in self._get_default_state().items():
                if key not in state:
                    state[key] = default_value
                    logger.debug(f"Added missing state key: {key}")

            # Convert last_alerts back to OrderedDict to preserve order
            if "last_alerts" in state and isinstance(state["last_alerts"], list):
                state["last_alerts"] = OrderedDict(state["last_alerts"])
            elif "last_alerts" not in state:
                state["last_alerts"] = OrderedDict()

            logger.debug(f"Loaded state from {self.state_file}")
            return state

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load state from {self.state_file}: {e}")
            logger.info("Using default state")
            return self._get_default_state()

    def save_state(self, state: Dict[str, Any]) -> None:
        """
        Save state to file atomically.

        Args:
            state: State dictionary to save
        """
        try:
            state_copy = state.copy()

            if "last_alerts" in state_copy and isinstance(state_copy["last_alerts"], OrderedDict):
                state_copy["last_alerts"] = list(state_copy["last_alerts"].items())

            for key, value in state_copy.items():
                if isinstance(value, set):
                    state_copy[key] = list(value)

            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=self.state_file.parent,
                prefix=".state-",
                suffix=".json",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(state_copy, f, indent=2, ensure_ascii=False, default=str)
                os.replace(tmp_path, self.state_file)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            logger.debug(f"Saved state to {self.state_file}")

        except (IOError, TypeError, OSError) as e:
            logger.error(f"Failed to save state to {self.state_file}: {e}")

    def _get_default_state(self) -> Dict[str, Any]:
        """Get default state values."""
        return {
            "last_alerts": OrderedDict(),  # Alert ID -> Alert data
            "active_alerts": [],  # Currently active alert IDs
            "last_sayalert": [],  # Alerts that were announced
            "alertscript_alerts": [],  # Alerts that triggered scripts
            "webhook_sent_alerts": [],  # Alerts that had webhooks sent
            "last_poll": None,  # Last NWS poll attempt timestamp
            "last_all_clear": None,  # Last all-clear timestamp
            "nws_last_error_at": None,  # When NWS fetch last failed (ISO); None if last fetch OK
            "nws_last_error_message": None,  # Short reason for operators / dashboard
            "nhc_last_error_at": None,  # When NHC poll last failed (ISO); None if last poll OK
            "nhc_last_error_message": None,  # Short reason for operators / dashboard
            "ct": None,  # Current courtesy tone mode ('normal' or 'wx')
            "id": None,  # Current identifier
            "announcement_cooldown": {},  # event|counties signature -> last announce ISO time
            "nhc_announced_advisories": [],  # NHC advisory keys already voiced
            "usgs_history_seeded": False,
            "wildfire_history_seeded": False,
            "usgs_last_error_at": None,
            "usgs_last_error_message": None,
            "usgs_announced_events": [],  # USGS earthquake IDs already voiced
            "wildfire_last_error_at": None,
            "wildfire_last_error_message": None,
            "wildfire_announced_incidents": [],  # WFIGS incident IDs already voiced
            "alert_id_aliases": {},  # collapsed NWS alert id -> canonical active id
            "version": "1.0.4",  # State file version
        }

    def update_alert_id_aliases(self, state: Dict[str, Any], aliases: Dict[str, str]) -> None:
        """Merge NWS deduplication alias map (secondary alert id -> canonical id)."""
        if not aliases:
            return
        stored = state.get("alert_id_aliases")
        if not isinstance(stored, dict):
            stored = {}
        for old_id, new_id in aliases.items():
            stored[old_id] = new_id
            self._migrate_alert_id_references(state, old_id, new_id)
        state["alert_id_aliases"] = stored

    @staticmethod
    def _migrate_alert_id_references(state: Dict[str, Any], old_id: str, new_id: str) -> None:
        last = state.get("last_alerts")
        if isinstance(last, dict) and old_id in last and new_id not in last:
            last[new_id] = last.pop(old_id)
        for key in ("last_sayalert", "alertscript_alerts", "webhook_sent_alerts", "active_alerts"):
            items = state.get(key)
            if not isinstance(items, list):
                continue
            if old_id in items and new_id not in items:
                state[key] = [new_id if item == old_id else item for item in items]
            elif old_id in items:
                state[key] = [item for item in items if item != old_id]

    @staticmethod
    def resolve_alert_id(state: Dict[str, Any], alert_id: str) -> str:
        aliases = state.get("alert_id_aliases") or {}
        seen: set[str] = set()
        current = alert_id
        while isinstance(aliases, dict) and current in aliases and current not in seen:
            seen.add(current)
            current = aliases[current]
        return current

    def _is_still_active_id(
        self, state: Dict[str, Any], alert_id: str, current_ids: Set[str]
    ) -> bool:
        if alert_id in current_ids:
            return True
        canonical = self.resolve_alert_id(state, alert_id)
        return canonical in current_ids

    def prune_alert_tracking(self, state: Dict[str, Any], alert_id: str) -> None:
        """Remove per-alert tracking entries when an alert expires."""
        for key in ("last_sayalert", "alertscript_alerts", "webhook_sent_alerts"):
            items = state.get(key)
            if isinstance(items, list) and alert_id in items:
                state[key] = [item for item in items if item != alert_id]
        aliases = state.get("alert_id_aliases")
        if isinstance(aliases, dict):
            aliases.pop(alert_id, None)
            state["alert_id_aliases"] = {
                src: dst for src, dst in aliases.items() if src != alert_id and dst != alert_id
            }

    @staticmethod
    def _trim_tracking_list(state: Dict[str, Any], key: str) -> None:
        items = state.get(key)
        if isinstance(items, list) and len(items) > TRACKING_LIST_MAX:
            state[key] = items[-TRACKING_LIST_MAX:]

    def _bound_tracking_lists(self, state: Dict[str, Any]) -> None:
        for key in ("last_sayalert", "alertscript_alerts", "webhook_sent_alerts"):
            self._trim_tracking_list(state, key)
        cooldown = state.get("announcement_cooldown")
        if isinstance(cooldown, dict) and len(cooldown) > TRACKING_LIST_MAX:
            keys = list(cooldown.keys())[-TRACKING_LIST_MAX:]
            state["announcement_cooldown"] = {k: cooldown[k] for k in keys}

    def get_alert_ids(self, state: Dict[str, Any]) -> Set[str]:
        """
        Get set of all alert IDs from state.

        Args:
            state: Current state dictionary

        Returns:
            Set of alert IDs
        """
        return set(state.get("last_alerts", {}).keys())

    def add_alert(self, state: Dict[str, Any], alert: WeatherAlert) -> None:
        """
        Add alert to state.

        Args:
            state: Current state dictionary
            alert: Alert to add
        """
        self.upsert_alert(state, alert)

    @staticmethod
    def weather_alert_to_state_dict(
        alert: WeatherAlert, existing: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Serialize a WeatherAlert for persistence in ``last_alerts``."""
        data = alert.model_dump(mode="json")
        data["added_at"] = (
            existing.get("added_at")
            if isinstance(existing, dict) and existing.get("added_at")
            else datetime.now(timezone.utc).isoformat()
        )
        if isinstance(existing, dict) and existing.get("updated_at"):
            data["updated_at"] = existing["updated_at"]
        return data

    @staticmethod
    def _alert_snapshot_changed(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
        compare_keys = (
            "event",
            "headline",
            "description",
            "instruction",
            "severity",
            "urgency",
            "certainty",
            "status",
            "category",
            "area_desc",
            "county_codes",
            "geocode",
            "effective",
            "expires",
            "onset",
            "ends",
            "sent",
            "sender",
            "sender_name",
        )
        for key in compare_keys:
            if old.get(key) != new.get(key):
                return True
        return False

    def upsert_alert(self, state: Dict[str, Any], alert: WeatherAlert) -> bool:
        """
        Insert or refresh alert metadata in state.

        NWS may update or extend an alert while keeping the same ``id``. The dashboard
        and API read from ``last_alerts``; without this, ``expires`` / ``ends`` / text
        can stay stuck on the first snapshot.

        Returns:
            True when the stored snapshot changed (new alert or NWS update/extension).
        """
        last = state.get("last_alerts", {})
        existing = last.get(alert.id) if isinstance(last, dict) else None
        alert_data = self.weather_alert_to_state_dict(
            alert, existing if isinstance(existing, dict) else None
        )

        changed = not isinstance(existing, dict) or self._alert_snapshot_changed(
            existing, alert_data
        )
        if changed and isinstance(existing, dict):
            alert_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            logger.info(
                "Alert %s updated from NWS poll (%s): expires=%s ends=%s",
                alert.id,
                alert.event,
                alert_data.get("expires"),
                alert_data.get("ends"),
            )

        state["last_alerts"][alert.id] = alert_data
        logger.debug("Upserted alert %s in state (changed=%s)", alert.id, changed)
        return changed

    def remove_alert(self, state: Dict[str, Any], alert_id: str) -> None:
        """
        Remove alert from state.

        Args:
            state: Current state dictionary
            alert_id: ID of alert to remove
        """
        if alert_id in state.get("last_alerts", {}):
            del state["last_alerts"][alert_id]
            logger.debug(f"Removed alert {alert_id} from state")
        self.prune_alert_tracking(state, alert_id)

    def update_active_alerts(self, state: Dict[str, Any], active_alert_ids: List[str]) -> None:
        """
        Update the list of currently active alerts.

        Args:
            state: Current state dictionary
            active_alert_ids: List of currently active alert IDs
        """
        state["active_alerts"] = active_alert_ids
        logger.debug(f"Updated active alerts: {len(active_alert_ids)} alerts")

    def get_new_alerts(
        self, state: Dict[str, Any], current_alerts: List[WeatherAlert]
    ) -> List[WeatherAlert]:
        """
        Get alerts that are new (not in state).

        Args:
            state: Current state dictionary
            current_alerts: List of current alerts

        Returns:
            List of new alerts
        """
        existing_ids = self.get_alert_ids(state)
        new_alerts = [alert for alert in current_alerts if alert.id not in existing_ids]

        logger.debug(f"Found {len(new_alerts)} new alerts out of {len(current_alerts)} total")
        return new_alerts

    def get_expired_alerts(
        self, state: Dict[str, Any], current_alerts: List[WeatherAlert]
    ) -> List[str]:
        """
        Get alert IDs that have expired (not in current alerts).

        Args:
            state: Current state dictionary
            current_alerts: List of current alerts

        Returns:
            List of expired alert IDs
        """
        current_ids = {alert.id for alert in current_alerts}
        existing_ids = self.get_alert_ids(state)
        expired_ids = [
            eid for eid in existing_ids if not self._is_still_active_id(state, eid, current_ids)
        ]

        logger.debug(f"Found {len(expired_ids)} expired alerts")
        return expired_ids

    def detect_county_changes(
        self, state: Dict[str, Any], current_alerts: List[WeatherAlert]
    ) -> List[WeatherAlert]:
        """
        Detect alerts where county lists have changed.

        Args:
            state: Current state dictionary
            current_alerts: List of current alerts

        Returns:
            List of alerts with changed county lists
        """
        alerts_with_changes = []
        last_alerts = state.get("last_alerts", {})

        for alert in current_alerts:
            if alert.id not in last_alerts:
                continue  # Skip new alerts (handled separately)

            old_alert_data = last_alerts[alert.id]
            old_county_codes = set(old_alert_data.get("county_codes", []))
            new_county_codes = set(alert.county_codes)

            if old_county_codes != new_county_codes:
                logger.debug(
                    f"County list changed for alert {alert.id} ({alert.event}): "
                    f"old={old_county_codes}, new={new_county_codes}"
                )
                alerts_with_changes.append(alert)

        return alerts_with_changes

    def cleanup_old_alerts(self, state: Dict[str, Any], max_age_hours: int = 24) -> None:
        """
        Remove alerts older than specified age.

        Args:
            state: Current state dictionary
            max_age_hours: Maximum age in hours
        """
        if not state.get("last_alerts"):
            return

        cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        alerts_to_remove = []

        for alert_id, alert_data in state["last_alerts"].items():
            try:
                added_at = datetime.fromisoformat(alert_data["added_at"].replace("Z", "+00:00"))
                if added_at.timestamp() < cutoff_time:
                    alerts_to_remove.append(alert_id)
            except (KeyError, ValueError) as e:
                logger.warning(f"Invalid alert data for {alert_id}: {e}")
                alerts_to_remove.append(alert_id)

        for alert_id in alerts_to_remove:
            del state["last_alerts"][alert_id]

        if alerts_to_remove:
            logger.info(f"Cleaned up {len(alerts_to_remove)} old alerts")

    def mark_alert_announced(self, state: Dict[str, Any], alert_id: str) -> None:
        """
        Mark an alert as announced.

        Args:
            state: Current state dictionary
            alert_id: ID of alert to mark as announced
        """
        if alert_id not in state.get("last_sayalert", []):
            state.setdefault("last_sayalert", []).append(alert_id)
            self._trim_tracking_list(state, "last_sayalert")
            logger.debug(f"Marked alert {alert_id} as announced")

    def mark_alert_script_triggered(self, state: Dict[str, Any], alert_id: str) -> None:
        """
        Mark an alert as having triggered a script.

        Args:
            state: Current state dictionary
            alert_id: ID of alert to mark as script-triggered
        """
        if alert_id not in state.get("alertscript_alerts", []):
            state.setdefault("alertscript_alerts", []).append(alert_id)
            self._trim_tracking_list(state, "alertscript_alerts")
            logger.debug(f"Marked alert {alert_id} as script-triggered")

    def has_alert_webhook_sent(self, state: Dict[str, Any], alert_id: str) -> bool:
        """
        Check if a webhook has already been sent for an alert.

        Args:
            state: Current state dictionary
            alert_id: ID of alert to check

        Returns:
            True if webhook was already sent, False otherwise
        """
        return alert_id in state.get("webhook_sent_alerts", [])

    def mark_alert_webhook_sent(self, state: Dict[str, Any], alert_id: str) -> None:
        """
        Mark an alert as having had a webhook sent.

        Args:
            state: Current state dictionary
            alert_id: ID of alert to mark as webhook-sent
        """
        if alert_id not in state.get("webhook_sent_alerts", []):
            state.setdefault("webhook_sent_alerts", []).append(alert_id)
            self._trim_tracking_list(state, "webhook_sent_alerts")
            logger.debug(f"Marked alert {alert_id} as webhook-sent")

    def update_poll_time(self, state: Dict[str, Any]) -> None:
        """
        Update the last poll timestamp.

        Args:
            state: Current state dictionary
        """
        state["last_poll"] = datetime.now(timezone.utc).isoformat()
        logger.debug("Updated last poll time")

    def update_all_clear_time(self, state: Dict[str, Any]) -> None:
        """
        Update the last all-clear timestamp.

        Args:
            state: Current state dictionary
        """
        state["last_all_clear"] = datetime.now(timezone.utc).isoformat()
        logger.debug("Updated last all-clear time")

    def clear_state(self) -> None:
        """
        Clear all cached state (for cleanslate mode).
        """
        if self.state_file.exists():
            try:
                self.state_file.unlink()
                logger.info(f"Cleared state file: {self.state_file}")
            except Exception as e:
                logger.error(f"Failed to clear state file: {e}")
