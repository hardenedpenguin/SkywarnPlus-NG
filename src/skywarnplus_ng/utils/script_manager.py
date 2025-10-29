"""
Script execution manager for SkywarnPlus-NG.
"""

import asyncio
import logging
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from ..core.config import ScriptConfig, ScriptsConfig
from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)


class ScriptExecutionError(Exception):
    """Script execution error."""

    pass


class ScriptManager:
    """Manages script execution for alerts."""

    def __init__(self, config: ScriptsConfig):
        """
        Initialize script manager.

        Args:
            config: Scripts configuration
        """
        self.config = config
        self._execution_history: List[Dict[str, Any]] = []

    async def execute_alert_script(self, alert: WeatherAlert) -> bool:
        """
        Execute script for a specific alert.

        Args:
            alert: Weather alert that triggered the script

        Returns:
            True if script executed successfully, False otherwise
        """
        if not self.config.enabled:
            logger.debug("Script execution disabled")
            return False

        # Find matching script for this alert type
        script_config = self._find_script_for_alert(alert)
        if not script_config:
            logger.debug(f"No script configured for alert type: {alert.event}")
            return False

        if not script_config.enabled:
            logger.debug(f"Script for {alert.event} is disabled")
            return False

        return await self._execute_script(script_config, alert, "alert")

    async def execute_all_clear_script(self) -> bool:
        """
        Execute all-clear script.

        Returns:
            True if script executed successfully, False otherwise
        """
        if not self.config.enabled:
            logger.debug("Script execution disabled")
            return False

        if not self.config.all_clear_script:
            logger.debug("No all-clear script configured")
            return False

        if not self.config.all_clear_script.enabled:
            logger.debug("All-clear script is disabled")
            return False

        return await self._execute_script(self.config.all_clear_script, None, "all_clear")

    def _find_script_for_alert(self, alert: WeatherAlert) -> Optional[ScriptConfig]:
        """
        Find script configuration for an alert.

        Args:
            alert: Weather alert

        Returns:
            Script configuration or None if not found
        """
        # Try exact match first
        if alert.event in self.config.alert_scripts:
            return self.config.alert_scripts[alert.event]

        # Try pattern matching (simple wildcard support)
        for pattern, script_config in self.config.alert_scripts.items():
            if self._matches_pattern(alert.event, pattern):
                return script_config

        return None

    def _matches_pattern(self, text: str, pattern: str) -> bool:
        """
        Check if text matches a pattern (supports simple wildcards).

        Args:
            text: Text to match
            pattern: Pattern to match against

        Returns:
            True if text matches pattern
        """
        import fnmatch
        return fnmatch.fnmatch(text, pattern)

    async def _execute_script(self, script_config: ScriptConfig, alert: Optional[WeatherAlert], script_type: str) -> bool:
        """
        Execute a script with the given configuration.

        Args:
            script_config: Script configuration
            alert: Weather alert (None for all-clear scripts)
            script_type: Type of script ("alert" or "all_clear")

        Returns:
            True if script executed successfully, False otherwise
        """
        try:
            logger.info(f"Executing {script_type} script: {script_config.command}")

            # Prepare environment variables
            env = self._prepare_environment(script_config, alert)

            # Prepare working directory
            working_dir = script_config.working_dir or Path.cwd()

            # Execute the script
            process = await asyncio.create_subprocess_exec(
                script_config.command,
                *script_config.args,
                env=env,
                cwd=working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=script_config.timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"Script timed out after {script_config.timeout}s: {script_config.command}")
                process.kill()
                await process.wait()
                self._record_execution(script_config, alert, script_type, False, "Timeout", "")
                return False

            # Decode output
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')

            # Check return code
            success = process.returncode == 0

            if success:
                logger.info(f"Script executed successfully: {script_config.command}")
                if stdout_str:
                    logger.debug(f"Script output: {stdout_str}")
            else:
                logger.error(f"Script failed with code {process.returncode}: {script_config.command}")
                if stderr_str:
                    logger.error(f"Script error: {stderr_str}")

            # Record execution
            self._record_execution(
                script_config, alert, script_type, success,
                f"Exit code: {process.returncode}",
                stdout_str + stderr_str
            )

            return success

        except FileNotFoundError:
            logger.error(f"Script not found: {script_config.command}")
            self._record_execution(script_config, alert, script_type, False, "File not found", "")
            return False
        except PermissionError:
            logger.error(f"Script not executable: {script_config.command}")
            self._record_execution(script_config, alert, script_type, False, "Permission denied", "")
            return False
        except Exception as e:
            logger.error(f"Error executing script {script_config.command}: {e}")
            self._record_execution(script_config, alert, script_type, False, str(e), "")
            return False

    def _prepare_environment(self, script_config: ScriptConfig, alert: Optional[WeatherAlert]) -> Dict[str, str]:
        """
        Prepare environment variables for script execution.

        Args:
            script_config: Script configuration
            alert: Weather alert (None for all-clear scripts)

        Returns:
            Environment variables dictionary
        """
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(Path.home()),
        }

        # Add configured environment variables
        env.update(script_config.env_vars)

        # Add alert-specific environment variables
        if alert:
            env.update({
                "ALERT_ID": alert.id,
                "ALERT_EVENT": alert.event,
                "ALERT_SEVERITY": alert.severity.value,
                "ALERT_URGENCY": alert.urgency.value,
                "ALERT_CERTAINTY": alert.certainty.value,
                "ALERT_AREA": alert.area_desc,
                "ALERT_COUNTIES": ",".join(alert.county_codes),
                "ALERT_EFFECTIVE": alert.effective.isoformat(),
                "ALERT_EXPIRES": alert.expires.isoformat(),
                "ALERT_SENDER": alert.sender,
            })

            if alert.onset:
                env["ALERT_ONSET"] = alert.onset.isoformat()
            if alert.ends:
                env["ALERT_ENDS"] = alert.ends.isoformat()

        # Add timestamp
        env["TIMESTAMP"] = datetime.now(timezone.utc).isoformat()

        return env

    def _record_execution(self, script_config: ScriptConfig, alert: Optional[WeatherAlert], 
                         script_type: str, success: bool, error_msg: str, output: str) -> None:
        """
        Record script execution in history.

        Args:
            script_config: Script configuration
            alert: Weather alert (None for all-clear scripts)
            script_type: Type of script
            success: Whether script executed successfully
            error_msg: Error message if failed
            output: Script output
        """
        execution_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "script_type": script_type,
            "command": script_config.command,
            "args": script_config.args,
            "success": success,
            "error_msg": error_msg,
            "output": output[:1000],  # Limit output length
            "alert_id": alert.id if alert else None,
            "alert_event": alert.event if alert else None,
        }

        self._execution_history.append(execution_record)

        # Keep only last 100 executions
        if len(self._execution_history) > 100:
            self._execution_history = self._execution_history[-100:]

    def get_execution_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get script execution history.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of execution records
        """
        return self._execution_history[-limit:]

    def get_script_status(self) -> Dict[str, Any]:
        """
        Get script manager status.

        Returns:
            Status dictionary
        """
        return {
            "enabled": self.config.enabled,
            "alert_scripts_count": len(self.config.alert_scripts),
            "all_clear_script_configured": self.config.all_clear_script is not None,
            "total_executions": len(self._execution_history),
            "recent_successes": len([e for e in self._execution_history[-10:] if e["success"]]),
            "recent_failures": len([e for e in self._execution_history[-10:] if not e["success"]]),
        }
