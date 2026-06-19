"""
Text-to-Speech engines: asl-tts (ASL3 Piper CLI) and gTTS fallback.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from .audio_utils import AudioSegment
from ..core.config import TTSConfig

logger = logging.getLogger(__name__)

try:
    from gtts import gTTS

    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logger.warning("gTTS not available")


class TTSEngineError(Exception):
    """TTS engine error."""

    pass


def _resolve_asl_tts_binary(config: TTSConfig) -> Path:
    raw = (config.asl_tts_binary or "asl-tts").strip()
    path = Path(raw)
    if path.is_file():
        return path
    found = shutil.which(raw)
    if found:
        return Path(found)
    raise TTSEngineError(
        f"asl-tts binary not found: {raw!r}. Install the asl3-tts package (provides asl-tts)."
    )


class AslTTSEngine:
    """ASL3 asl-tts CLI wrapper (Piper voices under /var/lib/piper-tts)."""

    def __init__(self, config: TTSConfig):
        self.config = config
        self.binary = _resolve_asl_tts_binary(config)
        self.voices_dir = Path(config.voices_dir or "/var/lib/piper-tts")
        self.voice = (config.voice or "en_US-amy-low.onnx").strip()
        self.node_number = int(config.node_number or 1)
        self._validate_config()

    def _validate_config(self) -> None:
        engine = (self.config.engine or "").lower().replace("_", "-")
        if engine not in ("asl-tts", "asltts"):
            raise TTSEngineError(f"Unsupported TTS engine: {self.config.engine}")

        if self.node_number <= 0:
            raise TTSEngineError("audio.tts.node_number must be a positive AllStar node number")

        if not self.voice:
            raise TTSEngineError(
                "audio.tts.voice is required for asl-tts (e.g. en_US-amy-low.onnx)"
            )

        model_path = self.voices_dir / self.voice
        if not model_path.is_file():
            raise TTSEngineError(
                f"Piper voice not found: {model_path}. "
                "Install voices with asl3-tts or place .onnx + .onnx.json in "
                f"{self.voices_dir}."
            )

    def is_available(self) -> bool:
        try:
            if not self.binary.is_file():
                return False
            model_path = self.voices_dir / self.voice
            return model_path.is_file()
        except Exception as exc:
            logger.error("asl-tts not available: %s", exc)
            return False

    def synthesize(self, text: str, output_path: Path) -> Path:
        if not text.strip():
            raise TTSEngineError("Text cannot be empty")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("Synthesizing with asl-tts: %r", text[:50])
        logger.info("asl-tts voice: %s", self.voice)

        want_ulaw = self.config.output_format.lower() in ("ulaw", "mulaw", "ul")
        final_path = output_path
        if want_ulaw and final_path.suffix.lower() not in (".ulaw", ".ul"):
            final_path = final_path.with_suffix(".ulaw")

        with tempfile.TemporaryDirectory(prefix="skywarnplus-ng-tts-") as tmp:
            ul_base = Path(tmp) / "tts_out"
            cmd = [
                str(self.binary),
                "-n",
                str(self.node_number),
                "-t",
                text,
                "-v",
                self.voice,
                "-f",
                str(ul_base),
            ]
            try:
                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or exc.stdout or str(exc)).strip()
                raise TTSEngineError(f"asl-tts failed: {stderr}") from exc
            except subprocess.TimeoutExpired as exc:
                raise TTSEngineError("asl-tts timed out") from exc
            except FileNotFoundError as exc:
                raise TTSEngineError(f"asl-tts binary missing: {self.binary}") from exc

            if result.stderr:
                logger.debug("asl-tts stderr: %s", result.stderr.strip())

            ul_path = ul_base.with_suffix(".ul")
            if not ul_path.is_file() or ul_path.stat().st_size == 0:
                raise TTSEngineError("asl-tts did not produce output (.ul)")

            if want_ulaw:
                shutil.copy2(ul_path, final_path)
                logger.info("Successfully synthesized audio: %s", final_path)
                return final_path

            return self._convert_ul_to_format(ul_path, output_path)

    def _convert_ul_to_format(self, ul_path: Path, output_path: Path) -> Path:
        fmt = self.config.output_format.lower()
        if fmt in ("ulaw", "mulaw", "ul"):
            shutil.copy2(ul_path, output_path)
            return output_path

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_path = Path(temp_wav.name)

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "mulaw",
                    "-ar",
                    "8000",
                    "-ac",
                    "1",
                    "-i",
                    str(ul_path),
                    str(temp_wav_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            audio = AudioSegment.from_wav(str(temp_wav_path))
            if audio.frame_rate != self.config.sample_rate:
                audio = audio.set_frame_rate(self.config.sample_rate)
            if fmt == "wav":
                audio.export(str(output_path), format="wav")
            elif fmt == "mp3":
                audio.export(str(output_path), format="mp3", bitrate=f"{self.config.bit_rate}k")
            else:
                output_path = output_path.with_suffix(".wav")
                audio.export(str(output_path), format="wav")
            logger.info("Successfully synthesized audio: %s", output_path)
            return output_path
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise TTSEngineError(f"Failed to convert asl-tts output: {stderr}") from exc
        except FileNotFoundError as exc:
            raise TTSEngineError("ffmpeg is required to convert asl-tts output") from exc
        finally:
            temp_wav_path.unlink(missing_ok=True)

    def get_audio_duration(self, audio_path: Path) -> float:
        try:
            if audio_path.suffix.lower() in (".ulaw", ".ul"):
                try:
                    result = subprocess.run(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-f",
                            "mulaw",
                            "-ar",
                            "8000",
                            "-ac",
                            "1",
                            "-show_entries",
                            "stream=duration",
                            "-of",
                            "default=noprint_wrappers=1:nokey=1",
                            str(audio_path),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=True,
                    )
                    output = result.stdout.strip()
                    if output:
                        return float(output)
                except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as exc:
                    logger.warning("ffprobe duration failed for ulaw: %s", exc)
                return audio_path.stat().st_size / 8000.0

            audio = AudioSegment.from_file(str(audio_path))
            return len(audio) / 1000.0
        except Exception as exc:
            logger.error("Failed to get audio duration: %s", exc)
            return 0.0

    def validate_audio_file(self, audio_path: Path) -> bool:
        if not audio_path.exists():
            logger.error("Audio file does not exist: %s", audio_path)
            return False
        try:
            if audio_path.suffix.lower() in (".ulaw", ".ul"):
                try:
                    subprocess.run(
                        ["ffprobe", "-v", "error", str(audio_path)],
                        capture_output=True,
                        timeout=10,
                        check=True,
                    )
                    return True
                except (subprocess.CalledProcessError, FileNotFoundError):
                    return audio_path.stat().st_size > 0
            AudioSegment.from_file(str(audio_path))
            return True
        except Exception as exc:
            logger.error("Invalid audio file %s: %s", audio_path, exc)
            return False


class GTTSEngine:
    """Google Text-to-Speech engine."""

    def __init__(self, config: TTSConfig):
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        if self.config.engine != "gtts":
            raise TTSEngineError(f"Unsupported TTS engine: {self.config.engine}")

        if not GTTS_AVAILABLE:
            raise TTSEngineError("gTTS library is not installed. Install with: pip install gtts")

        if not self.config.language:
            raise TTSEngineError("Language code is required")

        if not self.config.tld:
            raise TTSEngineError("Top-level domain is required")

    def is_available(self) -> bool:
        try:
            gTTS(text="test", lang=self.config.language, tld=self.config.tld, slow=self.config.slow)
            return True
        except Exception as exc:
            logger.error("gTTS not available: %s", exc)
            return False

    def synthesize(self, text: str, output_path: Path) -> Path:
        if not text.strip():
            raise TTSEngineError("Text cannot be empty")

        logger.debug("Synthesizing text: %r", text[:50])

        try:
            tts = gTTS(
                text=text, lang=self.config.language, tld=self.config.tld, slow=self.config.slow
            )

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_mp3:
                temp_mp3_path = Path(temp_mp3.name)

            tts.save(str(temp_mp3_path))
            final_path = self._convert_audio(temp_mp3_path, output_path)
            temp_mp3_path.unlink(missing_ok=True)
            logger.info("Successfully synthesized audio: %s", final_path)
            return final_path

        except Exception as exc:
            logger.error("Failed to synthesize text: %s", exc)
            raise TTSEngineError(f"Synthesis failed: {exc}") from exc

    def _convert_audio(self, input_path: Path, output_path: Path) -> Path:
        try:
            audio = AudioSegment.from_mp3(str(input_path))

            if audio.channels > 1:
                audio = audio.set_channels(1)

            if audio.frame_rate != self.config.sample_rate:
                audio = audio.set_frame_rate(self.config.sample_rate)

            audio = audio.normalize()

            if self.config.output_format.lower() == "wav":
                audio.export(str(output_path), format="wav")
            elif self.config.output_format.lower() == "mp3":
                audio.export(str(output_path), format="mp3", bitrate=f"{self.config.bit_rate}k")
            elif self.config.output_format.lower() in ["ulaw", "mulaw", "ul"]:
                audio = audio.set_frame_rate(8000).set_channels(1)

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                    temp_wav_path = Path(temp_wav.name)

                audio.export(str(temp_wav_path), format="wav")

                try:
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            str(temp_wav_path),
                            "-ar",
                            "8000",
                            "-ac",
                            "1",
                            "-f",
                            "mulaw",
                            str(output_path),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=30,
                        text=True,
                    )
                    if not output_path.exists() or output_path.stat().st_size == 0:
                        raise TTSEngineError(f"FFmpeg did not create ulaw output: {output_path}")
                except subprocess.CalledProcessError as exc:
                    stderr = (exc.stderr or "Unknown error").strip()
                    raise TTSEngineError(f"Failed to convert to ulaw format: {stderr}") from exc
                except FileNotFoundError as exc:
                    raise TTSEngineError("FFmpeg is required for ulaw format conversion") from exc
                finally:
                    temp_wav_path.unlink(missing_ok=True)
            else:
                output_path = output_path.with_suffix(".wav")
                audio.export(str(output_path), format="wav")

            return output_path

        except TTSEngineError:
            raise
        except Exception as exc:
            logger.error("Failed to convert audio: %s", exc)
            raise TTSEngineError(f"Audio conversion failed: {exc}") from exc

    def get_audio_duration(self, audio_path: Path) -> float:
        try:
            if audio_path.suffix.lower() in (".ulaw", ".ul"):
                try:
                    result = subprocess.run(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-f",
                            "mulaw",
                            "-ar",
                            "8000",
                            "-ac",
                            "1",
                            "-show_entries",
                            "stream=duration",
                            "-of",
                            "default=noprint_wrappers=1:nokey=1",
                            str(audio_path),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=True,
                    )
                    output = result.stdout.strip()
                    if output:
                        return float(output)
                except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
                    return audio_path.stat().st_size / 8000.0

            audio = AudioSegment.from_file(str(audio_path))
            return len(audio) / 1000.0
        except Exception as exc:
            logger.error("Failed to get audio duration: %s", exc)
            return 0.0

    def validate_audio_file(self, audio_path: Path) -> bool:
        if not audio_path.exists():
            logger.error("Audio file does not exist: %s", audio_path)
            return False
        try:
            if audio_path.suffix.lower() in (".ulaw", ".ul"):
                try:
                    subprocess.run(
                        ["ffprobe", "-v", "error", str(audio_path)],
                        capture_output=True,
                        timeout=10,
                        check=True,
                    )
                    return True
                except (subprocess.CalledProcessError, FileNotFoundError):
                    return audio_path.stat().st_size > 0
            AudioSegment.from_file(str(audio_path))
            return True
        except Exception as exc:
            logger.error("Invalid audio file %s: %s", audio_path, exc)
            return False
