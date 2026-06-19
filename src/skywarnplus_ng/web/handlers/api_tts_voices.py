"""API handlers for Piper voice catalog and on-demand install."""

from __future__ import annotations

import logging
from pathlib import Path
from aiohttp import web
from aiohttp.web import Request, Response

from ...audio.tts_voices import TTSVoiceError, build_voices_payload, install_voice

logger = logging.getLogger(__name__)


def _tts_voices_dir(config: object) -> Path:
    tts = getattr(getattr(config, "audio", None), "tts", None)
    if tts and getattr(tts, "voices_dir", None):
        return Path(str(tts.voices_dir))
    return Path("/var/lib/piper-tts")


class TtsVoicesApiMixin:
    async def api_tts_voices_handler(self, request: Request) -> Response:
        """List Piper voices (catalog + installed) for the configuration UI."""
        try:
            voices_dir = _tts_voices_dir(self.config)
            default_voice = str(getattr(self.config.audio.tts, "voice", "en_US-amy-low.onnx"))
            payload = build_voices_payload(voices_dir=voices_dir, default_voice=default_voice)
            return web.json_response(payload)
        except Exception as exc:
            logger.error("Error listing TTS voices: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)

    async def api_tts_voice_install_handler(self, request: Request) -> Response:
        """Download and install a catalog Piper voice into voices_dir."""
        try:
            data = await request.json()
            if not isinstance(data, dict):
                return web.json_response({"error": "JSON body must be an object"}, status=400)

            voice_id = data.get("voice_id") or data.get("id")
            if not voice_id or not isinstance(voice_id, str):
                return web.json_response({"error": "voice_id is required"}, status=400)

            voices_dir = _tts_voices_dir(self.config)
            filename = install_voice(voice_id.strip(), voices_dir)
            return web.json_response(
                {
                    "success": True,
                    "message": f"Voice installed: {filename}",
                    "file": filename,
                    "voice": filename,
                }
            )
        except TTSVoiceError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            logger.error("Error installing TTS voice: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)
