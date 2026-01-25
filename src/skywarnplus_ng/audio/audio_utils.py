"""
Modern audio processing utilities using soundfile + numpy + scipy.

This module replaces pydub with a more modern, actively maintained stack.
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import soundfile as sf
from scipy import signal

logger = logging.getLogger(__name__)


class AudioData:
    """
    Audio data container similar to pydub's AudioSegment.
    
    This class provides a pydub-like interface using soundfile and numpy.
    """
    
    def __init__(self, data: np.ndarray, sample_rate: int = 8000, channels: int = 1):
        """
        Initialize audio data.
        
        Args:
            data: Audio data as numpy array (1D for mono, 2D for stereo)
            sample_rate: Sample rate in Hz (must be positive)
            channels: Number of audio channels (1 or 2)
            
        Raises:
            ValueError: If parameters are invalid
            TypeError: If data is not a numpy array
        """
        if not isinstance(data, np.ndarray):
            raise TypeError(f"data must be a numpy array, got {type(data)}")
        
        if len(data) == 0:
            raise ValueError("Audio data cannot be empty")
        
        if sample_rate <= 0:
            raise ValueError(f"Sample rate must be positive, got {sample_rate}")
        
        if channels not in (1, 2):
            raise ValueError(f"Channels must be 1 or 2, got {channels}")
        
        # Validate data shape matches channels
        if len(data.shape) > 1:
            if data.shape[1] != channels:
                raise ValueError(
                    f"Data shape {data.shape} does not match channels={channels}. "
                    f"Expected shape: (samples,) for mono or (samples, {channels}) for stereo"
                )
        elif channels == 2:
            # Mono data but channels=2, will be converted in set_channels
            pass
        
        self.data = data
        self.sample_rate = sample_rate
        self.channels = channels
        
        # Ensure data is float32 for compatibility
        if self.data.dtype != np.float32:
            self.data = self.data.astype(np.float32)
    
    @property
    def frame_rate(self) -> int:
        """Get frame rate (sample rate)."""
        return self.sample_rate
    
    @property
    def duration_seconds(self) -> float:
        """Get duration in seconds."""
        return len(self.data) / self.sample_rate
    
    @property
    def duration_ms(self) -> int:
        """Get duration in milliseconds."""
        return int(self.duration_seconds * 1000)
    
    def __len__(self) -> int:
        """Get length in milliseconds (for compatibility with pydub)."""
        return self.duration_ms
    
    def set_frame_rate(self, target_rate: int) -> 'AudioData':
        """
        Resample audio to target sample rate.
        
        Args:
            target_rate: Target sample rate in Hz (must be positive)
            
        Returns:
            New AudioData instance with resampled audio
            
        Raises:
            ValueError: If target_rate is invalid
        """
        if target_rate <= 0:
            raise ValueError(f"Target sample rate must be positive, got {target_rate}")
        
        if target_rate == self.sample_rate:
            return self
        
        # Calculate number of samples for target rate
        num_samples = int(len(self.data) * target_rate / self.sample_rate)
        
        if num_samples == 0:
            raise ValueError(f"Cannot resample: resulting audio would be empty (target rate {target_rate}Hz too low)")
        
        # Resample using scipy
        try:
            resampled = signal.resample(self.data, num_samples)
            logger.debug(f"Resampled audio from {self.sample_rate}Hz to {target_rate}Hz ({len(self.data)} -> {num_samples} samples)")
            return AudioData(resampled, target_rate, self.channels)
        except Exception as e:
            raise RuntimeError(f"Failed to resample audio: {e}") from e
    
    def set_channels(self, target_channels: int) -> 'AudioData':
        """
        Convert audio to target number of channels.
        
        Args:
            target_channels: Target number of channels (1 for mono, 2 for stereo)
            
        Returns:
            New AudioData instance with converted channels
        """
        if target_channels == self.channels:
            return self
        
        if target_channels == 1:
            # Convert to mono (average channels if stereo)
            if len(self.data.shape) > 1:
                mono_data = np.mean(self.data, axis=1)
            else:
                mono_data = self.data
            return AudioData(mono_data, self.sample_rate, 1)
        elif target_channels == 2:
            # Convert to stereo (duplicate mono channel)
            if len(self.data.shape) == 1:
                stereo_data = np.column_stack([self.data, self.data])
            else:
                stereo_data = self.data
            return AudioData(stereo_data, self.sample_rate, 2)
        else:
            raise ValueError(f"Unsupported channel count: {target_channels}")
    
    def normalize(self) -> 'AudioData':
        """
        Normalize audio to prevent clipping.
        
        Returns:
            New AudioData instance with normalized audio
        """
        data = self.data.copy()
        
        # Find maximum absolute value
        max_val = np.max(np.abs(data))
        
        if max_val > 0:
            # Normalize to [-1, 1] range
            data = data / max_val
        
        return AudioData(data, self.sample_rate, self.channels)
    
    def __add__(self, other) -> 'AudioData':
        """
        Concatenate two AudioData instances.
        
        Args:
            other: Another AudioData instance or silence duration in ms
            
        Returns:
            New AudioData instance with concatenated audio
        """
        if isinstance(other, int):
            # Generate silence
            other = AudioData.silent(duration=other, sample_rate=self.sample_rate)
        
        if not isinstance(other, AudioData):
            raise TypeError(f"Cannot add AudioData with {type(other)}")
        
        # Ensure same sample rate and channels
        if other.sample_rate != self.sample_rate:
            other = other.set_frame_rate(self.sample_rate)
        if other.channels != self.channels:
            other = other.set_channels(self.channels)
        
        # Concatenate - handle both 1D and 2D arrays
        if len(self.data.shape) == 1 and len(other.data.shape) == 1:
            combined_data = np.concatenate([self.data, other.data])
        elif len(self.data.shape) == 2 and len(other.data.shape) == 2:
            combined_data = np.concatenate([self.data, other.data], axis=0)
        else:
            # Mixed shapes - convert both to same shape
            if len(self.data.shape) == 1:
                self_data = self.data.reshape(-1, 1)
            else:
                self_data = self.data
            if len(other.data.shape) == 1:
                other_data = other.data.reshape(-1, 1)
            else:
                other_data = other.data
            combined_data = np.concatenate([self_data, other_data], axis=0)
        
        return AudioData(combined_data, self.sample_rate, self.channels)
    
    def export(self, file_path: str, format: Optional[str] = None) -> None:
        """
        Export audio to file.
        
        Args:
            file_path: Output file path
            format: Output format (if None, inferred from extension)
        """
        output_path = Path(file_path)
        
        # Determine format from extension if not provided
        if format is None:
            ext = output_path.suffix.lower()
            if ext in ['.wav', '.wave']:
                format = 'wav'
            elif ext in ['.mp3']:
                format = 'mp3'
            elif ext in ['.ulaw', '.ul']:
                format = 'ulaw'
            else:
                format = 'wav'  # Default to WAV
        
        # Ensure mono for export
        if self.channels > 1:
            audio = self.set_channels(1)
        else:
            audio = self
        
        if format.lower() in ['ulaw', 'mulaw', 'ul']:
            # Export to ulaw using ffmpeg
            self._export_to_ulaw(audio, output_path)
        elif format.lower() == 'wav':
            # Export as WAV using soundfile
            sf.write(str(output_path), audio.data, audio.sample_rate)
        elif format.lower() == 'mp3':
            # Export as MP3 using ffmpeg (soundfile doesn't support MP3)
            self._export_to_mp3(audio, output_path)
        else:
            # Default to WAV
            sf.write(str(output_path), audio.data, audio.sample_rate)
    
    def _export_to_ulaw(self, audio: 'AudioData', output_path: Path) -> None:
        """
        Export audio to ulaw format using ffmpeg.
        
        Args:
            audio: AudioData to export
            output_path: Output file path
            
        Raises:
            RuntimeError: If conversion fails or ffmpeg is not available
        """
        import tempfile
        
        # Create temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_path = Path(temp_wav.name)
        
        try:
            # Export as WAV first
            sf.write(str(temp_wav_path), audio.data, audio.sample_rate)
            
            # Convert WAV to ulaw using ffmpeg
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(temp_wav_path),
                    "-ar", str(audio.sample_rate),
                    "-ac", "1",
                    "-f", "mulaw",
                    str(output_path)
                ],
                check=True,
                capture_output=True,
                timeout=30,
                text=True
            )
            
            # Verify file was created (with retry for filesystem sync)
            import time
            for _ in range(5):  # Retry up to 5 times
                if output_path.exists() and output_path.stat().st_size > 0:
                    break
                time.sleep(0.05)  # 50ms delay
            
            if not output_path.exists():
                raise RuntimeError(
                    f"FFmpeg did not create output file: {output_path}. "
                    f"Check disk space and permissions."
                )
            
            if output_path.stat().st_size == 0:
                raise RuntimeError(
                    f"FFmpeg created empty file: {output_path}. "
                    f"The input audio may be invalid or corrupted."
                )
            
            logger.debug(f"Exported audio to ulaw: {output_path} ({output_path.stat().st_size} bytes)")
                
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else 'Unknown error')
            raise RuntimeError(
                f"FFmpeg conversion to ulaw failed: {error_msg}. "
                f"Ensure ffmpeg is properly installed and the input audio is valid."
            ) from e
        except FileNotFoundError:
            raise RuntimeError(
                "FFmpeg is required for ulaw format conversion. "
                "Please install ffmpeg: sudo apt-get install ffmpeg (Debian/Ubuntu) "
                "or visit https://ffmpeg.org/download.html"
            )
        finally:
            temp_wav_path.unlink(missing_ok=True)
    
    def _export_to_mp3(self, audio: 'AudioData', output_path: Path) -> None:
        """Export audio to MP3 format using ffmpeg."""
        import tempfile
        
        # Create temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_path = Path(temp_wav.name)
        
        try:
            # Export as WAV first
            sf.write(str(temp_wav_path), audio.data, audio.sample_rate)
            
            # Convert WAV to MP3 using ffmpeg
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(temp_wav_path),
                    "-ar", str(audio.sample_rate),
                    "-ac", "1",
                    "-codec:a", "libmp3lame",
                    "-b:a", "128k",
                    str(output_path)
                ],
                check=True,
                capture_output=True,
                timeout=30,
                text=True
            )
            
            # Verify file was created
            if not output_path.exists():
                raise RuntimeError(f"FFmpeg did not create output file: {output_path}")
                
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else 'Unknown error')
            raise RuntimeError(f"FFmpeg conversion to MP3 failed: {error_msg}")
        except FileNotFoundError:
            raise RuntimeError("FFmpeg is required for MP3 format conversion")
        finally:
            temp_wav_path.unlink(missing_ok=True)
    
    @staticmethod
    def silent(duration: int, sample_rate: int = 8000) -> 'AudioData':
        """
        Generate silence audio.
        
        Args:
            duration: Duration in milliseconds (must be positive)
            sample_rate: Sample rate in Hz (must be positive)
            
        Returns:
            AudioData instance with silence
            
        Raises:
            ValueError: If duration or sample_rate is invalid
        """
        if duration < 0:
            raise ValueError(f"Duration must be non-negative, got {duration}")
        if sample_rate <= 0:
            raise ValueError(f"Sample rate must be positive, got {sample_rate}")
        
        num_samples = int(duration * sample_rate / 1000)
        if num_samples == 0:
            # AudioData rejects empty arrays; use 1 sample to avoid ValueError
            num_samples = 1
        silence_data = np.zeros(num_samples, dtype=np.float32)
        return AudioData(silence_data, sample_rate, 1)
    
    @staticmethod
    def empty() -> 'AudioData':
        """Create empty audio data."""
        return AudioData(np.array([], dtype=np.float32), 8000, 1)
    
    @staticmethod
    def from_wav(file_path: str) -> 'AudioData':
        """
        Load audio from WAV file.
        
        Args:
            file_path: Path to WAV file
            
        Returns:
            AudioData instance
            
        Raises:
            FileNotFoundError: If file does not exist
            RuntimeError: If file cannot be read or is invalid
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        
        if not path.is_file():
            raise RuntimeError(f"Path is not a file: {file_path}")
        
        try:
            data, sample_rate = sf.read(str(path))
            
            # Determine channels
            if len(data.shape) > 1:
                channels = data.shape[1]
            else:
                channels = 1
            
            if len(data) == 0:
                raise RuntimeError(f"Audio file is empty: {file_path}")
            
            logger.debug(f"Loaded WAV file: {file_path} ({len(data)} samples, {sample_rate}Hz, {channels} channels)")
            return AudioData(data, sample_rate, channels)
        except sf.LibsndfileError as e:
            raise RuntimeError(f"Failed to read WAV file {file_path}: {e}. The file may be corrupted or in an unsupported format.") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error loading WAV file {file_path}: {e}") from e
    
    @staticmethod
    def from_mp3(file_path: str) -> 'AudioData':
        """
        Load audio from MP3 file using ffmpeg.
        
        Args:
            file_path: Path to MP3 file
            
        Returns:
            AudioData instance
            
        Raises:
            FileNotFoundError: If file does not exist
            RuntimeError: If conversion fails or ffmpeg is not available
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"MP3 file not found: {file_path}")
        
        if not path.is_file():
            raise RuntimeError(f"Path is not a file: {file_path}")
        
        import tempfile
        
        # Create temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_path = Path(temp_wav.name)
        
        try:
            # Convert MP3 to WAV using ffmpeg
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(file_path),
                    str(temp_wav_path)
                ],
                check=True,
                capture_output=True,
                timeout=30,
                text=True
            )
            
            # Verify output file was created
            if not temp_wav_path.exists():
                raise RuntimeError(f"FFmpeg did not create output file when converting MP3: {file_path}")
            
            # Load the converted WAV file
            logger.debug(f"Converted MP3 to WAV: {file_path}")
            return AudioData.from_wav(str(temp_wav_path))
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else 'Unknown error')
            raise RuntimeError(
                f"Failed to convert MP3 file {file_path} to WAV. "
                f"FFmpeg error: {error_msg}. "
                f"Ensure the file is a valid MP3 and ffmpeg is properly installed."
            ) from e
        except FileNotFoundError:
            raise RuntimeError(
                "FFmpeg is required for MP3 file loading. "
                "Please install ffmpeg: sudo apt-get install ffmpeg (Debian/Ubuntu) "
                "or visit https://ffmpeg.org/download.html"
            )
        finally:
            temp_wav_path.unlink(missing_ok=True)
    
    @staticmethod
    def from_file(file_path: str) -> 'AudioData':
        """
        Load audio from file (auto-detect format).
        
        Args:
            file_path: Path to audio file
            
        Returns:
            AudioData instance
            
        Raises:
            FileNotFoundError: If file does not exist
            RuntimeError: If file cannot be read or format is unsupported
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        
        ext = path.suffix.lower()
        
        if ext == '.wav':
            return AudioData.from_wav(str(path))
        elif ext == '.mp3':
            return AudioData.from_mp3(str(path))
        elif ext in ['.ulaw', '.ul']:
            # Convert ulaw to WAV first
            return AudioData._from_ulaw(str(path))
        else:
            # Try soundfile first (supports many formats)
            try:
                data, sample_rate = sf.read(str(path))
                if len(data.shape) > 1:
                    channels = data.shape[1]
                else:
                    channels = 1
                logger.debug(f"Loaded audio file via soundfile: {file_path} (format: {ext})")
                return AudioData(data, sample_rate, channels)
            except sf.LibsndfileError as e:
                # Soundfile doesn't support this format, try ffmpeg
                logger.debug(f"Soundfile cannot read {ext} format, trying ffmpeg conversion")
                try:
                    return AudioData._from_ulaw(str(path))
                except Exception as e2:
                    raise RuntimeError(
                        f"Unable to load audio file {file_path}. "
                        f"Format '{ext}' is not supported. "
                        f"Supported formats: WAV, MP3, ulaw, and formats supported by soundfile/libsndfile. "
                        f"Error: {e2}"
                    ) from e2
            except Exception as e:
                raise RuntimeError(f"Failed to load audio file {file_path}: {e}") from e
    
    @staticmethod
    def _from_ulaw(file_path: str) -> 'AudioData':
        """
        Load audio from ulaw file using ffmpeg.
        
        Args:
            file_path: Path to ulaw file
            
        Returns:
            AudioData instance
            
        Raises:
            FileNotFoundError: If file does not exist
            RuntimeError: If conversion fails or ffmpeg is not available
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"ulaw file not found: {file_path}")
        
        import tempfile
        
        # Create temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_path = Path(temp_wav.name)
        
        try:
            # Convert ulaw to WAV using ffmpeg
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "mulaw",
                    "-ar", "8000",
                    "-ac", "1",
                    "-i", str(file_path),
                    str(temp_wav_path)
                ],
                check=True,
                capture_output=True,
                timeout=30,
                text=True
            )
            
            # Verify output file was created
            if not temp_wav_path.exists():
                raise RuntimeError(f"FFmpeg did not create output file when converting ulaw: {file_path}")
            
            # Load the converted WAV file
            logger.debug(f"Converted ulaw to WAV: {file_path}")
            return AudioData.from_wav(str(temp_wav_path))
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else 'Unknown error')
            raise RuntimeError(
                f"Failed to convert ulaw file {file_path} to WAV. "
                f"FFmpeg error: {error_msg}. "
                f"Ensure the file is a valid ulaw file and ffmpeg is properly installed."
            ) from e
        except FileNotFoundError:
            raise RuntimeError(
                "FFmpeg is required for ulaw file loading. "
                "Please install ffmpeg: sudo apt-get install ffmpeg (Debian/Ubuntu) "
                "or visit https://ffmpeg.org/download.html"
            )
        finally:
            temp_wav_path.unlink(missing_ok=True)


# Compatibility alias for pydub's AudioSegment
AudioSegment = AudioData
