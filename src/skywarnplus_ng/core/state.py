"""
State management for SkywarnPlus-NG.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from collections import OrderedDict

from .models import WeatherAlert

logger = logging.getLogger(__name__)


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
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # Ensure required keys exist
            for key, default_value in self._get_default_state().items():
                if key not in state:
                    state[key] = default_value
                    logger.debug(f"Added missing state key: {key}")

            # Convert last_alerts back to OrderedDict to preserve order
            if 'last_alerts' in state and isinstance(state['last_alerts'], list):
                state['last_alerts'] = OrderedDict(state['last_alerts'])
            elif 'last_alerts' not in state:
                state['last_alerts'] = OrderedDict()

            logger.debug(f"Loaded state from {self.state_file}")
            return state

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load state from {self.state_file}: {e}")
            logger.info("Using default state")
            return self._get_default_state()

    def save_state(self, state: Dict[str, Any]) -> None:
        """
        Save state to file.

        Args:
            state: State dictionary to save
        """
        try:
            # Create a copy for serialization
            state_copy = state.copy()
            
            # Convert OrderedDict to list for JSON serialization
            if 'last_alerts' in state_copy and isinstance(state_copy['last_alerts'], OrderedDict):
                state_copy['last_alerts'] = list(state_copy['last_alerts'].items())
            
            # Convert sets to lists for JSON serialization
            for key, value in state_copy.items():
                if isinstance(value, set):
                    state_copy[key] = list(value)

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state_copy, f, indent=2, ensure_ascii=False, default=str)
            
            logger.debug(f"Saved state to {self.state_file}")

        except (IOError, TypeError) as e:
            logger.error(f"Failed to save state to {self.state_file}: {e}")

    def _get_default_state(self) -> Dict[str, Any]:
        """Get default state values."""
        return {
            'last_alerts': OrderedDict(),  # Alert ID -> Alert data
            'active_alerts': [],  # Currently active alert IDs
            'last_sayalert': [],  # Alerts that were announced
            'alertscript_alerts': [],  # Alerts that triggered scripts
            'last_poll': None,  # Last poll timestamp
            'last_all_clear': None,  # Last all-clear timestamp
            'ct': None,  # Current courtesy tone mode ('normal' or 'wx')
            'id': None,  # Current identifier
            'version': '1.0.0',  # State file version
        }

    def get_alert_ids(self, state: Dict[str, Any]) -> Set[str]:
        """
        Get set of all alert IDs from state.

        Args:
            state: Current state dictionary

        Returns:
            Set of alert IDs
        """
        return set(state.get('last_alerts', {}).keys())

    def add_alert(self, state: Dict[str, Any], alert: WeatherAlert) -> None:
        """
        Add alert to state.

        Args:
            state: Current state dictionary
            alert: Alert to add
        """
        alert_data = {
            'id': alert.id,
            'event': alert.event,
            'headline': alert.headline,
            'description': alert.description,
            'instruction': alert.instruction,
            'severity': alert.severity.value,
            'urgency': alert.urgency.value,
            'certainty': alert.certainty.value,
            'area_desc': alert.area_desc,
            'county_codes': alert.county_codes,
            'effective': alert.effective.isoformat(),
            'expires': alert.expires.isoformat(),
            'onset': alert.onset.isoformat() if alert.onset else None,
            'ends': alert.ends.isoformat() if alert.ends else None,
            'added_at': datetime.now(timezone.utc).isoformat(),
        }
        
        state['last_alerts'][alert.id] = alert_data
        logger.debug(f"Added alert {alert.id} to state")

    def remove_alert(self, state: Dict[str, Any], alert_id: str) -> None:
        """
        Remove alert from state.

        Args:
            state: Current state dictionary
            alert_id: ID of alert to remove
        """
        if alert_id in state.get('last_alerts', {}):
            del state['last_alerts'][alert_id]
            logger.debug(f"Removed alert {alert_id} from state")

    def update_active_alerts(self, state: Dict[str, Any], active_alert_ids: List[str]) -> None:
        """
        Update the list of currently active alerts.

        Args:
            state: Current state dictionary
            active_alert_ids: List of currently active alert IDs
        """
        state['active_alerts'] = active_alert_ids
        logger.debug(f"Updated active alerts: {len(active_alert_ids)} alerts")

    def get_new_alerts(self, state: Dict[str, Any], current_alerts: List[WeatherAlert]) -> List[WeatherAlert]:
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

    def get_expired_alerts(self, state: Dict[str, Any], current_alerts: List[WeatherAlert]) -> List[str]:
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
        expired_ids = list(existing_ids - current_ids)
        
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
        last_alerts = state.get('last_alerts', {})
        
        for alert in current_alerts:
            if alert.id not in last_alerts:
                continue  # Skip new alerts (handled separately)
            
            old_alert_data = last_alerts[alert.id]
            old_county_codes = set(old_alert_data.get('county_codes', []))
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
        if not state.get('last_alerts'):
            return

        cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        alerts_to_remove = []

        for alert_id, alert_data in state['last_alerts'].items():
            try:
                added_at = datetime.fromisoformat(alert_data['added_at'].replace('Z', '+00:00'))
                if added_at.timestamp() < cutoff_time:
                    alerts_to_remove.append(alert_id)
            except (KeyError, ValueError) as e:
                logger.warning(f"Invalid alert data for {alert_id}: {e}")
                alerts_to_remove.append(alert_id)

        for alert_id in alerts_to_remove:
            del state['last_alerts'][alert_id]

        if alerts_to_remove:
            logger.info(f"Cleaned up {len(alerts_to_remove)} old alerts")

    def mark_alert_announced(self, state: Dict[str, Any], alert_id: str) -> None:
        """
        Mark an alert as announced.

        Args:
            state: Current state dictionary
            alert_id: ID of alert to mark as announced
        """
        if alert_id not in state.get('last_sayalert', []):
            state['last_sayalert'].append(alert_id)
            logger.debug(f"Marked alert {alert_id} as announced")

    def mark_alert_script_triggered(self, state: Dict[str, Any], alert_id: str) -> None:
        """
        Mark an alert as having triggered a script.

        Args:
            state: Current state dictionary
            alert_id: ID of alert to mark as script-triggered
        """
        if alert_id not in state.get('alertscript_alerts', []):
            state['alertscript_alerts'].append(alert_id)
            logger.debug(f"Marked alert {alert_id} as script-triggered")

    def update_poll_time(self, state: Dict[str, Any]) -> None:
        """
        Update the last poll timestamp.

        Args:
            state: Current state dictionary
        """
        state['last_poll'] = datetime.now(timezone.utc).isoformat()
        logger.debug("Updated last poll time")

    def update_all_clear_time(self, state: Dict[str, Any]) -> None:
        """
        Update the last all-clear timestamp.

        Args:
            state: Current state dictionary
        """
        state['last_all_clear'] = datetime.now(timezone.utc).isoformat()
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
