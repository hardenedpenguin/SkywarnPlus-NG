"""
Tail message management for SkywarnPlus-NG.

Tail messages are audio files that contain a list of active alerts and are
played automatically after transmissions to keep listeners informed about
current weather conditions.
"""

import logging
import fnmatch
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydub import AudioSegment

from ..core.config import AudioConfig, AlertConfig, FilteringConfig
from ..core.models import WeatherAlert
from .tts_engine import GTTSEngine

logger = logging.getLogger(__name__)


class TailMessageError(Exception):
    """Tail message error."""
    pass


class TailMessageManager:
    """Manages tail message generation and file management."""

    def __init__(
        self,
        audio_config: AudioConfig,
        alert_config: AlertConfig,
        filtering_config: FilteringConfig,
        tail_message_path: Path,
        audio_delay_ms: int = 0,
        with_county_names: bool = False,
        suffix_file: Optional[str] = None
    ):
        """
        Initialize tail message manager.

        Args:
            audio_config: Audio configuration
            alert_config: Alert configuration
            filtering_config: Filtering configuration
            tail_message_path: Path where tail message file should be written
            audio_delay_ms: Audio delay in milliseconds to prepend
            with_county_names: Whether to include county names in tail message
            suffix_file: Optional suffix audio file to append
        """
        self.audio_config = audio_config
        self.alert_config = alert_config
        self.filtering_config = filtering_config
        self.tail_message_path = tail_message_path
        self.audio_delay_ms = audio_delay_ms
        self.with_county_names = with_county_names
        self.suffix_file = suffix_file
        self.tts_engine = GTTSEngine(audio_config.tts)
        
        # Ensure output directory exists
        self.tail_message_path.parent.mkdir(parents=True, exist_ok=True)

    def _should_include_alert(self, alert: WeatherAlert) -> bool:
        """
        Check if an alert should be included in tail message.

        Args:
            alert: Alert to check

        Returns:
            True if alert should be included
        """
        # Check if tail messages are enabled
        if not self.alert_config.tail_message:
            return False

        # Check if alert is blocked from tail message
        for blocked_pattern in self.filtering_config.tail_message_blocked:
            if fnmatch.fnmatch(alert.event, blocked_pattern):
                logger.debug(f"Alert {alert.event} blocked from tail message by pattern: {blocked_pattern}")
                return False

        return True

    def _load_audio_file(self, file_path: Path) -> Optional[AudioSegment]:
        """
        Load an audio file, handling different formats.

        Args:
            file_path: Path to audio file

        Returns:
            AudioSegment or None if file not found
        """
        if not file_path.exists():
            logger.warning(f"Audio file not found: {file_path}")
            return None

        try:
            # Determine format from extension
            ext = file_path.suffix.lower()
            if ext == '.wav':
                return AudioSegment.from_wav(str(file_path))
            elif ext == '.mp3':
                return AudioSegment.from_mp3(str(file_path))
            elif ext in ['.ulaw', '.ul']:
                # For ulaw files, pydub doesn't support them directly
                # Convert to WAV using ffmpeg first, then load
                try:
                    # Create temporary WAV file
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                        temp_wav_path = Path(temp_wav.name)
                    
                    # Convert ulaw to WAV using ffmpeg
                    result = subprocess.run(
                        [
                            "ffmpeg", "-y",
                            "-f", "mulaw",  # Input format: mulaw
                            "-ar", "8000",  # Sample rate: 8kHz (standard for ulaw)
                            "-ac", "1",     # Channels: mono
                            "-i", str(file_path),
                            str(temp_wav_path)
                        ],
                        check=True,
                        capture_output=True,
                        timeout=30,
                        text=True
                    )
                    
                    # Load the converted WAV file
                    audio = AudioSegment.from_wav(str(temp_wav_path))
                    
                    # Clean up temporary file
                    try:
                        temp_wav_path.unlink()
                    except Exception:
                        pass
                    
                    return audio
                except subprocess.CalledProcessError as e:
                    error_msg = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else 'Unknown error')
                    logger.error(f"Failed to convert ulaw file {file_path} to WAV: {error_msg}")
                    return None
                except FileNotFoundError:
                    logger.error("FFmpeg not found - cannot load ulaw files")
                    return None
            else:
                # Try to auto-detect
                return AudioSegment.from_file(str(file_path))
        except Exception as e:
            logger.error(f"Failed to load audio file {file_path}: {e}")
            return None

    def _generate_alert_text_segment(self, alert: WeatherAlert) -> str:
        """
        Generate text for a single alert in the tail message.

        Args:
            alert: Alert to generate text for

        Returns:
            Text representation of the alert
        """
        text = alert.event
        
        # Add county names if enabled
        if self.with_county_names and alert.area_desc:
            text += f" for {alert.area_desc}"
        
        return text

    def build_tail_message(self, alerts: List[WeatherAlert]) -> bool:
        """
        Build tail message audio file from active alerts.

        Args:
            alerts: List of active alerts

        Returns:
            True if tail message was built successfully
        """
        if not self.alert_config.tail_message:
            logger.debug("Tail messages disabled, removing tail message file")
            self._remove_tail_message()
            return True

        try:
            # Filter alerts that should be included
            included_alerts = [alert for alert in alerts if self._should_include_alert(alert)]

            # If no alerts to include, create silent tail message
            if not included_alerts:
                logger.debug("No alerts to include in tail message, creating silent file")
                silence = AudioSegment.silent(duration=100)
                combined_sound = self._convert_audio_format(silence)
            else:
                # Build tail message from alerts
                combined_sound = AudioSegment.empty()
                
                # Load separator sound if available
                separator_path = self.audio_config.sounds_path / self.audio_config.separator_sound
                separator_sound = self._load_audio_file(separator_path)
                
                # Generate audio for each alert
                temp_files_to_cleanup = []
                for i, alert in enumerate(included_alerts):
                    logger.debug(f"Adding alert to tail message: {alert.event}")
                    
                    # Add separator before each alert (except first)
                    if i > 0 and separator_sound:
                        combined_sound += separator_sound
                    
                    # Generate TTS audio for alert text
                    alert_text = self._generate_alert_text_segment(alert)
                    logger.debug(f"Generating TTS for tail message: {alert_text}")
                    
                    # Create temporary file for this alert's audio
                    temp_alert_file = self.audio_config.temp_dir / f"tail_alert_{alert.id}.{self.audio_config.tts.output_format}"
                    temp_files_to_cleanup.append(temp_alert_file)
                    
                    try:
                        # Generate TTS audio
                        alert_audio_path = self.tts_engine.synthesize(alert_text, temp_alert_file)
                        if alert_audio_path and alert_audio_path.exists():
                            alert_audio = self._load_audio_file(alert_audio_path)
                            if alert_audio:
                                combined_sound += alert_audio
                                # Add small silence between alerts
                                combined_sound += AudioSegment.silent(duration=200)
                            else:
                                logger.warning(f"Failed to load generated audio for alert: {alert.event}")
                        else:
                            logger.warning(f"Failed to generate audio for alert: {alert.event}")
                    except Exception as e:
                        logger.error(f"Error generating audio for alert {alert.event}: {e}")
                        continue
                    finally:
                        # Clean up temporary file
                        try:
                            if temp_alert_file.exists():
                                temp_alert_file.unlink()
                        except Exception as e:
                            logger.debug(f"Failed to cleanup temp file {temp_alert_file}: {e}")

                # Add suffix if configured
                if self.suffix_file:
                    suffix_path = self.audio_config.sounds_path / self.suffix_file
                    suffix_sound = self._load_audio_file(suffix_path)
                    if suffix_sound:
                        logger.debug(f"Adding tail message suffix: {self.suffix_file}")
                        combined_sound += AudioSegment.silent(duration=1000) + suffix_sound

                # Convert to proper format
                combined_sound = self._convert_audio_format(combined_sound)

            # Add audio delay if configured
            if self.audio_delay_ms > 0:
                logger.debug(f"Prepending tail message with {self.audio_delay_ms}ms of silence")
                silence = AudioSegment.silent(duration=self.audio_delay_ms)
                combined_sound = silence + combined_sound

            # Export to tail message file
            logger.info(f"Writing tail message to {self.tail_message_path}")
            combined_sound.export(str(self.tail_message_path), format="wav")
            
            return True

        except Exception as e:
            logger.error(f"Error building tail message: {e}", exc_info=True)
            return False

    def _convert_audio_format(self, audio: AudioSegment) -> AudioSegment:
        """
        Convert audio to the required format for Asterisk.

        Args:
            audio: Audio segment to convert

        Returns:
            Converted audio segment
        """
        # Convert to mono if needed
        if audio.channels > 1:
            audio = audio.set_channels(1)
        
        # Resample to target sample rate
        if audio.frame_rate != self.audio_config.tts.sample_rate:
            audio = audio.set_frame_rate(self.audio_config.tts.sample_rate)
        
        return audio

    def _remove_tail_message(self) -> None:
        """Remove tail message file."""
        try:
            if self.tail_message_path.exists():
                self.tail_message_path.unlink()
                logger.debug(f"Removed tail message file: {self.tail_message_path}")
        except Exception as e:
            logger.error(f"Error removing tail message file: {e}")

    def update_tail_message(self, alerts: List[WeatherAlert]) -> bool:
        """
        Update tail message based on current alerts.

        Args:
            alerts: List of current active alerts

        Returns:
            True if update was successful
        """
        return self.build_tail_message(alerts)

