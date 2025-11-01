"""
Courtesy tone management for SkywarnPlus-NG.

Courtesy tones are audio files that play after transmissions. This module
manages dynamically switching between "normal" and "wx" (weather alert) mode
tones based on active weather alerts.
"""

import logging
import shutil
import fnmatch
from pathlib import Path
from typing import List, Dict, Optional

from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)


class CourtesyToneError(Exception):
    """Courtesy tone error."""
    pass


class CourtesyToneManager:
    """Manages courtesy tone switching based on weather alerts."""

    def __init__(
        self,
        enabled: bool,
        tone_dir: Path,
        tones_config: Dict[str, Dict[str, str]],
        ct_alerts: List[str],
        state_manager=None
    ):
        """
        Initialize courtesy tone manager.

        Args:
            enabled: Whether courtesy tone switching is enabled
            tone_dir: Directory where tone files are stored
            tones_config: Dictionary mapping CT keys to Normal/WX tone files
                         Example: {"ct1": {"Normal": "Boop.ulaw", "WX": "Stardust.ulaw"}}
            ct_alerts: List of alert events that trigger WX mode
            state_manager: Optional state manager to track current mode
        """
        self.enabled = enabled
        self.tone_dir = Path(tone_dir)
        self.tones_config = tones_config
        self.ct_alerts = ct_alerts
        self.state_manager = state_manager
        self.current_mode: Optional[str] = None

        # Ensure tone directory exists
        self.tone_dir.mkdir(parents=True, exist_ok=True)

        # Load current mode from state on initialization
        if self.state_manager:
            try:
                state = self.state_manager.load_state()
                self.current_mode = state.get('ct')
                if self.current_mode:
                    logger.debug(f"Loaded CT mode from state: {self.current_mode}")
            except Exception as e:
                logger.debug(f"Could not load CT mode from state: {e}")

        if not self.enabled:
            logger.info("Courtesy tone switching is disabled")
        else:
            logger.info(f"Courtesy tone manager initialized (tone_dir: {self.tone_dir})")

    def _has_wx_alerts(self, alerts: List[WeatherAlert]) -> bool:
        """
        Check if any active alerts match the CT trigger list.

        Args:
            alerts: List of active alerts

        Returns:
            True if any alert matches CT trigger list
        """
        if not self.ct_alerts:
            return False

        alert_events = {alert.event for alert in alerts}
        
        for alert_event in alert_events:
            for ct_alert_pattern in self.ct_alerts:
                if fnmatch.fnmatch(alert_event, ct_alert_pattern):
                    logger.debug(f"Alert {alert_event} matches CT trigger pattern: {ct_alert_pattern}")
                    return True
        
        return False

    def _copy_tone_file(self, source_file: Path, dest_file: Path) -> bool:
        """
        Copy a tone file from source to destination.

        Args:
            source_file: Source tone file path
            dest_file: Destination tone file path

        Returns:
            True if copy was successful
        """
        try:
            if not source_file.exists():
                logger.error(f"Source tone file does not exist: {source_file}")
                return False

            shutil.copyfile(source_file, dest_file)
            logger.debug(f"Copied tone file: {source_file} -> {dest_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to copy tone file {source_file} to {dest_file}: {e}")
            return False

    def change_mode(self, mode: str) -> bool:
        """
        Change courtesy tones to specified mode.

        Args:
            mode: Mode to change to ('normal' or 'wx')

        Returns:
            True if any changes were made
        """
        if not self.enabled:
            return False

        mode = mode.lower()
        if mode not in ['normal', 'wx']:
            logger.error(f"Invalid courtesy tone mode: {mode} (must be 'normal' or 'wx')")
            return False

        # If already in this mode, no need to change
        if self.current_mode == mode:
            logger.debug(f"Courtesy tones already in {mode} mode, skipping")
            return False

        logger.info(f"Changing courtesy tones to {mode} mode")

        changed = False
        mode_key = "Normal" if mode == "normal" else "WX"

        for ct_key, tone_settings in self.tones_config.items():
            # Get target tone file for this mode
            target_tone_file = tone_settings.get(mode_key)
            
            if not target_tone_file:
                logger.warning(f"No {mode_key} tone configured for {ct_key}, skipping")
                continue

            # Source file: tone_dir/target_tone_file
            source_file = self.tone_dir / target_tone_file
            
            # Destination file: tone_dir/ct_key.ulaw (or whatever extension source has)
            # Preserve extension from source file
            dest_ext = source_file.suffix if source_file.suffix else '.ulaw'
            dest_file = self.tone_dir / f"{ct_key}{dest_ext}"

            if self._copy_tone_file(source_file, dest_file):
                logger.info(f"Updated {ct_key} to {mode} mode with tone {target_tone_file}")
                changed = True
            else:
                logger.warning(f"Failed to update {ct_key} to {mode} mode")

        if changed:
            self.current_mode = mode
            logger.info(f"Courtesy tones changed to {mode} mode")
            
            # Update state if state manager is available
            if self.state_manager:
                try:
                    state = self.state_manager.load_state()
                    state['ct'] = mode
                    self.state_manager.save_state(state)
                except Exception as e:
                    logger.warning(f"Failed to update state with CT mode: {e}")
        else:
            logger.debug(f"No courtesy tone changes made (already in {mode} mode or files missing)")

        return changed

    def update_courtesy_tones(self, alerts: List[WeatherAlert]) -> bool:
        """
        Update courtesy tones based on active alerts.

        Args:
            alerts: List of current active alerts

        Returns:
            True if tones were updated
        """
        if not self.enabled:
            return False

        # Determine if we should be in WX mode
        should_be_wx = self._has_wx_alerts(alerts)
        target_mode = "wx" if should_be_wx else "normal"

        return self.change_mode(target_mode)

    def force_mode(self, mode: str) -> bool:
        """
        Force courtesy tones to a specific mode regardless of alerts.

        Args:
            mode: Mode to force ('normal' or 'wx')

        Returns:
            True if change was successful
        """
        return self.change_mode(mode)

