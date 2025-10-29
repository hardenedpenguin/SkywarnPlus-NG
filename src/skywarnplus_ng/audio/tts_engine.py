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
            # Try to load the audio file
            AudioSegment.from_file(str(audio_path))
            return True
        except Exception as e:
            logger.error(f"Invalid audio file {audio_path}: {e}")
            return False