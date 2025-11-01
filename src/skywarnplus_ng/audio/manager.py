"""
Audio management for SkywarnPlus-NG.
"""

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

from ..core.config import AudioConfig
from ..core.models import WeatherAlert
from .tts_engine import GTTSEngine, TTSEngineError
from pydub import AudioSegment

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

    def generate_alert_audio(
        self,
        alert: WeatherAlert,
        suffix_file: Optional[str] = None,
        county_audio_files: Optional[List[str]] = None,
        with_multiples: bool = False
    ) -> Optional[Path]:
        """
        Generate audio for a weather alert.

        Args:
            alert: Weather alert to generate audio for
            suffix_file: Optional suffix audio file to append
            county_audio_files: Optional list of county audio file names to append
            with_multiples: Whether to add "with multiples" tag

        Returns:
            Path to generated audio file, or None if generation failed
        """
        try:
            # Create alert text
            alert_text = self._create_alert_text(alert)
            if with_multiples:
                alert_text += ", with multiples"
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
            
            # Append county audio files if provided
            if county_audio_files:
                audio_path = self._append_county_audio(audio_path, county_audio_files)
                if not audio_path:
                    logger.warning("Failed to append county audio, using original audio")
                    # Regenerate original audio if county append fails
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    filename = f"alert_{alert.id}_{timestamp}.{self.config.tts.output_format}"
                    output_path = self.config.temp_dir / filename
                    audio_path = self.tts_engine.synthesize(alert_text, output_path)
            
            # Append suffix if provided
            if suffix_file:
                audio_path = self._append_suffix_audio(audio_path, suffix_file)
                if not audio_path:
                    logger.warning(f"Failed to append suffix {suffix_file}, using original audio")
                    # Return original audio if suffix fails
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    filename = f"alert_{alert.id}_{timestamp}.{self.config.tts.output_format}"
                    output_path = self.config.temp_dir / filename
                    audio_path = self.tts_engine.synthesize(alert_text, output_path)
            
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

    def generate_all_clear_audio(self, suffix_file: Optional[str] = None) -> Optional[Path]:
        """
        Generate all-clear audio message.

        Args:
            suffix_file: Optional suffix audio file to append

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
            
            # Append suffix if provided
            if suffix_file:
                audio_path = self._append_suffix_audio(audio_path, suffix_file)
                if not audio_path:
                    logger.warning(f"Failed to append suffix {suffix_file}, using original audio")
                    # Return original audio if suffix fails
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    filename = f"allclear_{timestamp}.{self.config.tts.output_format}"
                    output_path = self.config.temp_dir / filename
                    audio_path = self.tts_engine.synthesize(all_clear_text, output_path)
            
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

    def _append_county_audio(self, main_audio_path: Path, county_audio_files: List[str]) -> Optional[Path]:
        """
        Append county audio files to the main audio file.

        Args:
            main_audio_path: Path to main audio file
            county_audio_files: List of county audio filenames (in sounds_path)

        Returns:
            Path to new combined audio file, or None if failed
        """
        try:
            # Load main audio
            main_audio = AudioSegment.from_file(str(main_audio_path))
            main_audio = main_audio.set_frame_rate(8000).set_channels(1)
            
            combined = main_audio
            added_counties = set()
            
            for i, county_file in enumerate(county_audio_files):
                county_path = self.config.sounds_path / county_file
                
                if not county_path.exists():
                    logger.warning(f"County audio file not found: {county_path}")
                    continue
                
                # Skip duplicates
                if county_file in added_counties:
                    continue
                added_counties.add(county_file)
                
                # Load county audio
                county_audio = AudioSegment.from_file(str(county_path))
                county_audio = county_audio.set_frame_rate(8000).set_channels(1)
                
                # Add spacing: 600ms before first county, 400ms before others
                spacing = AudioSegment.silent(duration=600 if i == 0 else 400)
                combined = combined + spacing + county_audio
            
            # Add final spacing after last county
            if county_audio_files:
                combined = combined + AudioSegment.silent(duration=600)
            
            # Create new filename for combined audio
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            base_name = main_audio_path.stem
            combined_filename = f"{base_name}_with_counties_{timestamp}.{self.config.tts.output_format}"
            combined_path = self.config.temp_dir / combined_filename
            
            # Export combined audio
            combined.export(str(combined_path), format=self.config.tts.output_format)
            
            logger.debug(f"Appended {len(added_counties)} county audio files to audio: {combined_path}")
            return combined_path
            
        except Exception as e:
            logger.error(f"Failed to append county audio: {e}")
            return None

    def _append_suffix_audio(self, main_audio_path: Path, suffix_filename: str) -> Optional[Path]:
        """
        Append a suffix audio file to the main audio file.

        Args:
            main_audio_path: Path to main audio file
            suffix_filename: Filename of suffix audio file (in sounds_path)

        Returns:
            Path to new combined audio file, or None if failed
        """
        try:
            suffix_path = self.config.sounds_path / suffix_filename
            
            if not suffix_path.exists():
                logger.warning(f"Suffix audio file not found: {suffix_path}")
                return None
            
            # Load both audio files
            main_audio = AudioSegment.from_file(str(main_audio_path))
            suffix_audio = AudioSegment.from_file(str(suffix_path))
            
            # Convert to same format (8000Hz mono for Asterisk compatibility)
            main_audio = main_audio.set_frame_rate(8000).set_channels(1)
            suffix_audio = suffix_audio.set_frame_rate(8000).set_channels(1)
            
            # Combine: main audio + 500ms silence + suffix
            combined = main_audio + AudioSegment.silent(duration=500) + suffix_audio
            
            # Create new filename for combined audio
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            base_name = main_audio_path.stem
            combined_filename = f"{base_name}_with_suffix_{timestamp}.{self.config.tts.output_format}"
            combined_path = self.config.temp_dir / combined_filename
            
            # Export combined audio
            combined.export(str(combined_path), format=self.config.tts.output_format)
            
            logger.debug(f"Appended suffix {suffix_filename} to audio: {combined_path}")
            return combined_path
            
        except Exception as e:
            logger.error(f"Failed to append suffix audio: {e}")
            return None

    def generate_county_audio(self, county_name: str) -> Optional[str]:
        """
        Generate audio file for a county name using TTS.

        Args:
            county_name: Full county name (e.g., "Brazoria County")

        Returns:
            Filename of generated audio file (relative to sounds_path), or None if failed
        """
        try:
            # Sanitize filename: remove special chars, replace spaces with underscores
            sanitized = re.sub(r'[^\w\s-]', '', county_name)  # Remove special chars
            sanitized = re.sub(r'[-\s]+', '_', sanitized)  # Replace spaces/hyphens with underscore
            sanitized = sanitized.strip('_')  # Remove leading/trailing underscores
            
            # Determine file extension based on output format
            ext = self.config.tts.output_format
            if ext == 'wav':
                filename = f"{sanitized}.wav"
            elif ext == 'mp3':
                filename = f"{sanitized}.mp3"
            else:
                filename = f"{sanitized}.{ext}"
            
            output_path = self.config.sounds_path / filename
            
            # Check if file already exists
            if output_path.exists():
                logger.info(f"County audio file already exists: {filename}")
                return filename
            
            logger.info(f"Generating county audio for: {county_name} -> {filename}")
            
            # Generate audio using TTS (says full county name)
            audio_path = self.tts_engine.synthesize(county_name, output_path)
            
            # Validate generated audio
            if not self.tts_engine.validate_audio_file(audio_path):
                logger.error(f"Generated county audio file is invalid: {audio_path}")
                return None
            
            # Get audio duration
            duration = self.tts_engine.get_audio_duration(audio_path)
            logger.info(f"Generated county audio: {filename} (duration: {duration:.1f}s)")
            
            return filename
            
        except TTSEngineError as e:
            logger.error(f"TTS engine error generating county audio: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating county audio: {e}", exc_info=True)
            return None

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
