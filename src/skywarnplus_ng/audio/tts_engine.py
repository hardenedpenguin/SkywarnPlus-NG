"""
Text-to-Speech engine using gTTS and Piper TTS.
"""

import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .audio_utils import AudioSegment

from ..core.config import TTSConfig

logger = logging.getLogger(__name__)

# Try to import gTTS
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logger.warning("gTTS not available")

# Try to import Piper
try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    logger.warning("Piper TTS not available (pip install piper-tts)")
    if TYPE_CHECKING:
        from piper import PiperVoice  # type: ignore
    else:
        PiperVoice = None  # type: ignore


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
        
        if not GTTS_AVAILABLE:
            raise TTSEngineError("gTTS library is not installed. Install with: pip install gtts")
        
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
            # Load audio with AudioSegment (replaces pydub)
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
                probe_cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-f", "mulaw",
                    "-ar", "8000",
                    "-ac", "1",
                    "-show_entries", "stream=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ]
                try:
                    result = subprocess.run(
                        probe_cmd,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=True,
                    )
                    output = result.stdout.strip()
                    if output:
                        duration = float(output)
                        return duration
                except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
                    logger.warning(f"Failed to get ulaw duration with ffprobe: {e}, using file size estimate")
                    # Fallback: estimate from file size (ulaw is 8000 bytes/second at 8kHz)
                    file_size = audio_path.stat().st_size
                    return file_size / 8000.0
            
            # For other formats, use AudioSegment
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


class PiperTSEngine:
    """Piper Text-to-Speech engine."""

    def __init__(self, config: TTSConfig):
        """
        Initialize Piper TTS engine.

        Args:
            config: TTS configuration
        """
        self.config = config
        self._validate_config()
        self.voice: Optional[PiperVoice] = None
        self._load_voice()

    def _validate_config(self) -> None:
        """Validate TTS configuration."""
        if self.config.engine != "piper":
            raise TTSEngineError(f"Unsupported TTS engine: {self.config.engine}")
        
        if not PIPER_AVAILABLE:
            raise TTSEngineError("Piper TTS library is not installed. Install with: pip install piper-tts")
        
        if not self.config.model_path:
            raise TTSEngineError("Model path is required for Piper TTS")
        
        model_path = Path(self.config.model_path)
        if not model_path.exists():
            raise TTSEngineError(f"Piper model file not found: {model_path}")
        
        # Check for config file (usually .onnx.json)
        config_path = model_path.with_suffix(model_path.suffix + ".json")
        if not config_path.exists():
            logger.warning(f"Piper config file not found: {config_path}, will try to load without explicit config")

    def _load_voice(self) -> None:
        """Load Piper voice model."""
        try:
            model_path = Path(self.config.model_path)
            config_path = model_path.with_suffix(model_path.suffix + ".json")
            
            if config_path.exists():
                self.voice = PiperVoice.load(str(model_path), config_path=str(config_path))
            else:
                # Try loading without explicit config (Piper can sometimes auto-detect)
                self.voice = PiperVoice.load(str(model_path))
            
            logger.debug(f"Loaded Piper voice model: {model_path}")
        except Exception as e:
            logger.error(f"Failed to load Piper voice model: {e}")
            raise TTSEngineError(f"Failed to load Piper voice model: {e}") from e

    def is_available(self) -> bool:
        """
        Check if Piper TTS is available.

        Returns:
            True if Piper TTS is available
        """
        try:
            if not PIPER_AVAILABLE:
                logger.warning("Piper TTS library not installed")
                return False
            
            if self.voice is None:
                logger.warning("Piper voice model not loaded")
                return False
            
            # Skip the test synthesis to avoid hangs during initialization
            # Just check if voice is loaded
            # NOTE: We skip the test synthesis because it can hang indefinitely
            # if there are issues with the model or library. The actual synthesis
            # will fail fast if there's a real problem.
            logger.debug("Piper TTS appears to be available (voice model loaded)")
            return True
        except Exception as e:
            logger.error(f"Piper TTS not available: {e}")
            return False

    def _synthesize_to_wav(self, text: str, output_path: Path) -> None:
        """
        Synthesize text to WAV format using Piper.

        Args:
            text: Text to synthesize
            output_path: Path to save WAV file
        """
        if self.voice is None:
            raise TTSEngineError("Piper voice model not loaded")
        
        try:
            # Piper synthesizes to WAV format
            # Check if the output file exists and is writable
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Open file in binary write mode
            with open(output_path, "wb") as audio_file:
                try:
                    # Try calling synthesize - check API signature
                    # Some versions of piper-tts use different parameter names
                    import inspect
                    sig = inspect.signature(self.voice.synthesize)
                    params = list(sig.parameters.keys())
                    
                    logger.debug(f"Piper synthesize signature: {params}")
                    
                    # Try calling with common parameter combinations
                    if 'length_scale' in params:
                        self.voice.synthesize(text, audio_file, length_scale=self.config.speed)
                    elif 'speed' in params:
                        self.voice.synthesize(text, audio_file, speed=self.config.speed)
                    else:
                        # No speed parameter - just synthesize
                        self.voice.synthesize(text, audio_file)
                        
                except TypeError as e:
                    # If parameter names don't match, try with just text and file
                    logger.debug(f"TypeError with parameters, trying basic call: {e}")
                    try:
                        self.voice.synthesize(text, audio_file)
                    except Exception as e2:
                        logger.error(f"Piper synthesize failed even with basic call: {e2}")
                        raise TTSEngineError(f"Piper synthesis failed: {e2}") from e2
                except Exception as e:
                    logger.error(f"Piper synthesis failed with exception: {e}")
                    logger.error(f"Exception type: {type(e).__name__}")
                    raise TTSEngineError(f"Piper synthesis failed: {e}") from e
            
            # Verify the file was created and has content
            if not output_path.exists():
                raise TTSEngineError(f"Piper did not create output file: {output_path}")
            
            file_size = output_path.stat().st_size
            if file_size == 0:
                raise TTSEngineError(f"Piper created empty output file: {output_path}")
            
            logger.debug(f"Piper synthesized {file_size} bytes to {output_path}")
            
        except TTSEngineError:
            raise
        except Exception as e:
            logger.error(f"Piper synthesis failed: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise TTSEngineError(f"Piper synthesis failed: {e}") from e

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

        logger.debug(f"Synthesizing text with Piper: '{text[:50]}...'")

        try:
            # Piper outputs WAV format, so we need to convert if needed
            if self.config.output_format.lower() in ["wav"]:
                # Direct WAV output
                self._synthesize_to_wav(text, output_path)
                logger.info(f"Successfully synthesized audio: {output_path}")
                return output_path
            else:
                # Need to convert from WAV to desired format
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                    temp_wav_path = Path(temp_wav.name)
                
                try:
                    # Synthesize to temporary WAV file
                    self._synthesize_to_wav(text, temp_wav_path)
                    
                    # Convert to desired format
                    final_path = self._convert_audio(temp_wav_path, output_path)
                    logger.info(f"Successfully synthesized audio: {final_path}")
                    return final_path
                finally:
                    temp_wav_path.unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Failed to synthesize text: {e}")
            raise TTSEngineError(f"Synthesis failed: {e}") from e

    def _convert_audio(self, input_path: Path, output_path: Path) -> Path:
        """
        Convert audio file to desired format.

        Args:
            input_path: Input audio file path (WAV from Piper)
            output_path: Desired output path

        Returns:
            Path to converted audio file
        """
        try:
            # Load audio (Piper outputs WAV)
            audio = AudioSegment.from_wav(str(input_path))
            
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
            
            # For other formats, use AudioSegment
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