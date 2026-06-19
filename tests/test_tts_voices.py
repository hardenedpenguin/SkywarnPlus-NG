"""Tests for Piper voice catalog, listing, and install helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skywarnplus_ng.audio.tts_voices import (
    TTSVoiceError,
    build_voices_payload,
    install_voice,
    list_voice_models,
    load_voice_catalog_data,
)
from skywarnplus_ng.web.handlers.api_config import _list_piper_onnx_models


def test_list_voice_models_requires_json_sidecar(tmp_path: Path) -> None:
    voices_dir = tmp_path / "piper-tts"
    voices_dir.mkdir()
    (voices_dir / "a_voice.onnx").write_text("x")
    (voices_dir / "a_voice.onnx.json").write_text("{}")
    (voices_dir / "b_voice.onnx").write_text("x")
    (voices_dir / "readme.txt").write_text("n")
    sub = voices_dir / "nested"
    sub.mkdir()
    (sub / "ignore.onnx").write_text("x")
    (sub / "ignore.onnx.json").write_text("{}")

    assert list_voice_models(voices_dir) == ["a_voice.onnx"]


def test_list_voice_models_missing_dir(tmp_path: Path) -> None:
    assert list_voice_models(tmp_path / "nope") == []


def test_list_piper_onnx_models_legacy_paths(tmp_path: Path) -> None:
    voices_dir = tmp_path / "piper-tts"
    voices_dir.mkdir()
    (voices_dir / "amy.onnx").write_text("x")
    (voices_dir / "amy.onnx.json").write_text("{}")

    paths = _list_piper_onnx_models(voices_dir)
    assert paths == [str(voices_dir / "amy.onnx")]


def test_load_voice_catalog_data_has_voices() -> None:
    data = load_voice_catalog_data()
    assert isinstance(data["regions"], list)
    assert len(data["regions"]) >= 1
    assert isinstance(data["voices"], dict)
    assert "en_US-amy-low" in data["voices"]
    assert data["voices"]["en_US-amy-low"]["curated"] is True


def test_build_voices_payload_marks_installed_and_custom(tmp_path: Path) -> None:
    voices_dir = tmp_path / "piper-tts"
    voices_dir.mkdir()
    (voices_dir / "en_US-amy-low.onnx").write_text("x")
    (voices_dir / "en_US-amy-low.onnx.json").write_text("{}")
    (voices_dir / "custom_voice.onnx").write_text("x")
    (voices_dir / "custom_voice.onnx.json").write_text("{}")

    payload = build_voices_payload(
        voices_dir=voices_dir,
        default_voice="en_US-amy-low.onnx",
    )

    amy = next(v for v in payload["voices"] if v["file"] == "en_US-amy-low.onnx")
    custom = next(v for v in payload["voices"] if v["file"] == "custom_voice.onnx")
    not_installed = next(v for v in payload["voices"] if v["file"] == "en_US-lessac-high.onnx")

    assert amy["installed"] is True
    assert amy["catalog"] is True
    assert custom["installed"] is True
    assert custom["catalog"] is False
    assert custom["label"].endswith("(custom)")
    assert not_installed["installed"] is False
    assert payload["default"] == "en_US-amy-low.onnx"
    assert payload["voices_dir"] == str(voices_dir)


def test_install_voice_rejects_unknown_id(tmp_path: Path) -> None:
    with pytest.raises(TTSVoiceError, match="not available"):
        install_voice("not-a-real-voice-id", tmp_path / "piper-tts")


@patch("skywarnplus_ng.audio.tts_voices.subprocess.run")
def test_install_voice_success(mock_run: MagicMock, tmp_path: Path) -> None:
    voices_dir = tmp_path / "piper-tts"
    voices_dir.mkdir()
    script = tmp_path / "install.sh"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)

    def fake_install(*args, **kwargs):
        (voices_dir / "en_US-amy-low.onnx").write_text("x")
        (voices_dir / "en_US-amy-low.onnx.json").write_text("{}")
        return MagicMock(returncode=0, stdout="ok", stderr="")

    mock_run.side_effect = fake_install

    filename = install_voice("en_US-amy-low", voices_dir, install_script=script)
    assert filename == "en_US-amy-low.onnx"
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "sudo"
    assert str(script) in cmd
