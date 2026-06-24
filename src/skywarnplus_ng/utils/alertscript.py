"""
Enhanced AlertScript manager for SkywarnPlus-NG.

Supports mapping-based alert-to-command execution with advanced features:
- ClearCommands: Execute when alerts clear
- ActiveCommands/InactiveCommands: Transition-based commands
- {alert_title} placeholder substitution (values are shell-quoted for BASH)
- Multi-node DTMF support (DTMF strings validated after substitution)
- Match: ALL vs Match: ANY logic
"""

import asyncio
import fnmatch
import logging
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..core.models import (
    AlertCategory,
    AlertCertainty,
    AlertSeverity,
    AlertStatus,
    AlertUrgency,
    WeatherAlert,
)

# Allowed characters for Asterisk `rpt fun` DTMF argument (digits + DTMF letters).
_DTMF_COMMAND_PATTERN = re.compile(r"^[0-9*#A-Da-d]{1,128}$")

logger = logging.getLogger(__name__)


class AlertScriptMapping:
    """Represents an AlertScript mapping configuration."""

    def __init__(
        self,
        script_type: str,  # "BASH" or "DTMF"
        commands: List[str],
        triggers: List[str],
        match_type: str = "ANY",  # "ANY" or "ALL"
        nodes: Optional[List[int]] = None,
        clear_commands: Optional[List[str]] = None,
    ):
        self.script_type = script_type.upper()
        self.commands = commands
        self.triggers = triggers
        self.match_type = match_type.upper()
        self.nodes = nodes or []
        self.clear_commands = clear_commands or []

    def matches_alert(self, alert_event: str) -> bool:
        """
        Check if an alert event matches this mapping's triggers.

        Args:
            alert_event: Alert event name

        Returns:
            True if alert matches
        """
        for trigger in self.triggers:
            if fnmatch.fnmatch(alert_event, trigger):
                return True
        return False

    def matches_all_triggers(self, alert_events: Set[str]) -> bool:
        """
        Check if all triggers match (for Match: ALL).

        Args:
            alert_events: Set of active alert event names

        Returns:
            True if all triggers match
        """
        matched_triggers = set()
        for alert_event in alert_events:
            for trigger in self.triggers:
                if fnmatch.fnmatch(alert_event, trigger):
                    matched_triggers.add(trigger)
        return len(matched_triggers) == len(self.triggers)

    def matches_any_trigger(self, alert_events: Set[str]) -> bool:
        """
        Check if any trigger matches (for Match: ANY).

        Args:
            alert_events: Set of active alert event names

        Returns:
            True if any trigger matches
        """
        for alert_event in alert_events:
            if self.matches_alert(alert_event):
                return True
        return False


class AlertScriptManager:
    """Enhanced AlertScript manager with mapping-based execution."""

    def __init__(
        self,
        enabled: bool,
        mappings: List[Dict[str, Any]],
        active_commands: Optional[List[Dict[str, Any]]] = None,
        inactive_commands: Optional[List[Dict[str, Any]]] = None,
        asterisk_path: Path = Path("/usr/sbin/asterisk"),
    ):
        """
        Initialize AlertScript manager.

        Args:
            enabled: Whether AlertScript is enabled
            mappings: List of mapping configurations
            active_commands: Commands to run when alerts go from 0 to non-zero
            inactive_commands: Commands to run when alerts go from non-zero to 0
            asterisk_path: Path to Asterisk binary
        """
        self.enabled = enabled
        self.asterisk_path = asterisk_path
        self.processed_alerts: Set[str] = set()  # Track processed alert events

        # Parse mappings
        self.mappings: List[AlertScriptMapping] = []
        for mapping_config in mappings:
            try:
                mapping = AlertScriptMapping(
                    script_type=mapping_config.get("Type", "BASH"),
                    commands=mapping_config.get("Commands", []),
                    triggers=mapping_config.get("Triggers", []),
                    match_type=mapping_config.get("Match", "ANY"),
                    nodes=mapping_config.get("Nodes", []),
                    clear_commands=mapping_config.get("ClearCommands", []),
                )
                self.mappings.append(mapping)
            except Exception as e:
                logger.error(f"Failed to parse AlertScript mapping: {e}")

        # Parse active/inactive commands
        self.active_commands: List[AlertScriptMapping] = []
        self.inactive_commands: List[AlertScriptMapping] = []

        if active_commands:
            for cmd_config in active_commands:
                try:
                    mapping = AlertScriptMapping(
                        script_type=cmd_config.get("Type", "BASH"),
                        commands=cmd_config.get("Commands", []),
                        triggers=[],  # Not used for active/inactive
                        match_type="ANY",
                        nodes=cmd_config.get("Nodes", []),
                    )
                    self.active_commands.append(mapping)
                except Exception as e:
                    logger.error(f"Failed to parse ActiveCommand: {e}")

        if inactive_commands:
            for cmd_config in inactive_commands:
                try:
                    mapping = AlertScriptMapping(
                        script_type=cmd_config.get("Type", "BASH"),
                        commands=cmd_config.get("Commands", []),
                        triggers=[],  # Not used for active/inactive
                        match_type="ANY",
                        nodes=cmd_config.get("Nodes", []),
                    )
                    self.inactive_commands.append(mapping)
                except Exception as e:
                    logger.error(f"Failed to parse InactiveCommand: {e}")

        if self.enabled:
            logger.info(f"AlertScript manager initialized with {len(self.mappings)} mappings")

    @staticmethod
    def _substitute_placeholders(
        command: str, alert: Optional[WeatherAlert] = None, *, shell_quoting: bool = True
    ) -> str:
        """
        Substitute placeholders in command string.

        For BASH, values are passed through :func:`shlex.quote` so NWS text cannot
        inject shell syntax. For DTMF, values are inserted raw; the full string is
        then validated with :meth:`_dtmf_command_is_safe`.

        Args:
            command: Command string with placeholders
            alert: Optional alert for placeholder substitution
            shell_quoting: If True (BASH), quote substituted values

        Returns:
            Command string with placeholders replaced
        """
        if alert:
            q = shlex.quote if shell_quoting else str
            command = command.replace("{alert_title}", q(alert.event))
            command = command.replace("{alert_id}", q(alert.id))
            command = command.replace("{alert_event}", q(alert.event))
            command = command.replace("{alert_area}", q(alert.area_desc))
            command = command.replace("{alert_counties}", q(",".join(alert.county_codes)))
        return command

    @staticmethod
    def _dtmf_command_is_safe(cmd: str) -> bool:
        """Reject DTMF strings that are not safe to pass to Asterisk ``rpt fun``."""
        s = cmd.strip()
        if not s:
            return False
        return bool(_DTMF_COMMAND_PATTERN.fullmatch(s))

    async def _execute_bash_command(self, command: str) -> bool:
        """
        Execute a bash command via ``/bin/bash -c`` (no shell parsing of argv[0]).

        Args:
            command: Full command string after placeholder substitution

        Returns:
            True if command executed successfully
        """
        try:
            logger.info(f"AlertScript: Executing BASH command: {command}")
            process = await asyncio.create_subprocess_exec(
                "/bin/bash",
                "-c",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            except asyncio.TimeoutError:
                logger.warning("AlertScript BASH command timed out after 30s: %s", command)
                process.kill()
                await process.wait()
                return False

            if process.returncode == 0:
                logger.debug(f"BASH command succeeded: {command}")
                return True
            else:
                logger.warning(f"BASH command failed (code {process.returncode}): {command}")
                if stderr:
                    logger.warning(f"Error output: {stderr.decode('utf-8', errors='replace')}")
                return False
        except Exception as e:
            logger.error(f"Error executing BASH command '{command}': {e}")
            return False

    async def _execute_dtmf_command(self, node: int, command: str) -> bool:
        """
        Execute a DTMF command on a node.

        Args:
            node: Node number
            command: DTMF command string

        Returns:
            True if command executed successfully
        """
        try:
            if not self._dtmf_command_is_safe(command):
                logger.warning(
                    "AlertScript: Skipping unsafe or invalid DTMF command for node %s: %r",
                    node,
                    command,
                )
                return False

            dtmf_cmd = f"rpt fun {node} {command}"
            logger.info(f"AlertScript: Executing DTMF command on node {node}: {command}")

            process = await asyncio.create_subprocess_exec(
                "sudo",
                "-n",
                "-u",
                "asterisk",
                str(self.asterisk_path),
                "-rx",
                dtmf_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.debug(f"DTMF command succeeded on node {node}: {command}")
                return True
            else:
                logger.warning(
                    f"DTMF command failed on node {node} (code {process.returncode}): {command}"
                )
                return False
        except Exception as e:
            logger.error(f"Error executing DTMF command on node {node} '{command}': {e}")
            return False

    async def _execute_mapping_commands(
        self, mapping: AlertScriptMapping, alerts: List[WeatherAlert], is_clear: bool = False
    ) -> None:
        """
        Execute commands for a mapping.

        Args:
            mapping: AlertScript mapping
            alerts: List of alerts that matched
            is_clear: Whether these are clear commands
        """
        commands = mapping.clear_commands if is_clear else mapping.commands
        # Run once with no alert context when the list is empty (e.g. InactiveCommands).
        alert_iter: List[Optional[WeatherAlert]] = list(alerts) if alerts else [None]

        for command_template in commands:
            for alert in alert_iter:
                if mapping.script_type == "BASH":
                    command = self._substitute_placeholders(
                        command_template, alert, shell_quoting=True
                    )
                    await self._execute_bash_command(command)
                elif mapping.script_type == "DTMF":
                    command = self._substitute_placeholders(
                        command_template, alert, shell_quoting=False
                    )
                    for node in mapping.nodes:
                        await self._execute_dtmf_command(node, command)

    async def process_alerts(
        self, current_alerts: List[WeatherAlert], previous_alert_events: Optional[Set[str]] = None
    ) -> Set[str]:
        """
        Process alerts and execute matching AlertScript mappings.

        Args:
            current_alerts: Current list of active alerts
            previous_alert_events: Set of alert events from previous poll (for transitions)

        Returns:
            Set of processed alert event names
        """
        if not self.enabled:
            return set()

        current_alert_events = {alert.event for alert in current_alerts}
        previous_alert_events = previous_alert_events or set()

        # Handle ActiveCommands (0 -> non-zero transition)
        if not previous_alert_events and current_alert_events:
            logger.info("AlertScript: Active alerts transition (0 -> non-zero)")
            for mapping in self.active_commands:
                # Use first alert for placeholder substitution
                await self._execute_mapping_commands(
                    mapping, current_alerts[:1] if current_alerts else []
                )

        # Handle InactiveCommands (non-zero -> 0 transition)
        if previous_alert_events and not current_alert_events:
            logger.info("AlertScript: Active alerts transition (non-zero -> 0)")
            for mapping in self.inactive_commands:
                await self._execute_mapping_commands(mapping, [])

        # Process mappings for new alerts
        new_alert_events = current_alert_events - self.processed_alerts
        matched_alerts_by_mapping: Dict[AlertScriptMapping, List[WeatherAlert]] = {}

        for mapping in self.mappings:
            # Check if mapping matches based on match type
            if mapping.match_type == "ALL":
                if mapping.matches_all_triggers(current_alert_events):
                    # Get all alerts that match any trigger
                    matching_alerts = [
                        alert for alert in current_alerts if mapping.matches_alert(alert.event)
                    ]
                    if matching_alerts:
                        matched_alerts_by_mapping[mapping] = matching_alerts
            else:  # Match: ANY
                matching_alerts = [
                    alert
                    for alert in current_alerts
                    if mapping.matches_alert(alert.event) and alert.event in new_alert_events
                ]
                if matching_alerts:
                    matched_alerts_by_mapping[mapping] = matching_alerts

        # Execute commands for matched mappings
        for mapping, alerts in matched_alerts_by_mapping.items():
            logger.debug(f"AlertScript: Executing mapping for alerts: {[a.event for a in alerts]}")
            await self._execute_mapping_commands(mapping, alerts)
            # Track processed alerts
            for alert in alerts:
                self.processed_alerts.add(alert.event)

        # Process clear commands for mappings
        cleared_alert_events = self.processed_alerts - current_alert_events
        if cleared_alert_events:
            logger.debug(f"AlertScript: Processing clear commands for: {cleared_alert_events}")

            for mapping in self.mappings:
                if not mapping.clear_commands:
                    continue

                # Check if mapping should trigger clear commands
                should_clear = False
                if mapping.match_type == "ALL":
                    # For ALL, check if all triggers are cleared
                    should_clear = not any(
                        mapping.matches_alert(event) for event in current_alert_events
                    ) and any(mapping.matches_alert(event) for event in cleared_alert_events)
                else:  # Match: ANY
                    # For ANY, check if any trigger is cleared
                    should_clear = any(
                        mapping.matches_alert(event) for event in cleared_alert_events
                    )

                if should_clear:
                    # Use alerts from processed set for placeholder substitution
                    cleared_alerts = [
                        alert
                        for alert in current_alerts
                        if alert.event in cleared_alert_events
                        and mapping.matches_alert(alert.event)
                    ]
                    if not cleared_alerts:
                        _now = datetime.now(timezone.utc)
                        _ev = next(iter(cleared_alert_events))
                        dummy_alert = WeatherAlert(
                            id="cleared",
                            event=_ev,
                            description="",
                            headline=None,
                            instruction=None,
                            severity=AlertSeverity.UNKNOWN,
                            urgency=AlertUrgency.UNKNOWN,
                            certainty=AlertCertainty.UNKNOWN,
                            status=AlertStatus.ACTUAL,
                            category=AlertCategory.OTHER,
                            sent=_now,
                            effective=_now,
                            onset=None,
                            expires=_now,
                            ends=None,
                            area_desc="",
                            geocode=[],
                            county_codes=[],
                            sender="",
                            sender_name="",
                        )
                        cleared_alerts = [dummy_alert]

                    await self._execute_mapping_commands(mapping, cleared_alerts, is_clear=True)
                    # Remove from processed set
                    for event in cleared_alert_events:
                        if mapping.matches_alert(event):
                            self.processed_alerts.discard(event)

        return current_alert_events
