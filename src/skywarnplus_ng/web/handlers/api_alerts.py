"""
Alerts API handlers mixin.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp.web import Request, Response

from ..alert_payload import build_active_alerts_payload

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class AlertsApiMixin:
    async def api_alerts_handler(self, request: Request) -> Response:
        """Handle API alerts endpoint."""
        try:
            config = self.app.config if self.app and hasattr(self.app, "config") else None
            alerts_data = build_active_alerts_payload(self.app.state, config)

            return web.json_response(
                {
                    "alerts": alerts_data,
                    "count": len(alerts_data),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_alert_audio_handler(self, request: Request) -> Response:
        """Generate and stream TTS audio for a specific alert."""
        try:
            alert_id = request.match_info.get("alert_id")
            if not alert_id:
                return web.json_response({"error": "alert_id is required"}, status=400)

            # Ensure audio subsystem is available
            if not self.app or not self.app.audio_manager:
                return web.json_response({"error": "Audio system not available"}, status=503)

            # Look up alert data from state
            alert_data = self.app.state.get("last_alerts", {}).get(alert_id)
            if not alert_data:
                return web.json_response({"error": "Alert not found or expired"}, status=404)

            # Construct WeatherAlert model defensively
            try:
                from ...core.models import WeatherAlert

                alert_model = WeatherAlert(**alert_data)
            except Exception:
                # Fallback: minimal model using required fields
                from datetime import datetime
                from ...core.models import WeatherAlert

                minimal = {
                    "id": alert_data.get("id", alert_id),
                    "event": alert_data.get("event", "Weather Alert"),
                    "description": alert_data.get("description", alert_data.get("area_desc", "")),
                    "sent": datetime.now(timezone.utc),
                    "effective": datetime.now(timezone.utc),
                    "expires": datetime.now(timezone.utc),
                    "area_desc": alert_data.get("area_desc", ""),
                    "sender": alert_data.get("sender", "NWS"),
                    "sender_name": alert_data.get("sender_name", "National Weather Service"),
                }
                alert_model = WeatherAlert(**minimal)

            # Get county audio files if county names are enabled (same logic as _announce_alert)
            county_audio_files = None
            if self.app.config.alerts.with_county_names:
                county_codes_list = getattr(alert_model, "county_codes", []) or []
                area_desc = getattr(alert_model, "area_desc", None)
                if county_codes_list:
                    county_audio_files = self.app._get_county_audio_files(
                        county_codes_list, area_desc=area_desc
                    )

            # Generate audio file with county audio if enabled; include CAP description for preview
            audio_path = self.app.audio_manager.generate_alert_audio(
                alert_model,
                county_audio_files=county_audio_files,
                include_cap_description=True,
            )
            if not audio_path or not audio_path.exists():
                return web.json_response({"error": "Failed to generate audio"}, status=500)

            # Determine content type from extension
            ext = audio_path.suffix.lower()

            # Convert ulaw to WAV for browser compatibility (browsers can't play ulaw)
            if ext in [".ulaw", ".ul"]:
                import tempfile
                import subprocess

                # Create temporary WAV file for conversion
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                    temp_wav_path = Path(temp_wav.name)

                try:
                    # Convert ulaw to WAV using ffmpeg
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-f",
                            "mulaw",  # Input format: mulaw
                            "-ar",
                            "8000",  # Sample rate: 8kHz (standard for ulaw)
                            "-ac",
                            "1",  # Channels: mono
                            "-i",
                            str(audio_path),
                            str(temp_wav_path),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=30,
                        text=True,
                    )

                    # Read the converted WAV file into memory
                    wav_data = temp_wav_path.read_bytes()

                    # Clean up temp file
                    try:
                        temp_wav_path.unlink(missing_ok=True)
                    except Exception:
                        pass

                    # Return WAV data as response
                    return web.Response(body=wav_data, headers={"Content-Type": "audio/wav"})
                except subprocess.CalledProcessError as e:
                    logger.error(
                        f"Failed to convert ulaw to WAV: {e.stderr if e.stderr else 'Unknown error'}"
                    )
                    # Clean up temp file
                    try:
                        temp_wav_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    # Fallback: try to return original file anyway
                    return web.FileResponse(
                        path=str(audio_path), headers={"Content-Type": "application/octet-stream"}
                    )
                except Exception as conv_e:
                    logger.error(f"Error during ulaw conversion: {conv_e}")
                    # Clean up temp file on error
                    try:
                        temp_wav_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    # Fallback: return original file
                    return web.FileResponse(
                        path=str(audio_path), headers={"Content-Type": "application/octet-stream"}
                    )

            # Handle other formats
            if ext in [".mp3"]:
                content_type = "audio/mpeg"
            elif ext in [".wav"]:
                content_type = "audio/wav"
            elif ext in [".ogg"]:
                content_type = "audio/ogg"
            else:
                content_type = "application/octet-stream"

            # Stream file to client
            return web.FileResponse(path=str(audio_path), headers={"Content-Type": content_type})
        except Exception as e:
            logger.error(f"Error generating alert audio: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def api_alerts_history_handler(self, request: Request) -> Response:
        """Handle API alerts history endpoint."""
        try:
            if not self.app.database_manager:
                return web.json_response({"error": "Database not available"}, status=503)

            # Get query parameters
            limit = int(request.query.get("limit", 100))
            hours = int(request.query.get("hours", 24))

            # Get alerts from database
            alerts = await self.app.database_manager.get_recent_alerts(limit=limit, hours=hours)

            # Convert to dict format
            alerts_data = []
            for alert in alerts:
                # Helper function to safely format datetime
                def format_datetime(dt):
                    if dt is None:
                        return None
                    if hasattr(dt, "isoformat"):
                        return dt.isoformat()
                    # If it's already a string, return as-is
                    return str(dt)

                alerts_data.append(
                    {
                        "id": alert.id,
                        "event": alert.event,
                        "severity": alert.severity,
                        "area_desc": alert.area_desc,
                        "effective_time": format_datetime(alert.effective_time),
                        "expires_time": format_datetime(alert.expires_time),
                        "processed_at": format_datetime(alert.processed_at),
                        "announced": alert.announced,
                        "script_executed": alert.script_executed,
                    }
                )

            return web.json_response(
                {
                    "alerts": alerts_data,
                    "count": len(alerts_data),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"Error getting alerts history: {e}")
            return web.json_response({"error": str(e)}, status=500)
