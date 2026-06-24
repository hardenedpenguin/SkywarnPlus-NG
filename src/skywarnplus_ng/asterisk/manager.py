"""
Asterisk manager for SkywarnPlus-NG on ASL3.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from ..core.config import AsteriskConfig

logger = logging.getLogger(__name__)


class AsteriskError(Exception):
    """Asterisk manager error."""

    pass


class AsteriskManager:
    """Manages Asterisk integration for radio repeater control."""

    def __init__(self, config: AsteriskConfig):
        """
        Initialize Asterisk manager.

        Args:
            config: Asterisk configuration
        """
        self.config = config
        self.asterisk_path = Path("/usr/sbin/asterisk")
        self._validate_asterisk()

    def _validate_asterisk(self) -> None:
        """Validate that Asterisk is available."""
        if not self.asterisk_path.exists():
            raise AsteriskError(f"Asterisk not found at {self.asterisk_path}")

        if not self.asterisk_path.is_file():
            raise AsteriskError(f"Asterisk path is not a file: {self.asterisk_path}")

        if not self.asterisk_path.stat().st_mode & 0o111:  # Check if executable
            raise AsteriskError(f"Asterisk is not executable: {self.asterisk_path}")

        logger.info(f"Asterisk found at {self.asterisk_path}")

    async def _run_asterisk_command(
        self,
        command: str,
        *,
        cwd: Optional[Path] = None,
        wait: bool = True,
    ) -> Tuple[int, str, str]:
        """
        Run an Asterisk CLI command.

        Args:
            command: Asterisk CLI command to run
            cwd: Working directory for the subprocess
            wait: When false, start the command and return without blocking

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        try:
            logger.debug(f"Running Asterisk command: {command}")

            work_dir = str(cwd) if cwd else "/var/lib/skywarnplus-ng"

            try:
                import pwd

                asterisk_uid = pwd.getpwnam("asterisk").pw_uid
                is_asterisk_user = os.geteuid() == asterisk_uid
            except (ImportError, KeyError):
                is_asterisk_user = os.getenv("USER") == "asterisk"

            if is_asterisk_user:
                command_args = [str(self.asterisk_path), "-rx", command]
                logger.debug(f"Running command directly as asterisk user: {command_args}")
            else:
                command_args = [
                    "sudo",
                    "-n",
                    "-u",
                    "asterisk",
                    str(self.asterisk_path),
                    "-rx",
                    command,
                ]
                logger.debug(f"Running command via sudo: {command_args}")

            if not wait:
                await asyncio.create_subprocess_exec(
                    *command_args,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    cwd=work_dir,
                )
                return 0, "", ""

            process = await asyncio.create_subprocess_exec(
                *command_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )

            stdout, stderr = await process.communicate()

            return_code = process.returncode
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            logger.debug(f"Asterisk command result: code={return_code}")
            if stderr_str and return_code != 0:
                logger.warning(f"Asterisk stderr: {stderr_str}")

            if return_code != 0:
                logger.error(f"Asterisk command failed: {command}")
                logger.error(f"Return code: {return_code}")
                logger.error(f"Stdout: {stdout_str}")
                logger.error(f"Stderr: {stderr_str}")

            return return_code, stdout_str, stderr_str

        except Exception as e:
            logger.error(f"Failed to run Asterisk command '{command}': {e}")
            raise AsteriskError(f"Command execution failed: {e}") from e

    async def test_connection(self) -> bool:
        """
        Test connection to Asterisk via CLI.

        Returns:
            True if Asterisk is responding, False otherwise
        """
        try:
            return_code, stdout, stderr = await self._run_asterisk_command("core show version")

            if return_code == 0 and "Asterisk" in stdout:
                logger.info("Asterisk CLI connection test successful")
                return True
            else:
                logger.warning(f"Asterisk CLI connection test failed: {stdout}")
                return False

        except Exception as e:
            logger.error(f"Asterisk CLI connection test error: {e}")
            return False

    async def get_node_status(self, node_number: int) -> Dict[str, Any]:
        """
        Get status of a specific node.

        Args:
            node_number: Node number to check

        Returns:
            Dictionary with node status information
        """
        try:
            return_code, stdout, stderr = await self._run_asterisk_command(
                f"rpt show {node_number}"
            )

            status = {
                "node": node_number,
                "online": False,
                "connected": False,
                "error": None,
                "raw_output": stdout,
            }

            if return_code == 0:
                # Parse node status from output
                if "Node is online" in stdout or "Node is connected" in stdout:
                    status["online"] = True
                if "Node is connected" in stdout:
                    status["connected"] = True
            else:
                status["error"] = stderr or "Unknown error"

            logger.debug(f"Node {node_number} status: {status}")
            return status

        except Exception as e:
            logger.error(f"Failed to get status for node {node_number}: {e}")
            return {
                "node": node_number,
                "online": False,
                "connected": False,
                "error": str(e),
                "raw_output": "",
            }

    async def get_all_nodes_status(self) -> List[Dict[str, Any]]:
        """
        Get status of all configured nodes.

        Returns:
            List of node status dictionaries
        """
        if not self.config.nodes:
            logger.warning("No nodes configured")
            return []

        tasks = [self.get_node_status(node) for node in self.config.get_nodes_list()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        node_statuses = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error getting node status: {result}")
                continue
            node_statuses.append(result)

        return node_statuses

    async def play_audio_on_node(self, node_number: int, audio_path: Path) -> bool:
        """
        Play audio file on a specific node.

        Args:
            node_number: Node number to play audio on
            audio_path: Path to audio file (can be anywhere, including /tmp)

        Returns:
            True if playback started successfully, False otherwise
        """
        if not audio_path.exists():
            logger.error(f"Audio file does not exist: {audio_path}")
            return False

        # Verify file is not empty
        if audio_path.stat().st_size == 0:
            logger.error(f"Audio file is empty: {audio_path}")
            return False

        # Log file extension for debugging
        file_ext = audio_path.suffix.lower()
        if file_ext not in [".ulaw", ".ul", ".wav", ".gsm"]:
            logger.warning(
                f"Audio file has unexpected extension {file_ext}, may cause playback issues"
            )

        try:
            # Use full path for playback (Asterisk can play from /tmp or anywhere)
            # Remove file extension for rpt playback command (Asterisk doesn't need it)
            playback_path = str(audio_path.resolve())  # Use resolve() to get absolute path

            # Remove extension - Asterisk auto-detects format from the file
            if playback_path.endswith((".wav", ".mp3", ".gsm", ".ulaw", ".ul")):
                playback_path = playback_path.rsplit(".", 1)[0]

            # Log what we're doing
            file_extension = audio_path.suffix.lower() if audio_path.suffix else None
            logger.debug(
                f"Audio file extension: {file_extension}, playback path (no ext): {playback_path}"
            )

            # Build the rpt playback command
            # Format: rpt localplay <node> <filename> for local playback
            # Format: rpt playback <node> <filename> for global playback
            playback_mode = getattr(self.config, "playback_mode", "local").lower()
            if playback_mode == "global":
                command = f"rpt playback {node_number} {playback_path}"
            else:
                command = f"rpt localplay {node_number} {playback_path}"

            # Verify readability from the service user when already running as asterisk
            try:
                actual_file_path = str(audio_path.resolve())
                if os.geteuid() == 0 or os.getenv("USER") == "asterisk":
                    if not os.access(actual_file_path, os.R_OK):
                        logger.warning(
                            "Asterisk user may not be able to read file: %s",
                            actual_file_path,
                        )
            except Exception as e:
                logger.debug(f"Could not verify file accessibility: {e}")

            logger.debug(
                "Playing audio on node %s (mode: %s): %s",
                node_number,
                playback_mode,
                playback_path,
            )

            playback_cwd = (
                audio_path.parent
                if audio_path.parent.exists()
                else Path("/var/lib/skywarnplus-ng")
            )
            return_code, stdout, stderr = await self._run_asterisk_command(
                command,
                cwd=playback_cwd,
                wait=False,
            )

            if return_code == 0:
                logger.info(f"Started audio playback on node {node_number}: {playback_path}")
                return True
            else:
                logger.error(f"Failed to play audio on node {node_number}")
                logger.error(f"Return code: {return_code}")
                logger.error(f"Stdout: {stdout}")
                logger.error(f"Stderr: {stderr}")
                return False

        except Exception as e:
            logger.error(f"Error playing audio on node {node_number}: {e}", exc_info=True)
            return False

    async def play_audio_on_all_nodes(self, audio_path: Path) -> List[int]:
        """
        Play audio file on all configured nodes.

        Args:
            audio_path: Path to audio file

        Returns:
            List of node numbers where playback started successfully
        """
        # Get all node numbers (handles both int and NodeConfig formats)
        all_nodes = self.config.get_nodes_list()
        return await self.play_audio_on_nodes(audio_path, all_nodes)

    async def play_audio_on_nodes(self, audio_path: Path, node_numbers: List[int]) -> List[int]:
        """
        Play audio file on specific nodes.

        Args:
            audio_path: Path to audio file
            node_numbers: List of node numbers to play audio on

        Returns:
            List of node numbers where playback started successfully
        """
        if not node_numbers:
            logger.warning("No nodes specified for audio playback")
            return []

        logger.info(f"Playing audio on {len(node_numbers)} nodes: {audio_path}")

        # Play audio on specified nodes concurrently
        tasks = [self.play_audio_on_node(node, audio_path) for node in node_numbers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_nodes = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error playing audio on node {node_numbers[i]}: {result}")
            elif result:
                successful_nodes.append(node_numbers[i])

        logger.info(f"Audio playback started on {len(successful_nodes)}/{len(node_numbers)} nodes")
        return successful_nodes

    async def stop_audio_on_node(self, node_number: int) -> bool:
        """
        Stop audio playback on a specific node.

        Args:
            node_number: Node number to stop audio on

        Returns:
            True if stop command was sent successfully, False otherwise
        """
        try:
            # Use rpt stop command
            command = f"rpt stop {node_number}"
            return_code, stdout, stderr = await self._run_asterisk_command(command)

            if return_code == 0:
                logger.info(f"Stopped audio playback on node {node_number}")
                return True
            else:
                logger.warning(f"Failed to stop audio on node {node_number}: {stderr}")
                return False

        except Exception as e:
            logger.error(f"Error stopping audio on node {node_number}: {e}")
            return False

    async def stop_audio_on_all_nodes(self) -> List[int]:
        """
        Stop audio playback on all configured nodes.

        Returns:
            List of node numbers where stop command was sent successfully
        """
        if not self.config.get_nodes_list():
            return []

        node_numbers = self.config.get_nodes_list()
        logger.info(f"Stopping audio on {len(node_numbers)} nodes")

        tasks = [self.stop_audio_on_node(node) for node in node_numbers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_nodes = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error stopping audio on node {node_numbers[i]}: {result}")
            elif result:
                successful_nodes.append(node_numbers[i])

        logger.info(f"Audio stopped on {len(successful_nodes)}/{len(node_numbers)} nodes")
        return successful_nodes

    async def key_node(self, node_number: int) -> bool:
        """
        Key (transmit) a specific node.

        Args:
            node_number: Node number to key

        Returns:
            True if key command was sent successfully, False otherwise
        """
        try:
            command = f"rpt key {node_number}"
            return_code, stdout, stderr = await self._run_asterisk_command(command)

            if return_code == 0:
                logger.info(f"Keyed node {node_number}")
                return True
            else:
                logger.warning(f"Failed to key node {node_number}: {stderr}")
                return False

        except Exception as e:
            logger.error(f"Error keying node {node_number}: {e}")
            return False

    async def unkey_node(self, node_number: int) -> bool:
        """
        Unkey (stop transmitting) a specific node.

        Args:
            node_number: Node number to unkey

        Returns:
            True if unkey command was sent successfully, False otherwise
        """
        try:
            command = f"rpt unkey {node_number}"
            return_code, stdout, stderr = await self._run_asterisk_command(command)

            if return_code == 0:
                logger.info(f"Unkeyed node {node_number}")
                return True
            else:
                logger.warning(f"Failed to unkey node {node_number}: {stderr}")
                return False

        except Exception as e:
            logger.error(f"Error unkeying node {node_number}: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Get Asterisk manager status.

        Returns:
            Status dictionary
        """
        return {
            "enabled": self.config.enabled,
            "nodes": self.config.nodes,
            "audio_delay": self.config.audio_delay,
            "asterisk_path": str(self.asterisk_path),
            "asterisk_exists": self.asterisk_path.exists(),
        }
