"""Tests for runtime TTS engine reload after config changes."""

from pathlib import Path

from skywarnplus_ng.audio.manager import AudioManager
from skywarnplus_ng.audio.tts_engine import AslTTSEngine
from skywarnplus_ng.core.config import AudioConfig, TTSConfig


def _audio_config(tmp_path: Path, voice: str) -> AudioConfig:
    voices_dir = tmp_path / "piper-tts"
    voices_dir.mkdir(parents=True, exist_ok=True)
    for name in ("en_US-amy-low.onnx", "en_US-ryan-medium.onnx"):
        (voices_dir / name).write_text("fake")
        (voices_dir / f"{name}.json").write_text("{}")
    binary = tmp_path / "asl-tts"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    return AudioConfig(
        sounds_path=tmp_path / "sounds",
        temp_dir=tmp_path / "tmp",
        tts=TTSConfig(
            engine="asl-tts",
            voice=voice,
            voices_dir=str(voices_dir),
            asl_tts_binary=str(binary),
            node_number=546050,
            output_format="ulaw",
        ),
    )


def test_reload_tts_engine_switches_voice(tmp_path: Path) -> None:
    manager = AudioManager(_audio_config(tmp_path, "en_US-amy-low.onnx"))
    assert isinstance(manager.tts_engine, AslTTSEngine)
    assert manager.tts_engine.voice == "en_US-amy-low.onnx"

    manager.config = _audio_config(tmp_path, "en_US-ryan-medium.onnx")
    assert manager.reload_tts_engine() is True
    assert isinstance(manager.tts_engine, AslTTSEngine)
    assert manager.tts_engine.voice == "en_US-ryan-medium.onnx"


def test_reload_tts_engine_keeps_previous_on_invalid_voice(tmp_path: Path) -> None:
    manager = AudioManager(_audio_config(tmp_path, "en_US-amy-low.onnx"))
    original = manager.tts_engine

    bad = _audio_config(tmp_path, "missing-voice.onnx")
    manager.config = bad
    assert manager.reload_tts_engine() is False
    assert manager.tts_engine is original
