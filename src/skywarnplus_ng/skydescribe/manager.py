"""
SkyDescribe Manager - Handles generation and management of weather description audio files.
"""

import contextlib
import logging
import subprocess
import wave
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..audio.manager import AudioManager
from ..core.models import WeatherAlert
from ..utils.cap_speech import prepare_cap_text_for_tts

logger = logging.getLogger(__name__)


class SkyDescribeError(Exception):
    """SkyDescribe error."""


@dataclass
class DescriptionAudio:
    """Description audio file metadata."""

    alert_id: str
    file_path: Path
    created_at: datetime
    duration_seconds: float
    description_text: str


class SkyDescribeManager:
    """Manages weather description audio generation and DTMF functionality."""

    def __init__(self, audio_manager: AudioManager, descriptions_dir: Path, max_words: int = 150):
        """
        Initialize SkyDescribe manager.

        Args:
            audio_manager: Audio manager for TTS functionality
            descriptions_dir: Directory to store description audio files
            max_words: Maximum words in description (default: 150)
        """
        self.audio_manager = audio_manager
        self.descriptions_dir = descriptions_dir
        self.descriptions_dir.mkdir(parents=True, exist_ok=True)

        # Ensure directory is readable by asterisk user (chmod 755)
        try:
            import os

            os.chmod(self.descriptions_dir, 0o755)
            logger.debug(f"Set permissions on descriptions directory: {self.descriptions_dir}")
        except Exception as e:
            logger.warning(f"Failed to set permissions on descriptions directory: {e}")

        self.max_words = max_words

        # Cache of generated description audio files
        self._description_cache: dict[str, DescriptionAudio] = {}

        # DTMF code mappings
        self.dtmf_codes = {
            "*1": "current_alerts",
            "*2": "alert_by_id",
            "*3": "all_clear",
            "*4": "system_status",
            "*5": "help",
        }

    async def generate_description_audio(self, alert: WeatherAlert) -> DescriptionAudio | None:
        """
        Generate audio file for alert description.

        Args:
            alert: Weather alert to generate description for

        Returns:
            DescriptionAudio object or None if generation failed
        """
        try:
            # Check if we already have this description
            if alert.id in self._description_cache:
                cached = self._description_cache[alert.id]
                if cached.file_path.exists():
                    logger.debug(f"Using cached description for alert {alert.id}")
                    return cached

            # Create description text
            description_text = self._create_description_text(alert)

            # Generate unique filename
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f"desc_{alert.id}_{timestamp}.{self.audio_manager.config.tts.output_format}"
            output_path = self.descriptions_dir / filename

            # Generate audio using the audio manager's TTS engine
            audio_path = self.audio_manager.tts_engine.synthesize(description_text, output_path)

            if not audio_path or not audio_path.exists():
                logger.error(f"Failed to generate description audio for alert {alert.id}")
                return None

            # Get audio duration
            duration = self.audio_manager.tts_engine.get_audio_duration(audio_path)

            # Create description audio object
            desc_audio = DescriptionAudio(
                alert_id=alert.id,
                file_path=audio_path,
                created_at=datetime.now(UTC),
                duration_seconds=duration,
                description_text=description_text,
            )

            # Cache the result
            self._description_cache[alert.id] = desc_audio

            logger.info(f"Generated description audio for alert {alert.id}: {audio_path}")
            return desc_audio

        except Exception as e:
            logger.error(f"Error generating description audio for alert {alert.id}: {e}")
            return None

    def modify_description(self, description: str) -> str:
        """
        Modify the description to make it more suitable for conversion to audio.
        This matches the behavior of the original SkyDescribe.py.

        Args:
            description: The description text.

        Returns:
            The modified description text.
        """
        return prepare_cap_text_for_tts(description, max_words=self.max_words)

    def _create_description_text(self, alert: WeatherAlert) -> str:
        """
        Create comprehensive description text for alert.

        Args:
            alert: Weather alert

        Returns:
            Formatted description text
        """
        parts = []

        # Alert type and area
        parts.append(f"Weather alert: {alert.event}")
        parts.append(f"Affected area: {alert.area_desc}")

        # Add headline if available
        if alert.headline:
            parts.append(f"Headline: {alert.headline}")

        # Add full description
        if alert.description:
            parts.append(f"Description: {alert.description}")

        # Add instructions if available
        if alert.instruction:
            parts.append(f"Instructions: {alert.instruction}")

        # Add timing information
        parts.append(f"Effective: {alert.effective.strftime('%B %d, %Y at %I:%M %p')}")
        parts.append(f"Expires: {alert.expires.strftime('%B %d, %Y at %I:%M %p')}")

        # Add severity and urgency
        parts.append(f"Severity: {alert.severity.value}")
        parts.append(f"Urgency: {alert.urgency.value}")
        parts.append(f"Certainty: {alert.certainty.value}")

        return ". ".join(parts) + "."

    async def generate_current_alerts_description(
        self, alerts: list[WeatherAlert]
    ) -> DescriptionAudio | None:
        """
        Generate description for all current active alerts.

        Args:
            alerts: List of current active alerts

        Returns:
            DescriptionAudio object or None if generation failed
        """
        try:
            if not alerts:
                # Generate "no alerts" message
                text = "There are currently no active weather alerts in your area."
            else:
                # Create summary text
                parts = [f"There are currently {len(alerts)} active weather alerts:"]

                for i, alert in enumerate(alerts, 1):
                    parts.append(f"Alert {i}: {alert.event} for {alert.area_desc}")
                    if alert.description:
                        # Truncate description for summary
                        desc = (
                            alert.description[:200] + "..."
                            if len(alert.description) > 200
                            else alert.description
                        )
                        parts.append(f"Details: {desc}")

                text = ". ".join(parts) + "."

            # Generate unique filename for current alerts
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f"current_alerts_{timestamp}.{self.audio_manager.config.tts.output_format}"
            output_path = self.descriptions_dir / filename

            # Generate audio
            audio_path = self.audio_manager.tts_engine.synthesize(text, output_path)

            if not audio_path or not audio_path.exists():
                logger.error("Failed to generate current alerts description audio")
                return None

            # Get duration
            duration = self.audio_manager.tts_engine.get_audio_duration(audio_path)

            # Create description audio object
            desc_audio = DescriptionAudio(
                alert_id="current_alerts",
                file_path=audio_path,
                created_at=datetime.now(UTC),
                duration_seconds=duration,
                description_text=text,
            )

            logger.info(f"Generated current alerts description: {audio_path}")
            return desc_audio

        except Exception as e:
            logger.error(f"Error generating current alerts description: {e}")
            return None

    async def generate_all_clear_description(self) -> DescriptionAudio | None:
        """Generate all-clear description audio."""
        try:
            text = "The National Weather Service has cleared all alerts."

            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f"all_clear_{timestamp}.{self.audio_manager.config.tts.output_format}"
            output_path = self.descriptions_dir / filename

            audio_path = self.audio_manager.tts_engine.synthesize(text, output_path)

            if not audio_path or not audio_path.exists():
                logger.error("Failed to generate all-clear description audio")
                return None

            duration = self.audio_manager.tts_engine.get_audio_duration(audio_path)

            desc_audio = DescriptionAudio(
                alert_id="all_clear",
                file_path=audio_path,
                created_at=datetime.now(UTC),
                duration_seconds=duration,
                description_text=text,
            )

            logger.info(f"Generated all-clear description: {audio_path}")
            return desc_audio

        except Exception as e:
            logger.error(f"Error generating all-clear description: {e}")
            return None

    async def generate_system_status_description(
        self, status: dict[str, Any]
    ) -> DescriptionAudio | None:
        """Generate system status description audio."""
        try:
            parts = ["SkywarnPlus-NG System Status"]

            if status.get("running", False):
                parts.append("System is running normally")
                parts.append(f"Active alerts: {status.get('active_alerts', 0)}")
                parts.append(f"Uptime: {self._format_uptime(status.get('uptime_seconds', 0))}")
            else:
                parts.append("System is not running")

            parts.append("For detailed information, visit the web dashboard")

            text = ". ".join(parts) + "."

            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f"system_status_{timestamp}.{self.audio_manager.config.tts.output_format}"
            output_path = self.descriptions_dir / filename

            audio_path = self.audio_manager.tts_engine.synthesize(text, output_path)

            if not audio_path or not audio_path.exists():
                logger.error("Failed to generate system status description audio")
                return None

            duration = self.audio_manager.tts_engine.get_audio_duration(audio_path)

            desc_audio = DescriptionAudio(
                alert_id="system_status",
                file_path=audio_path,
                created_at=datetime.now(UTC),
                duration_seconds=duration,
                description_text=text,
            )

            logger.info(f"Generated system status description: {audio_path}")
            return desc_audio

        except Exception as e:
            logger.error(f"Error generating system status description: {e}")
            return None

    def cleanup_alert_description(self, alert_id: str) -> int:
        """
        Clean up description audio files for a specific alert ID.

        Args:
            alert_id: Alert ID to clean up description files for

        Returns:
            Number of files cleaned up
        """
        if not self.descriptions_dir.exists():
            return 0

        cleaned_count = 0

        # Remove from cache
        if alert_id in self._description_cache:
            cached = self._description_cache[alert_id]
            if cached.file_path.exists():
                try:
                    cached.file_path.unlink()
                    cleaned_count += 1
                    logger.debug(
                        f"Cleaned up cached description file for alert {alert_id}: {cached.file_path}"
                    )
                except OSError as e:
                    logger.warning(
                        f"Failed to clean up cached description file {cached.file_path}: {e}"
                    )
            del self._description_cache[alert_id]

        # Also check for any files matching the pattern (in case cache was cleared)
        import fnmatch

        for file_path in self.descriptions_dir.iterdir():
            if file_path.is_file():
                try:
                    filename = file_path.name
                    # Match pattern: desc_{alert_id}_*
                    if fnmatch.fnmatch(filename, f"desc_{alert_id}_*"):
                        file_path.unlink()
                        cleaned_count += 1
                        logger.debug(
                            f"Cleaned up description file for alert {alert_id}: {file_path}"
                        )
                except OSError as e:
                    logger.warning(f"Failed to clean up description file {file_path}: {e}")

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} description file(s) for alert {alert_id}")

        return cleaned_count

    def _format_uptime(self, uptime_seconds: int) -> str:
        """Format uptime in a human-readable way."""
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60

        if hours > 0:
            return f"{hours} hours and {minutes} minutes"
        else:
            return f"{minutes} minutes"

    def get_description_audio(self, alert_id: str) -> DescriptionAudio | None:
        """Get cached description audio by alert ID."""
        return self._description_cache.get(alert_id)

    def cleanup_old_descriptions(self, max_age_hours: int = 24) -> int:
        """
        Clean up old description audio files.

        Args:
            max_age_hours: Maximum age of files to keep

        Returns:
            Number of files cleaned up
        """
        cleaned_count = 0
        cutoff_time = datetime.now(UTC).timestamp() - (max_age_hours * 3600)

        for alert_id, desc_audio in list(self._description_cache.items()):
            if desc_audio.created_at.timestamp() < cutoff_time:
                try:
                    if desc_audio.file_path.exists():
                        desc_audio.file_path.unlink()
                    del self._description_cache[alert_id]
                    cleaned_count += 1
                except Exception as e:
                    logger.warning(f"Failed to clean up description audio {alert_id}: {e}")

            logger.info(f"Cleaned up {cleaned_count} old description audio files")
        return cleaned_count

    def describe_by_index_or_title(
        self,
        index_or_title: str,
        last_alerts: OrderedDict,
        asterisk_nodes: list[int] | None = None,
        use_describe_wav: bool = True,
    ) -> Path | None:
        """
        Generate description audio by index or title, matching the original SkyDescribe.py behavior.

        Args:
            index_or_title: Alert index (1-based) or title
            last_alerts: OrderedDict of alert title -> list of alert data (from state)
            asterisk_nodes: List of Asterisk node numbers to play audio on (optional)
            use_describe_wav: If True, use describe.wav as output filename (default: True)

        Returns:
            Path to the generated audio file, or None if generation failed
        """
        alerts = list(last_alerts.items())

        # list the alerts in order as a numbered list
        logger.debug("SkyDescribe: List of alerts:")
        for i, alert in enumerate(alerts):
            logger.debug("SkyDescribe: %d. %s", i + 1, alert[0])

        # Determine if the argument is an index or a title
        description = None
        alert_title = None

        if str(index_or_title).isdigit():
            index = int(index_or_title) - 1
            if index >= len(alerts):
                logger.error("SkyDescribe: No alert found at index %d.", index + 1)
                description = f"Sky Describe error, no alert found at index {index + 1}."
            else:
                alert_title, alert_data = alerts[index]

                # Count the unique instances of the alert
                unique_instances = len(
                    set(
                        (data.get("description", ""), data.get("end_time_utc", ""))
                        for data in alert_data
                    )
                )

                # Get the description
                if unique_instances == 1:
                    description = alert_data[0].get("description", "")
                else:
                    description = (
                        "There are {} unique instances of {}. Describing the first one. {}".format(
                            unique_instances, alert_title, alert_data[0].get("description", "")
                        )
                    )

        else:
            # Argument is not an index, assume it's a title
            title = index_or_title
            for alert, alert_data in alerts:
                if alert == title:  # Assuming alert is a title
                    alert_title = alert
                    # Count the unique instances of the alert
                    unique_instances = len(
                        set(
                            (data.get("description", ""), data.get("end_time_utc", ""))
                            for data in alert_data
                        )
                    )

                    # Get the description
                    if unique_instances == 1:
                        description = alert_data[0].get("description", "")
                    else:
                        description = "There are {} unique instances of {}. Describing the first one. {}".format(
                            unique_instances, alert_title, alert_data[0].get("description", "")
                        )
                    break
            else:
                logger.error("SkyDescribe: No alert with title %s found.", title)
                description = f"Sky Describe error, no alert found with title {title}."

        logger.debug("\n\nSkyDescribe: Original description: %s", description)

        # If the description is not an error message, extract the alert title and modify
        if "Sky Describe error" not in description:
            if not alert_title:
                # Try to find alert title from last_alerts
                for alert, _ in alerts:
                    if description and alert in description:
                        alert_title = alert
                        break

            if alert_title:
                logger.info("SkyDescribe: Generating description for alert: %s", alert_title)
                # Add the alert title at the beginning
                description = f"Detailed alert information for {alert_title}. {description}"
            else:
                logger.info("SkyDescribe: Generating description without alert title")

            # Apply modify_description
            description = self.modify_description(description)

        logger.debug("\n\nSkyDescribe: Modified description: %s\n\n", description)

        # Determine output path
        # Use correct extension based on configured output format
        output_ext = self.audio_manager.config.tts.output_format
        if use_describe_wav:
            output_path = self.descriptions_dir / f"describe.{output_ext}"
        else:
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            output_path = self.descriptions_dir / f"describe_{timestamp}.{output_ext}"

        # Generate audio using configured TTS engine
        audio_file = self.audio_manager.tts_engine.synthesize(description, output_path)
        if not audio_file or not audio_file.exists():
            logger.error("SkyDescribe: Failed to generate audio file")
            return None

        # Set permissions so asterisk user can read the file (chmod 644)
        try:
            import os

            os.chmod(audio_file, 0o644)
            logger.debug(f"Set permissions on audio file: {audio_file}")
        except Exception as e:
            logger.warning(f"Failed to set permissions on audio file: {e}")

        # Get audio duration (only for WAV format - other formats may not support this)
        try:
            # Only try to get duration if it's a WAV file
            if audio_file.suffix.lower() == ".wav":
                with contextlib.closing(wave.open(str(audio_file), "r")) as f:
                    frames = f.getnframes()
                    rate = f.getframerate()
                    duration = frames / float(rate)
                logger.debug("SkyDescribe: Length of the audio file in seconds: %s", duration)
            else:
                # For non-WAV formats, duration calculation may not be straightforward
                logger.debug(
                    f"SkyDescribe: Audio format {audio_file.suffix} - duration not calculated"
                )
        except Exception as e:
            logger.warning(f"SkyDescribe: Could not determine audio duration: {e}")

        # Play on Asterisk nodes if configured
        if asterisk_nodes:
            self.play_on_asterisk_nodes(audio_file, asterisk_nodes)

        return audio_file

    def play_on_asterisk_nodes(
        self, audio_path: Path, nodes: list[int], playback_mode: str = "local"
    ) -> None:
        """
        Play audio file on Asterisk nodes using rpt localplay or rpt playback.
        This matches the behavior of the original SkyDescribe.py.

        Args:
            audio_path: Path to the audio file
            nodes: List of Asterisk node numbers
            playback_mode: Playback mode - "local" (rpt localplay) or "global" (rpt playback)
        """
        # Verify file exists and is readable
        if not audio_path.exists():
            logger.error(f"SkyDescribe: Audio file does not exist: {audio_path}")
            return

        # Remove extension for Asterisk playback command
        playback_path = str(audio_path.resolve())
        if playback_path.endswith((".wav", ".mp3", ".gsm", ".ulaw", ".ul")):
            playback_path = playback_path.rsplit(".", 1)[0]

        import os

        # Check if we're already running as asterisk user (no sudo needed)
        current_user = os.getenv("USER") or os.getenv("USERNAME") or ""
        try:
            import pwd

            current_uid = os.getuid()
            try:
                asterisk_uid = pwd.getpwnam("asterisk").pw_uid
                is_asterisk_user = current_uid == asterisk_uid
            except KeyError:
                is_asterisk_user = False
        except (ImportError, AttributeError):
            is_asterisk_user = current_user == "asterisk"

        # Verify we can read the file (skip sudo when already asterisk; asterisk often not in sudoers)
        if not os.access(audio_path, os.R_OK):
            logger.warning(f"SkyDescribe: Cannot read audio file: {audio_path}")

        asterisk_path = "/usr/sbin/asterisk"

        # Normalize node to int (in case raw config.asterisk.nodes was passed)
        def _node_num(n):
            return int(getattr(n, "number", n) if not isinstance(n, int) else n)

        for node in nodes:
            node_num = _node_num(node)
            logger.info("SkyDescribe: Broadcasting description on node %s.", node_num)

            if playback_mode.lower() == "global":
                asterisk_cmd = f"rpt playback {node_num} {playback_path}"
            else:
                asterisk_cmd = f"rpt localplay {node_num} {playback_path}"

            try:
                if is_asterisk_user:
                    logger.debug(
                        "SkyDescribe: Running as asterisk user: %s -rx '%s'",
                        asterisk_path,
                        asterisk_cmd,
                    )
                    cmd = [asterisk_path, "-rx", asterisk_cmd]
                else:
                    logger.debug(
                        "SkyDescribe: Running via sudo: sudo -n -u asterisk %s -rx '%s'",
                        asterisk_path,
                        asterisk_cmd,
                    )
                    cmd = ["sudo", "-n", "-u", "asterisk", asterisk_path, "-rx", asterisk_cmd]

                # Fire-and-forget: rpt localplay blocks until playback finishes (~30s+).
                # Use Popen so describe returns immediately; audio continues playing.
                # Use audio file's directory as cwd; Asterisk can fail with "Unable to access
                # the running directory" when cwd is /tmp (permission or path resolution).
                work_dir = str(audio_path.parent)

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=work_dir,
                )
                logger.info(
                    "SkyDescribe: Started playback on node %s (pid %s) cwd=%s",
                    node_num,
                    proc.pid,
                    work_dir,
                )
            except Exception as e:
                logger.error("SkyDescribe: Failed to start playback on node %s: %s", node_num, e)
