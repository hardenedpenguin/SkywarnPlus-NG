"""
Audio management for SkywarnPlus-NG.
"""

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

from ..core.config import AudioConfig
from ..core.models import WeatherAlert
from .tts_engine import GTTSEngine, TTSEngineError

logger = logging.getLogger(__name__)


class AudioManagerError(Exception):
    """Audio manager error."""

    pass


class AudioManager:
    """Manages audio generation and file handling."""

    def __init__(self, config: AudioConfig):
        """
        Initialize audio manager.

        Args:
            config: Audio configuration
        """
        self.config = config
        self.tts_engine = GTTSEngine(config.tts)
        
        # Ensure directories exist
        self.config.sounds_path.mkdir(parents=True, exist_ok=True)
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Validate TTS engine
        if not self.tts_engine.is_available():
            raise AudioManagerError("TTS engine is not available")

    def generate_alert_audio(self, alert: WeatherAlert) -> Optional[Path]:
        """
        Generate audio for a weather alert.

        Args:
            alert: Weather alert to generate audio for

        Returns:
            Path to generated audio file, or None if generation failed
        """
        try:
            # Create alert text
            alert_text = self._create_alert_text(alert)
            logger.info(f"Generating audio for alert: {alert.event}")
            
            # Generate unique filename
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"alert_{alert.id}_{timestamp}.{self.config.tts.output_format}"
            output_path = self.config.temp_dir / filename
            
            # Synthesize audio
            audio_path = self.tts_engine.synthesize(alert_text, output_path)
            
            # Validate generated audio
            if not self.tts_engine.validate_audio_file(audio_path):
                logger.error(f"Generated audio file is invalid: {audio_path}")
                return None
            
            # Get audio duration
            duration = self.tts_engine.get_audio_duration(audio_path)
            logger.info(f"Generated alert audio: {audio_path} (duration: {duration:.1f}s)")
            
            return audio_path
            
        except TTSEngineError as e:
            logger.error(f"TTS engine error generating alert audio: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating alert audio: {e}", exc_info=True)
            return None

    def generate_all_clear_audio(self) -> Optional[Path]:
        """
        Generate all-clear audio message.

        Returns:
            Path to generated audio file, or None if generation failed
        """
        try:
            all_clear_text = "All clear. No active weather alerts at this time."
            logger.info("Generating all-clear audio")
            
            # Generate unique filename
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"allclear_{timestamp}.{self.config.tts.output_format}"
            output_path = self.config.temp_dir / filename
            
            # Synthesize audio
            audio_path = self.tts_engine.synthesize(all_clear_text, output_path)
            
            # Validate generated audio
            if not self.tts_engine.validate_audio_file(audio_path):
                logger.error(f"Generated all-clear audio file is invalid: {audio_path}")
                return None
            
            # Get audio duration
            duration = self.tts_engine.get_audio_duration(audio_path)
            logger.info(f"Generated all-clear audio: {audio_path} (duration: {duration:.1f}s)")
            
            return audio_path
            
        except TTSEngineError as e:
            logger.error(f"TTS engine error generating all-clear audio: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating all-clear audio: {e}", exc_info=True)
            return None

    def _create_alert_text(self, alert: WeatherAlert) -> str:
        """
        Create text for alert announcement.
        
        Only announces the alert type, matching original SkywarnPlus behavior.

        Args:
            alert: Weather alert

        Returns:
            Text to be spoken
        """
        # Only announce the alert type, just like the original SkywarnPlus
        return f"Weather alert: {alert.event}"

    def get_alert_sound_path(self) -> Optional[Path]:
        """
        Get path to alert sound file.

        Returns:
            Path to alert sound file, or None if not found
        """
        sound_path = self.config.sounds_path / self.config.alert_sound
        if sound_path.exists():
            return sound_path
        
        logger.warning(f"Alert sound file not found: {sound_path}")
        return None

    def get_all_clear_sound_path(self) -> Optional[Path]:
        """
        Get path to all-clear sound file.

        Returns:
            Path to all-clear sound file, or None if not found
        """
        sound_path = self.config.sounds_path / self.config.all_clear_sound
        if sound_path.exists():
            return sound_path
        
        logger.warning(f"All-clear sound file not found: {sound_path}")
        return None

    def get_separator_sound_path(self) -> Optional[Path]:
        """
        Get path to separator sound file.

        Returns:
            Path to separator sound file, or None if not found
        """
        sound_path = self.config.sounds_path / self.config.separator_sound
        if sound_path.exists():
            return sound_path
        
        logger.warning(f"Separator sound file not found: {sound_path}")
        return None

    def cleanup_old_audio(self, max_age_hours: int = 24) -> int:
        """
        Clean up old audio files.

        Args:
            max_age_hours: Maximum age of files to keep in hours

        Returns:
            Number of files cleaned up
        """
        if not self.config.temp_dir.exists():
            return 0
        
        cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        cleaned_count = 0
        
        for file_path in self.config.temp_dir.iterdir():
            if file_path.is_file():
                try:
                    file_age = file_path.stat().st_mtime
                    if file_age < cutoff_time:
                        file_path.unlink()
                        cleaned_count += 1
                        logger.debug(f"Cleaned up old audio file: {file_path}")
                except OSError as e:
                    logger.warning(f"Failed to clean up file {file_path}: {e}")
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old audio files")
        
        return cleaned_count

    def get_audio_info(self, audio_path: Path) -> Dict[str, Any]:
        """
        Get information about an audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            Dictionary with audio file information
        """
        info = {
            "path": str(audio_path),
            "exists": audio_path.exists(),
            "size_bytes": 0,
            "duration_seconds": 0.0,
            "valid": False,
        }
        
        if audio_path.exists():
            info["size_bytes"] = audio_path.stat().st_size
            info["duration_seconds"] = self.tts_engine.get_audio_duration(audio_path)
            info["valid"] = self.tts_engine.validate_audio_file(audio_path)
        
        return info

    def copy_audio_to_sounds(self, source_path: Path, filename: str) -> Optional[Path]:
        """
        Copy audio file to sounds directory.

        Args:
            source_path: Source audio file path
            filename: Destination filename

        Returns:
            Path to copied file, or None if copy failed
        """
        try:
            dest_path = self.config.sounds_path / filename
            
            # Ensure destination directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(source_path, dest_path)
            
            logger.debug(f"Copied audio file: {source_path} -> {dest_path}")
            return dest_path
            
        except Exception as e:
            logger.error(f"Failed to copy audio file: {e}")
            return None
