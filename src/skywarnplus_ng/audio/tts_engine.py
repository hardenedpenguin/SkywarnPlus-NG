"""
Text-to-Speech engine using gTTS.
"""

import logging
import tempfile
from pathlib import Path
from typing import Optional
from gtts import gTTS
from pydub import AudioSegment
from pydub.utils import which

from ..core.config import TTSConfig

logger = logging.getLogger(__name__)


class TTSEngineError(Exception):
    """TTS engine error."""

    pass


class GTTSEngine:
    """Google Text-to-Speech engine."""

    def __init__(self, config: TTSConfig):
        """
        Initialize gTTS engine.

        Args:
            config: TTS configuration
        """
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate TTS configuration."""
        if self.config.engine != "gtts":
            raise TTSEngineError(f"Unsupported TTS engine: {self.config.engine}")
        
        if not self.config.language:
            raise TTSEngineError("Language code is required")
        
        if not self.config.tld:
            raise TTSEngineError("Top-level domain is required")

    def is_available(self) -> bool:
        """
        Check if gTTS is available.

        Returns:
            True if gTTS is available
        """
        try:
            # Test gTTS availability by creating a test instance
            test_tts = gTTS(text="test", lang=self.config.language, tld=self.config.tld, slow=self.config.slow)
            return True
        except Exception as e:
            logger.error(f"gTTS not available: {e}")
            return False

    def synthesize(self, text: str, output_path: Path) -> Path:
        """
        Synthesize text to speech and save to file.

        Args:
            text: Text to synthesize
            output_path: Path to save audio file

        Returns:
            Path to the generated audio file

        Raises:
            TTSEngineError: If synthesis fails
        """
        if not text.strip():
            raise TTSEngineError("Text cannot be empty")

        logger.debug(f"Synthesizing text: '{text[:50]}...'")

        try:
            # Create gTTS instance
            tts = gTTS(
                text=text,
                lang=self.config.language,
                tld=self.config.tld,
                slow=self.config.slow
            )

            # Create temporary file for MP3 output
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_mp3:
                temp_mp3_path = Path(temp_mp3.name)

            # Generate MP3 audio
            tts.save(str(temp_mp3_path))
            logger.debug(f"Generated MP3 audio: {temp_mp3_path}")

            # Convert MP3 to desired format
            final_path = self._convert_audio(temp_mp3_path, output_path)
            
            # Clean up temporary MP3 file
            temp_mp3_path.unlink(missing_ok=True)

            logger.info(f"Successfully synthesized audio: {final_path}")
            return final_path

        except Exception as e:
            logger.error(f"Failed to synthesize text: {e}")
            raise TTSEngineError(f"Synthesis failed: {e}") from e

    def _convert_audio(self, input_path: Path, output_path: Path) -> Path:
        """
        Convert audio file to desired format.

        Args:
            input_path: Input audio file path
            output_path: Desired output path

        Returns:
            Path to converted audio file
        """
        try:
            # Load audio with pydub
            audio = AudioSegment.from_mp3(str(input_path))
            
            # Convert to mono if needed
            if audio.channels > 1:
                audio = audio.set_channels(1)
                logger.debug("Converted to mono")
            
            # Resample to desired sample rate
            if audio.frame_rate != self.config.sample_rate:
                audio = audio.set_frame_rate(self.config.sample_rate)
                logger.debug(f"Resampled to {self.config.sample_rate} Hz")
            
            # Normalize audio
            audio = audio.normalize()
            
            # Export to desired format
            if self.config.output_format.lower() == "wav":
                audio.export(str(output_path), format="wav")
            elif self.config.output_format.lower() == "mp3":
                audio.export(str(output_path), format="mp3", bitrate=f"{self.config.bit_rate}k")
            elif self.config.output_format.lower() in ["ulaw", "mulaw", "ul"]:
                # Export to ulaw format using WAV intermediate + ffmpeg conversion
                # First ensure we're at 8000Hz mono (required for ulaw)
                audio = audio.set_frame_rate(8000).set_channels(1)
                
                # Export as WAV first, then convert to ulaw using ffmpeg
                import tempfile
                import subprocess
                
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                    temp_wav_path = Path(temp_wav.name)
                
                # Export as WAV (pydub can do this reliably)
                audio.export(str(temp_wav_path), format="wav")
                
                # Convert WAV to ulaw using ffmpeg
                try:
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
                        raise TTSEngineError(f"FFmpeg did not create output file: {output_path}")
                    
                    file_size = output_path.stat().st_size
                    if file_size == 0:
                        logger.error(f"FFmpeg created empty file: {output_path}")
                        raise TTSEngineError(f"FFmpeg created empty ulaw file: {output_path}")
                    
                    logger.debug(f"Converted to ulaw: {output_path} ({file_size} bytes)")
                except subprocess.CalledProcessError as e:
                    error_msg = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else 'Unknown error')
                    logger.error(f"FFmpeg conversion to ulaw failed: {error_msg}")
                    if e.stdout:
                        stdout_msg = e.stdout if isinstance(e.stdout, str) else e.stdout.decode()
                        logger.error(f"FFmpeg stdout: {stdout_msg}")
                    raise TTSEngineError(f"Failed to convert to ulaw format: {error_msg}")
                except FileNotFoundError:
                    logger.error("FFmpeg not found - cannot convert to ulaw")
                    raise TTSEngineError("FFmpeg is required for ulaw format conversion")
                finally:
                    temp_wav_path.unlink(missing_ok=True)
            else:
                # Default to WAV
                output_path = output_path.with_suffix(".wav")
                audio.export(str(output_path), format="wav")
            
            logger.debug(f"Converted audio: {input_path} -> {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Failed to convert audio: {e}")
            raise TTSEngineError(f"Audio conversion failed: {e}") from e

    def get_audio_duration(self, audio_path: Path) -> float:
        """
        Get duration of audio file in seconds.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds
        """
        try:
            # Handle ulaw files specially
            if audio_path.suffix.lower() in ['.ulaw', '.ul']:
                # For ulaw, use ffprobe to get duration
                import subprocess
                try:
                    result = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=True
                    )
                    duration = float(result.stdout.strip())
                    return duration
                except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
                    logger.warning(f"Failed to get ulaw duration with ffprobe: {e}, using file size estimate")
                    # Fallback: estimate from file size (ulaw is 8000 bytes/second at 8kHz)
                    file_size = audio_path.stat().st_size
                    return file_size / 8000.0
            
            # For other formats, use pydub
            audio = AudioSegment.from_file(str(audio_path))
            return len(audio) / 1000.0  # Convert milliseconds to seconds
        except Exception as e:
            logger.error(f"Failed to get audio duration: {e}")
            return 0.0

    def validate_audio_file(self, audio_path: Path) -> bool:
        """
        Validate that audio file exists and is readable.

        Args:
            audio_path: Path to audio file

        Returns:
            True if audio file is valid
        """
        if not audio_path.exists():
            logger.error(f"Audio file does not exist: {audio_path}")
            return False
        
        try:
            # For ulaw files, check with ffprobe
            if audio_path.suffix.lower() in ['.ulaw', '.ul']:
                import subprocess
                try:
                    result = subprocess.run(
                        ["ffprobe", "-v", "error", str(audio_path)],
                        capture_output=True,
                        timeout=10,
                        check=True
                    )
                    return True
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # If ffprobe fails, check if file exists and has size > 0
                    return audio_path.stat().st_size > 0
            
            # For other formats, try to load with pydub
            AudioSegment.from_file(str(audio_path))
            return True
        except Exception as e:
            logger.error(f"Invalid audio file {audio_path}: {e}")
            return False