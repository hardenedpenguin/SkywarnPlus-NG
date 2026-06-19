"""
Piper voice catalog and install helpers for asl-tts (ASL3 / supermon-ng convention).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from importlib import resources
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_REGIONS = [
    "Americas",
    "Europe",
    "Asia-Pacific",
    "Middle East & Africa",
    "Other",
]

VOICE_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
HF_PATH_RE = re.compile(r"^[a-zA-Z0-9._/-]+$")

DEFAULT_INSTALL_SCRIPT = Path("/var/lib/skywarnplus-ng/scripts/install-tts-voice.sh")


class TTSVoiceError(Exception):
    """Voice catalog or install error."""


def catalog_path() -> Path:
    """Shipped Piper voice catalog (from supermon-ng announcement_voices.json)."""
    return Path(resources.files("skywarnplus_ng.data") / "tts_voices_catalog.json")


def load_voice_catalog_data() -> dict[str, Any]:
    """Load regions and voice catalog entries."""
    path = catalog_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Voice catalog not readable at %s: %s", path, exc)
        return {"regions": DEFAULT_REGIONS, "voices": {}}

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Voice catalog JSON invalid: %s", exc)
        return {"regions": DEFAULT_REGIONS, "voices": {}}

    if not isinstance(decoded, dict):
        return {"regions": DEFAULT_REGIONS, "voices": {}}

    regions = decoded.get("regions", DEFAULT_REGIONS)
    if not isinstance(regions, list):
        regions = DEFAULT_REGIONS

    voices_raw = decoded.get("voices", {})
    if not isinstance(voices_raw, dict):
        voices_raw = {}

    voices: dict[str, dict[str, Any]] = {}
    for voice_id, entry in voices_raw.items():
        if not isinstance(voice_id, str) or not VOICE_ID_RE.match(voice_id):
            continue
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label", voice_id)).strip()
        hf_path = str(entry.get("huggingface_path", "")).strip()
        if not label or not hf_path or not HF_PATH_RE.match(hf_path):
            continue
        voices[voice_id] = {
            "label": label,
            "huggingface_path": hf_path,
            "region": str(entry.get("region", "Other")),
            "language": str(entry.get("language", "")),
            "locale": str(entry.get("locale", "")),
            "quality": str(entry.get("quality", "")),
            "curated": bool(entry.get("curated", False)),
        }

    return {"regions": [str(r) for r in regions], "voices": voices}


def list_installed_voice_files(voices_dir: Path) -> dict[str, Path]:
    """Map voice filename (e.g. en_US-amy-low.onnx) to resolved path."""
    installed: dict[str, Path] = {}
    if not voices_dir.is_dir():
        return installed
    try:
        root = voices_dir.resolve()
    except OSError:
        return installed
    try:
        candidates = sorted(root.glob("*.onnx"), key=lambda p: p.name.lower())
    except OSError:
        return installed
    for model in candidates:
        try:
            if not model.exists():
                continue
            model.resolve().relative_to(root)
        except (ValueError, OSError):
            continue
        config_path = model.with_suffix(model.suffix + ".json")
        if not config_path.exists():
            continue
        installed[model.name] = model
    return installed


def list_voice_models(voices_dir: Path) -> list[str]:
    """Return sorted installed voice basenames (*.onnx) with a paired *.onnx.json."""
    return sorted(list_installed_voice_files(voices_dir).keys(), key=str.lower)


def build_voices_payload(
    *,
    voices_dir: Path,
    default_voice: str,
) -> dict[str, Any]:
    """
    Build voice list for the configuration UI (supermon-ng compatible shape).
    """
    catalog_data = load_voice_catalog_data()
    catalog = catalog_data["voices"]
    regions = catalog_data["regions"]
    installed = list_installed_voice_files(voices_dir)

    voices: list[dict[str, Any]] = []
    seen: set[str] = set()

    for voice_id, entry in catalog.items():
        filename = f"{voice_id}.onnx"
        voices.append(
            {
                "id": voice_id,
                "file": filename,
                "label": entry["label"],
                "installed": filename in installed,
                "catalog": True,
                "region": entry["region"],
                "language": entry["language"],
                "locale": entry["locale"],
                "quality": entry["quality"],
                "curated": entry["curated"],
            }
        )
        seen.add(filename)

    for filename in installed:
        if filename in seen:
            continue
        voice_id = filename.removesuffix(".onnx")
        voices.append(
            {
                "id": voice_id,
                "file": filename,
                "label": f"{voice_id} (custom)",
                "installed": True,
                "catalog": False,
                "region": "Other",
                "language": "",
                "locale": "",
                "quality": "",
                "curated": False,
            }
        )

    voices.sort(key=lambda item: str(item.get("label", "")).lower())

    default = default_voice if default_voice.endswith(".onnx") else f"{default_voice}.onnx"
    if not default:
        default = "en_US-amy-low.onnx"

    return {
        "default": default,
        "regions": regions,
        "voices_dir": str(voices_dir),
        "voices": voices,
    }


def install_voice(
    voice_id: str,
    voices_dir: Path,
    install_script: Path | None = None,
) -> str:
    """
    Download and install a catalog voice via the privileged install script.

    Returns:
        Installed voice filename (e.g. en_US-amy-low.onnx).
    """
    normalized = voice_id.removesuffix(".onnx").strip()
    if not VOICE_ID_RE.match(normalized):
        raise TTSVoiceError("Invalid voice id")

    catalog = load_voice_catalog_data()["voices"]
    entry = catalog.get(normalized)
    if not entry:
        raise TTSVoiceError("Voice is not available in the catalog")

    script = install_script or DEFAULT_INSTALL_SCRIPT
    if not script.is_file():
        raise TTSVoiceError(
            f"Voice install script not found: {script}. Reinstall skywarnplus-ng or install manually."
        )

    cmd = [
        "sudo",
        "-n",
        str(script),
        "--voice-id",
        normalized,
        "--voices-dir",
        str(voices_dir),
        "--huggingface-path",
        str(entry["huggingface_path"]),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TTSVoiceError("Voice install timed out") from exc
    except FileNotFoundError as exc:
        raise TTSVoiceError("sudo is not available for voice install") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "install failed").strip()
        if "password" in detail.lower() and result.returncode == 1:
            raise TTSVoiceError(
                "Voice install requires sudo permission for the asterisk user. "
                "Reinstall or upgrade skywarnplus-ng to install /etc/sudoers.d/skywarnplus-ng-tts."
            )
        raise TTSVoiceError(detail or "Voice install failed")

    filename = f"{normalized}.onnx"
    if filename not in list_installed_voice_files(voices_dir):
        raise TTSVoiceError(f"Install finished but {filename} was not found in {voices_dir}")

    return filename
