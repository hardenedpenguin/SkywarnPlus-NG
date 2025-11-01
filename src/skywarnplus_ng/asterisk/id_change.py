"""
ID change management for SkywarnPlus-NG.

ID changes allow dynamically switching the node identifier audio file
between "normal" and "wx" (weather alert) mode based on active weather alerts.
"""

import logging
import shutil
import fnmatch
from pathlib import Path
from typing import List, Optional

from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)


class IDChangeError(Exception):
    """ID change error."""
    pass


class IDChangeManager:
    """Manages ID file switching based on weather alerts."""

    def __init__(
        self,
        enabled: bool,
        id_dir: Path,
        normal_id: str,
        wx_id: str,
        rpt_id: str,
        id_alerts: List[str],
        state_manager=None
    ):
        """
        Initialize ID change manager.

        Args:
            enabled: Whether ID changing is enabled
            id_dir: Directory where ID files are stored
            normal_id: Filename for normal mode ID (e.g., "NORMALID.ulaw")
            wx_id: Filename for WX mode ID (e.g., "WXID.ulaw")
            rpt_id: Filename that Asterisk uses (e.g., "RPTID.ulaw")
            id_alerts: List of alert events that trigger WX mode
            state_manager: Optional state manager to track current mode
        """
        self.enabled = enabled
        self.id_dir = Path(id_dir)
        self.normal_id = normal_id
        self.wx_id = wx_id
        self.rpt_id = rpt_id
        self.id_alerts = id_alerts
        self.state_manager = state_manager
        self.current_mode: Optional[str] = None

        # Ensure ID directory exists
        self.id_dir.mkdir(parents=True, exist_ok=True)

        # Load current mode from state on initialization
        if self.state_manager:
            try:
                state = self.state_manager.load_state()
                self.current_mode = state.get('id')
                if self.current_mode:
                    logger.debug(f"Loaded ID mode from state: {self.current_mode}")
            except Exception as e:
                logger.debug(f"Could not load ID mode from state: {e}")

        if not self.enabled:
            logger.info("ID changing is disabled")
        else:
            logger.info(f"ID change manager initialized (id_dir: {self.id_dir}, rpt_id: {self.rpt_id})")

    def _has_wx_alerts(self, alerts: List[WeatherAlert]) -> bool:
        """
        Check if any active alerts match the ID trigger list.

        Args:
            alerts: List of active alerts

        Returns:
            True if any alert matches ID trigger list
        """
        if not self.id_alerts:
            return False

        alert_events = {alert.event for alert in alerts}
        
        for alert_event in alert_events:
            for id_alert_pattern in self.id_alerts:
                if fnmatch.fnmatch(alert_event, id_alert_pattern):
                    logger.debug(f"Alert {alert_event} matches ID trigger pattern: {id_alert_pattern}")
                    return True
        
        return False

    def _copy_id_file(self, source_file: Path, dest_file: Path) -> bool:
        """
        Copy an ID file from source to destination.

        Args:
            source_file: Source ID file path
            dest_file: Destination ID file path

        Returns:
            True if copy was successful
        """
        try:
            if not source_file.exists():
                logger.error(f"Source ID file does not exist: {source_file}")
                return False

            shutil.copyfile(source_file, dest_file)
            logger.debug(f"Copied ID file: {source_file} -> {dest_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to copy ID file {source_file} to {dest_file}: {e}")
            return False

    def change_mode(self, mode: str) -> bool:
        """
        Change ID to specified mode.

        Args:
            mode: Mode to change to ('normal' or 'wx')

        Returns:
            True if change was successful
        """
        if not self.enabled:
            return False

        mode = mode.upper()
        if mode not in ['NORMAL', 'WX']:
            logger.error(f"Invalid ID mode: {mode} (must be 'NORMAL' or 'WX')")
            return False

        # If already in this mode, no need to change
        if self.current_mode == mode:
            logger.debug(f"ID already in {mode} mode, skipping")
            return False

        logger.info(f"Changing ID to {mode} mode")

        # Determine source file based on mode
        if mode == "NORMAL":
            source_filename = self.normal_id
        else:  # WX
            source_filename = self.wx_id

        source_file = self.id_dir / source_filename
        dest_file = self.id_dir / self.rpt_id

        if self._copy_id_file(source_file, dest_file):
            self.current_mode = mode
            logger.info(f"ID changed to {mode} mode (copied {source_filename} to {self.rpt_id})")
            
            # Update state if state manager is available
            if self.state_manager:
                try:
                    state = self.state_manager.load_state()
                    state['id'] = mode
                    self.state_manager.save_state(state)
                    logger.debug(f"Updated state with ID mode: {mode}")
                except Exception as e:
                    logger.warning(f"Failed to update state with ID mode: {e}")
            
            return True
        else:
            logger.error(f"Failed to change ID to {mode} mode")
            return False

    def update_id(self, alerts: List[WeatherAlert]) -> bool:
        """
        Update ID based on active alerts.

        Args:
            alerts: List of current active alerts

        Returns:
            True if ID was updated
        """
        if not self.enabled:
            return False

        # Determine if we should be in WX mode
        should_be_wx = self._has_wx_alerts(alerts)
        target_mode = "WX" if should_be_wx else "NORMAL"

        return self.change_mode(target_mode)

    def force_mode(self, mode: str) -> bool:
        """
        Force ID to a specific mode regardless of alerts.

        Args:
            mode: Mode to force ('normal' or 'wx')

        Returns:
            True if change was successful
        """
        return self.change_mode(mode)

