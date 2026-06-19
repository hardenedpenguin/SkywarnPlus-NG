"""Tests for AslTTSEngine subprocess wrapper."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skywarnplus_ng.audio.tts_engine import AslTTSEngine, TTSEngineError
from skywarnplus_ng.core.config import TTSConfig


def _make_config(tmp_path: Path) -> TTSConfig:
    voices_dir = tmp_path / "piper-tts"
    voices_dir.mkdir()
    voice = "en_US-amy-low.onnx"
    (voices_dir / voice).write_text("fake")
    (voices_dir / f"{voice}.json").write_text("{}")
    return TTSConfig(
        engine="asl-tts",
        voice=voice,
        voices_dir=str(voices_dir),
        asl_tts_binary=str(tmp_path / "asl-tts"),
        node_number=546050,
        output_format="ulaw",
    )


def test_asl_tts_synthesize_ulaw(tmp_path: Path) -> None:
    binary = tmp_path / "asl-tts"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    config = _make_config(tmp_path)
    config.asl_tts_binary = str(binary)
    engine = AslTTSEngine(config)

    output = tmp_path / "alert.ulaw"

    def fake_run(cmd, **kwargs):
        base = Path(cmd[cmd.index("-f") + 1])
        ul = base.with_suffix(".ul")
        ul.write_bytes(b"\x00" * 8000)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("skywarnplus_ng.audio.tts_engine.subprocess.run", side_effect=fake_run):
        result = engine.synthesize("Test alert", output)

    assert result == output
    assert output.is_file()
    assert output.stat().st_size == 8000


def test_asl_tts_missing_binary(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.asl_tts_binary = str(tmp_path / "missing")
    with pytest.raises(TTSEngineError, match="asl-tts binary not found"):
        AslTTSEngine(config)
