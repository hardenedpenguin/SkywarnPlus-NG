"""
Audio management for SkywarnPlus-NG.
"""

import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

from ..core.config import AudioConfig, TTSConfig
from ..core.models import WeatherAlert
from .tts_engine import GTTSEngine, PiperTSEngine, TTSEngineError
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
        self.tts_engine = self._create_tts_engine(config.tts)
        self._fallback_tts_engine: Optional[GTTSEngine] = None
        
        # Ensure directories exist
        self.config.sounds_path.mkdir(parents=True, exist_ok=True)
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure temp directory is readable by asterisk user (chmod 755)
        try:
            os.chmod(self.config.temp_dir, 0o755)
            logger.debug(f"Set permissions on temp directory: {self.config.temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to set permissions on temp directory: {e}")
        
        # Validate TTS engine with fallback to gTTS if Piper fails
        if not self.tts_engine.is_available():
            if config.tts.engine.lower() == "piper":
                logger.warning("Piper TTS is not available or failed to initialize. Falling back to gTTS.")
                # Create a gTTS config from the existing config
                from ..core.config import TTSConfig
                gtts_config = TTSConfig(
                    engine="gtts",
                    language=config.tts.language or "en",
                    tld=config.tts.tld or "com",
                    slow=config.tts.slow or False,
                    output_format=config.tts.output_format,
                    sample_rate=config.tts.sample_rate,
                    bit_rate=config.tts.bit_rate
                )
                self.tts_engine = GTTSEngine(gtts_config)
                if not self.tts_engine.is_available():
                    raise AudioManagerError("TTS engine is not available (tried Piper and gTTS)")
            else:
                raise AudioManagerError("TTS engine is not available")

    @staticmethod
    def _create_tts_engine(tts_config):
        """
        Create appropriate TTS engine based on configuration.

        Args:
            tts_config: TTS configuration

        Returns:
            TTS engine instance (GTTSEngine or PiperTSEngine)

        Raises:
            AudioManagerError: If engine type is unsupported
        """
        engine_type = tts_config.engine.lower()
        
        if engine_type == "gtts":
            return GTTSEngine(tts_config)
        elif engine_type == "piper":
            try:
                return PiperTSEngine(tts_config)
            except Exception as e:
                logger.error(f"Failed to initialize Piper TTS engine: {e}")
                logger.error("Piper TTS initialization failed. This may be due to:")
                logger.error("  - Missing or corrupted model file")
                logger.error("  - Incompatible Piper library version")
                logger.error("  - Resource constraints (memory/CPU)")
                logger.error("  - Incorrect model path configuration")
                # Don't raise here - let the fallback mechanism handle it
                raise
        else:
            raise AudioManagerError(f"Unsupported TTS engine: {engine_type}. Supported engines: 'gtts', 'piper'")

    def _get_fallback_tts_engine(self) -> Optional[GTTSEngine]:
        """
        Lazily create a gTTS fallback so we can still generate county audio if
        Piper becomes unavailable mid-run.
        """
        if self._fallback_tts_engine:
            return self._fallback_tts_engine

        try:
            fallback_config = TTSConfig(
                engine="gtts",
                language=self.config.tts.language or "en",
                tld=self.config.tts.tld or "com",
                slow=self.config.tts.slow or False,
                output_format=self.config.tts.output_format,
                sample_rate=self.config.tts.sample_rate,
                bit_rate=self.config.tts.bit_rate,
            )
            self._fallback_tts_engine = GTTSEngine(fallback_config)
            return self._fallback_tts_engine
        except Exception as exc:
            logger.error(f"Unable to initialize gTTS fallback engine: {exc}")
            return None

    def _synthesize_with_optional_fallback(
        self,
        text: str,
        output_path: Path,
        allow_fallback: bool = False,
    ):
        """
        Synthesize audio, optionally retrying with gTTS if the primary Piper
        engine fails. Returns a tuple of (engine_used, generated_path).
        """
        try:
            audio_path = self.tts_engine.synthesize(text, output_path)
            return self.tts_engine, audio_path
        except TTSEngineError as primary_error:
            if allow_fallback and self.config.tts.engine.lower() == "piper":
                logger.warning(f"Piper TTS failed ({primary_error}); attempting gTTS fallback")
                fallback_engine = self._get_fallback_tts_engine()
                if fallback_engine:
                    audio_path = fallback_engine.synthesize(text, output_path)
                    return fallback_engine, audio_path
                logger.error("gTTS fallback is unavailable; cannot synthesize audio")
            raise

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
            engine_used, audio_path = self._synthesize_with_optional_fallback(
                alert_text,
                output_path,
                allow_fallback=False,
            )
            
            # Validate generated audio
            if not engine_used.validate_audio_file(audio_path):
                logger.error(f"Generated audio file is invalid: {audio_path}")
                return None
            
            # Append county audio files if provided
            if county_audio_files:
                logger.info(f"Appending {len(county_audio_files)} county audio file(s): {county_audio_files} (sounds_path: {self.config.sounds_path})")
                new_audio_path = self._append_county_audio(audio_path, county_audio_files)
                if new_audio_path:
                    # County audio append succeeded, use the combined file
                    audio_path = new_audio_path
                    logger.info(f"Using combined audio with counties: {audio_path}")
                else:
                    logger.warning("Failed to append county audio, using original audio")
                    # Keep using the original audio_path (don't regenerate)
                    logger.info(f"Using original audio without counties: {audio_path}")
            else:
                logger.info(f"No county audio files provided for alert {alert.id} (county_audio_files is {county_audio_files})")
            
            # Append suffix if provided
            if suffix_file:
                new_audio_path = self._append_suffix_audio(audio_path, suffix_file)
                if new_audio_path:
                    # Suffix append succeeded, use the combined file
                    audio_path = new_audio_path
                    logger.debug(f"Using combined audio with suffix: {audio_path}")
                else:
                    logger.warning(f"Failed to append suffix {suffix_file}, using original audio")
                    # Keep using the existing audio_path (don't regenerate)
                    logger.debug(f"Using original audio without suffix: {audio_path}")
            
            # Get audio duration
            duration = engine_used.get_audio_duration(audio_path)
            
            # Ensure asterisk user can read the file (chmod 644)
            try:
                os.chmod(audio_path, 0o644)
                logger.debug(f"Set permissions on audio file: {audio_path}")
            except Exception as e:
                logger.warning(f"Failed to set permissions on audio file: {e}")
            
            # Ensure file is flushed to disk and verify it exists
            try:
                import time
                import os
                # Force filesystem sync
                try:
                    os.sync()  # Sync filesystem buffers
                except:
                    pass  # os.sync might not be available on all systems
                
                # Small delay to ensure filesystem has the file
                time.sleep(0.1)
                
                # Verify file exists and has content
                if not audio_path.exists():
                    logger.error(f"Audio file does not exist after creation: {audio_path}")
                    return None
                
                file_stat = audio_path.stat()
                if file_stat.st_size == 0:
                    logger.error(f"Audio file is empty after creation: {audio_path}")
                    return None
                
                logger.debug(f"Audio file verified: {audio_path} ({file_stat.st_size} bytes)")
            except Exception as e:
                logger.error(f"Failed to verify audio file: {e}", exc_info=True)
            
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
            engine_used, audio_path = self._synthesize_with_optional_fallback(
                all_clear_text,
                output_path,
                allow_fallback=False,
            )
            
            # Validate generated audio
            if not engine_used.validate_audio_file(audio_path):
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
            duration = engine_used.get_audio_duration(audio_path)
            
            # Ensure asterisk user can read the file (chmod 644)
            try:
                os.chmod(audio_path, 0o644)
                logger.debug(f"Set permissions on audio file: {audio_path}")
            except Exception as e:
                logger.warning(f"Failed to set permissions on audio file: {e}")
            
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

    def cleanup_alert_audio(self, alert_id: str) -> int:
        """
        Clean up audio files for a specific alert ID.
        
        Args:
            alert_id: Alert ID to clean up files for
            
        Returns:
            Number of files cleaned up
        """
        if not self.config.temp_dir.exists():
            return 0
        
        cleaned_count = 0
        
        # Check for files matching patterns: alert_{alert_id}_*.ulaw, tail_alert_{alert_id}.ulaw
        # Also handles variations (ulaw, wav, etc.)
        import fnmatch
        for file_path in self.config.temp_dir.iterdir():
            if file_path.is_file():
                try:
                    filename = file_path.name
                    # Check if file matches any pattern
                    if (fnmatch.fnmatch(filename, f"alert_{alert_id}_*") or 
                        fnmatch.fnmatch(filename, f"tail_alert_{alert_id}.*")):
                        file_path.unlink()
                        cleaned_count += 1
                        logger.debug(f"Cleaned up audio file for alert {alert_id}: {file_path}")
                except OSError as e:
                    logger.warning(f"Failed to clean up file {file_path}: {e}")
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} audio file(s) for alert {alert_id}")
        
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

    def _load_audio_file_for_append(self, audio_path: Path) -> Optional[AudioSegment]:
        """
        Load an audio file for appending, handling ulaw format conversion.
        
        Args:
            audio_path: Path to audio file (may be ulaw, wav, etc.)
            
        Returns:
            AudioSegment or None if failed
        """
        try:
            ext = audio_path.suffix.lower()
            if ext in ['.ulaw', '.ul']:
                # For ulaw files, convert to WAV first using ffmpeg
                import tempfile
                import subprocess
                
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                    temp_wav_path = Path(temp_wav.name)
                
                # Convert ulaw to WAV using ffmpeg
                result = subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-f", "mulaw",  # Input format: mulaw
                        "-ar", "8000",  # Sample rate: 8kHz (standard for ulaw)
                        "-ac", "1",     # Channels: mono
                        "-i", str(audio_path),
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
            else:
                # For other formats, use pydub directly
                return AudioSegment.from_file(str(audio_path))
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else 'Unknown error')
            logger.error(f"Failed to convert ulaw file {audio_path} to WAV: {error_msg}")
            return None
        except FileNotFoundError:
            logger.error("FFmpeg not found - cannot load ulaw files")
            return None
        except Exception as e:
            logger.error(f"Failed to load audio file {audio_path}: {e}")
            return None

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
            # Load main audio (handles ulaw conversion if needed)
            logger.info(f"Loading main audio file: {main_audio_path}")
            main_audio = self._load_audio_file_for_append(main_audio_path)
            if not main_audio:
                logger.error(f"Failed to load main audio file: {main_audio_path}")
                return None
            # Ensure 8kHz mono for Asterisk compatibility (required for ulaw)
            main_audio = main_audio.set_frame_rate(8000).set_channels(1)
            
            combined = main_audio
            appended_counties: List[str] = []
            missing_files: List[str] = []
            failed_loads: List[str] = []
            
            for county_file in county_audio_files:
                county_path = self.config.sounds_path / county_file
                logger.info(f"Looking for county audio file: {county_path} (resolved from sounds_path: {self.config.sounds_path}, filename: {county_file})")
                
                if not county_path.exists():
                    logger.warning(f"County audio file not found: {county_path} (sounds_path: {self.config.sounds_path})")
                    missing_files.append(county_file)
                    continue
                
                # Skip duplicates
                if county_file in appended_counties:
                    continue
                
                # Load county audio (handles ulaw conversion if needed)
                logger.info(f"Loading county audio file: {county_path}")
                county_audio = self._load_audio_file_for_append(county_path)
                if not county_audio:
                    logger.warning(f"Failed to load county audio file: {county_path}")
                    failed_loads.append(county_file)
                    continue
                county_audio = county_audio.set_frame_rate(8000).set_channels(1)
                logger.info(f"Successfully loaded county audio file: {county_file} (duration: {len(county_audio)/1000:.2f}s)")
                
                # Add spacing: 600ms before first county, 400ms before others
                spacing = AudioSegment.silent(duration=600 if not appended_counties else 400)
                combined = combined + spacing + county_audio
                appended_counties.append(county_file)
            
            if missing_files:
                logger.warning(f"Missing county audio files: {missing_files}")
            if failed_loads:
                logger.warning(f"Failed to load county audio files (conversion errors): {failed_loads}")
            if not appended_counties:
                logger.warning("No county audio could be appended; returning original alert audio")
                return main_audio_path
            
            # Add final spacing after last county
            combined = combined + AudioSegment.silent(duration=600)
            
            # Create new filename for combined audio
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            base_name = main_audio_path.stem
            combined_filename = f"{base_name}_with_counties_{timestamp}.{self.config.tts.output_format}"
            combined_path = self.config.temp_dir / combined_filename
            
            # Export combined audio in the configured format
            if self.config.tts.output_format.lower() in ["ulaw", "mulaw", "ul"]:
                # For ulaw, export as raw and convert
                self._export_to_ulaw(combined, combined_path)
            else:
                combined.export(str(combined_path), format=self.config.tts.output_format)
            
            # Ensure asterisk user can read the file
            try:
                os.chmod(combined_path, 0o644)
                logger.debug(f"Set permissions on combined audio file: {combined_path}")
            except Exception as e:
                logger.warning(f"Failed to set permissions on combined audio file: {e}")
            
            # Verify the file exists and has content
            if not combined_path.exists():
                logger.error(f"Combined audio file does not exist after creation: {combined_path}")
                return None
            if combined_path.stat().st_size == 0:
                logger.error(f"Combined audio file is empty after creation: {combined_path}")
                return None
            
            logger.info(f"Appended {len(appended_counties)} county audio files to audio: {combined_path}")
            return combined_path
            
        except Exception as e:
            logger.error(f"Failed to append county audio: {e}")
            return None

    def _export_to_ulaw(self, audio: AudioSegment, output_path: Path) -> None:
        """
        Export audio segment to ulaw format using ffmpeg.
        
        Args:
            audio: AudioSegment to export
            output_path: Path for output ulaw file
        """
        import tempfile
        import subprocess
        
        # Ensure 8kHz mono for ulaw
        audio = audio.set_frame_rate(8000).set_channels(1)
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_path = Path(temp_wav.name)
        
        try:
            # Export as WAV first (more reliable than raw)
            audio.export(str(temp_wav_path), format="wav")
            
            # Convert WAV to ulaw using ffmpeg
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(temp_wav_path),
                    "-ar", "8000", "-ac", "1",
                    "-f", "mulaw",
                    str(output_path)
                ],
                check=True,
                capture_output=True,
                timeout=30,
                text=True
            )
            # Verify file was created
            import time
            time.sleep(0.1)  # Brief pause for filesystem sync
            
            if not output_path.exists():
                logger.error(f"FFmpeg output file does not exist: {output_path}")
                logger.error(f"FFmpeg command: ffmpeg -y -i {temp_wav_path} -ar 8000 -ac 1 -f mulaw {output_path}")
                raise AudioManagerError(f"FFmpeg did not create output file: {output_path}")
            
            file_size = output_path.stat().st_size
            if file_size == 0:
                logger.error(f"FFmpeg created empty file: {output_path}")
                raise AudioManagerError(f"FFmpeg created empty ulaw file: {output_path}")
            
            logger.debug(f"Exported to ulaw: {output_path} ({file_size} bytes)")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else 'Unknown error')
            logger.error(f"FFmpeg conversion to ulaw failed: {error_msg}")
            if e.stdout:
                stdout_msg = e.stdout if isinstance(e.stdout, str) else e.stdout.decode()
                logger.error(f"FFmpeg stdout: {stdout_msg}")
            raise AudioManagerError(f"Failed to convert to ulaw format: {error_msg}")
        except FileNotFoundError:
            logger.error("FFmpeg not found - cannot convert to ulaw")
            raise AudioManagerError("FFmpeg is required for ulaw format conversion")
        finally:
            temp_wav_path.unlink(missing_ok=True)

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
            
            # Export combined audio in the configured format
            if self.config.tts.output_format.lower() in ["ulaw", "mulaw", "ul"]:
                # For ulaw, export as raw and convert
                self._export_to_ulaw(combined, combined_path)
            else:
                combined.export(str(combined_path), format=self.config.tts.output_format)
            
            # Ensure asterisk user can read the file
            try:
                os.chmod(combined_path, 0o644)
                logger.debug(f"Set permissions on combined audio file: {combined_path}")
            except Exception as e:
                logger.warning(f"Failed to set permissions on combined audio file: {e}")
            
            # Verify the file exists and has content
            if not combined_path.exists():
                logger.error(f"Combined audio file with suffix does not exist after creation: {combined_path}")
                return None
            if combined_path.stat().st_size == 0:
                logger.error(f"Combined audio file with suffix is empty after creation: {combined_path}")
                return None
            
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
            
            # Ensure "County" is included in TTS text (even if not in county_name)
            # This ensures the audio says "Brazoria County" instead of just "Brazoria"
            tts_text = county_name.strip()
            if not tts_text.lower().endswith("county"):
                tts_text = f"{tts_text} County"
            
            # Generate audio using TTS (says full county name with "County" suffix)
            engine_used, audio_path = self._synthesize_with_optional_fallback(
                tts_text,
                output_path,
                allow_fallback=True,
            )
            
            # Validate generated audio
            if not engine_used.validate_audio_file(audio_path):
                logger.error(f"Generated county audio file is invalid: {audio_path}")
                return None
            
            # Get audio duration
            duration = engine_used.get_audio_duration(audio_path)
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
