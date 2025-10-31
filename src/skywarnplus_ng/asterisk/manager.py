"""
Asterisk manager for SkywarnPlus-NG on ASL3.
"""

import asyncio
import logging
import subprocess
import socket
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

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
        # If AMI credentials are configured, we don't need to check for asterisk binary
        if self.config.ami_username and self.config.ami_secret:
            logger.info("AMI credentials configured, will use AMI for connections")
            return
        
        # Otherwise, check for asterisk binary for CLI access
        if not self.asterisk_path.exists():
            raise AsteriskError(f"Asterisk not found at {self.asterisk_path}")
        
        if not self.asterisk_path.is_file():
            raise AsteriskError(f"Asterisk path is not a file: {self.asterisk_path}")
        
        if not self.asterisk_path.stat().st_mode & 0o111:  # Check if executable
            raise AsteriskError(f"Asterisk is not executable: {self.asterisk_path}")
        
        logger.info(f"Asterisk found at {self.asterisk_path}")

    def _has_ami_credentials(self) -> bool:
        """Check if AMI credentials are configured."""
        return bool(self.config.ami_username and self.config.ami_secret)

    async def _test_ami_connection(self) -> bool:
        """
        Test connection to Asterisk via AMI.
        
        Returns:
            True if connection successful, False otherwise
        """
        if not self._has_ami_credentials():
            return False
            
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.ami_host, self.config.ami_port),
                timeout=5.0
            )
            
            # Wait for AMI greeting
            greeting = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if not greeting.startswith(b'Asterisk Call Manager'):
                logger.warning(f"Unexpected AMI greeting: {greeting}")
                writer.close()
                await writer.wait_closed()
                return False
            
            # Read the rest of the greeting
            while True:
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=1.0)
                    if line.strip() == b'':
                        break
                except asyncio.TimeoutError:
                    break
            
            # Send login
            login = f"Action: Login\nUsername: {self.config.ami_username}\nSecret: {self.config.ami_secret}\n\n"
            writer.write(login.encode())
            await writer.drain()
            
            # Read response
            response_lines = []
            while True:
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=2.0)
                    if not line:
                        break
                    response_lines.append(line.decode('utf-8', errors='replace').strip())
                    if line.strip() == b'':
                        break
                except asyncio.TimeoutError:
                    break
            
            response_text = '\n'.join(response_lines)
            
            # Check if login was successful
            if 'Success' in response_text or 'Message: Authentication accepted' in response_text:
                logger.debug("AMI authentication successful")
                writer.close()
                await writer.wait_closed()
                return True
            else:
                logger.warning(f"AMI authentication failed: {response_text}")
                writer.close()
                await writer.wait_closed()
                return False
                
        except asyncio.TimeoutError:
            logger.error("AMI connection timeout")
            return False
        except Exception as e:
            logger.error(f"AMI connection error: {e}")
            return False

    async def _run_asterisk_command(self, command: str) -> Tuple[int, str, str]:
        """
        Run an Asterisk CLI command.

        Args:
            command: Asterisk CLI command to run

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        try:
            logger.debug(f"Running Asterisk command: {command}")
            
            # Execute via sudo as the asterisk user (requires sudoers configuration)
            process = await asyncio.create_subprocess_exec(
                "sudo", "-n", "-u", "asterisk", str(self.asterisk_path), "-x", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/tmp"  # Run from /tmp to avoid permission issues
            )
            
            stdout, stderr = await process.communicate()
            
            return_code = process.returncode
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            logger.debug(f"Asterisk command result: code={return_code}, stdout={stdout_str[:100]}...")
            
            if return_code != 0:
                logger.warning(f"Asterisk command failed: {command}, code={return_code}, stderr={stderr_str}")
            
            return return_code, stdout_str, stderr_str
            
        except Exception as e:
            logger.error(f"Failed to run Asterisk command '{command}': {e}")
            raise AsteriskError(f"Command execution failed: {e}") from e

    async def test_connection(self) -> bool:
        """
        Test connection to Asterisk.
        
        Uses AMI if credentials are configured, otherwise falls back to CLI.

        Returns:
            True if Asterisk is responding, False otherwise
        """
        # Try AMI first if credentials are configured
        if self._has_ami_credentials():
            try:
                connected = await self._test_ami_connection()
                if connected:
                    logger.info("Asterisk AMI connection test successful")
                    return True
                else:
                    logger.warning("Asterisk AMI connection test failed")
                    return False
            except Exception as e:
                logger.error(f"Asterisk AMI connection test error: {e}")
                return False
        
        # Fall back to CLI
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
            return_code, stdout, stderr = await self._run_asterisk_command(f"rpt show {node_number}")
            
            status = {
                "node": node_number,
                "online": False,
                "connected": False,
                "error": None,
                "raw_output": stdout
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
                "raw_output": ""
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
        
        tasks = [self.get_node_status(node) for node in self.config.nodes]
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
        
        try:
            # Use full path for playback (Asterisk can play from /tmp or anywhere)
            # Remove file extension for rpt playback command (Asterisk doesn't need it)
            playback_path = str(audio_path)
            if playback_path.endswith(('.wav', '.mp3', '.gsm')):
                playback_path = playback_path.rsplit('.', 1)[0]
            
            # Use rpt playback command with full path (without extension)
            command = f"rpt playback {node_number} {playback_path}"
            logger.debug(f"Executing Asterisk command: {command}")
            return_code, stdout, stderr = await self._run_asterisk_command(command)
            
            if return_code == 0:
                logger.info(f"Started audio playback on node {node_number}: {playback_path}")
                return True
            else:
                logger.error(f"Failed to play audio on node {node_number}: stderr={stderr}, stdout={stdout}")
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
        if not self.config.nodes:
            logger.warning("No nodes configured for audio playback")
            return []
        
        logger.info(f"Playing audio on {len(self.config.nodes)} nodes: {audio_path}")
        
        # Play audio on all nodes concurrently
        tasks = [
            self.play_audio_on_node(node, audio_path) 
            for node in self.config.nodes
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_nodes = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error playing audio on node {self.config.nodes[i]}: {result}")
            elif result:
                successful_nodes.append(self.config.nodes[i])
        
        logger.info(f"Audio playback started on {len(successful_nodes)}/{len(self.config.nodes)} nodes")
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
        if not self.config.nodes:
            return []
        
        logger.info(f"Stopping audio on {len(self.config.nodes)} nodes")
        
        # Stop audio on all nodes concurrently
        tasks = [self.stop_audio_on_node(node) for node in self.config.nodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_nodes = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error stopping audio on node {self.config.nodes[i]}: {result}")
            elif result:
                successful_nodes.append(self.config.nodes[i])
        
        logger.info(f"Audio stopped on {len(successful_nodes)}/{len(self.config.nodes)} nodes")
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