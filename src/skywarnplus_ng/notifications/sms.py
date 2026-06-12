"""
SMS notifications via Twilio.

Works from mobile nodes with outbound internet — no local modem or gateway required.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import aiohttp

from ..core.models import WeatherAlert
from .phone import normalize_phone_number

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


@dataclass
class SmsConfig:
    """Twilio SMS configuration."""

    account_sid: str
    auth_token: str
    from_number: str
    enabled: bool = True
    timeout_seconds: int = 30
    retry_count: int = 3
    retry_delay_seconds: int = 5
    max_length: int = 160
    all_clear_enabled: bool = False
    api_base_url: Optional[str] = None  # for tests only

    def __post_init__(self) -> None:
        if not str(self.account_sid or "").strip():
            raise ValueError("Twilio Account SID is required")
        if not str(self.auth_token or "").strip():
            raise ValueError("Twilio Auth Token is required")
        from_num = normalize_phone_number(self.from_number)
        if not from_num:
            raise ValueError("Twilio From number must be a valid E.164 phone number")
        self.from_number = from_num

    @property
    def messages_url(self) -> str:
        base = (self.api_base_url or TWILIO_API_BASE).rstrip("/")
        return f"{base}/Accounts/{self.account_sid}/Messages.json"


def format_short_alert_message(alert: WeatherAlert, max_length: int = 160) -> str:
    """Build a compact SMS body for a weather alert."""
    area = (alert.area_desc or "").strip()
    if len(area) > 72:
        area = area[:69] + "..."

    expires = alert.expires
    if expires:
        expire_label = expires.astimezone(timezone.utc).strftime("%m/%d %I:%M %p UTC")
        expire_label = expire_label.replace(" 0", " ").replace("/0", "/")
    else:
        expire_label = "see NWS"

    lines = [f"⚠ {alert.event}"]
    if area:
        lines.append(area)
    lines.append(f"Until {expire_label}")

    body = "\n".join(lines)
    if len(body) <= max_length:
        return body

    compact = f"⚠ {alert.event}\nUntil {expire_label}"
    if len(compact) <= max_length:
        return compact

    event = alert.event
    if len(event) > max_length - 20:
        event = event[: max_length - 23] + "..."
    return f"⚠ {event}\nUntil {expire_label}"[:max_length]


def format_short_general_message(title: str, message: str, max_length: int = 160) -> str:
    """Build a compact SMS for non-alert notifications (e.g. all-clear)."""
    body = f"{title}\n{message}".strip()
    if len(body) <= max_length:
        return body
    return body[: max_length - 3] + "..."


class SmsNotifier:
    """Deliver SMS through the Twilio REST API."""

    def __init__(self, config: SmsConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "SmsNotifier":
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session:
            await self.session.close()

    def _auth_header(self) -> str:
        token = base64.b64encode(
            f"{self.config.account_sid}:{self.config.auth_token}".encode()
        ).decode("ascii")
        return f"Basic {token}"

    async def send_sms(
        self,
        to: str,
        body: str,
        *,
        alert_id: Optional[str] = None,
        event: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an SMS via Twilio."""
        phone = normalize_phone_number(to)
        if not phone:
            return {"success": False, "error": "Invalid destination phone number"}

        text = body.strip()
        if not text:
            return {"success": False, "error": "Empty SMS body"}

        if len(text) > self.config.max_length:
            text = text[: self.config.max_length]

        form = urlencode(
            {
                "To": phone,
                "From": self.config.from_number,
                "Body": text,
            }
        )
        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        }

        last_error = "Unknown error"
        for attempt in range(1, self.config.retry_count + 1):
            try:
                if not self.session:
                    raise RuntimeError("SMS notifier session not initialized")

                async with self.session.post(
                    self.config.messages_url,
                    data=form,
                    headers=headers,
                ) as response:
                    response_text = await response.text()
                    if 200 <= response.status < 300:
                        result: Dict[str, Any] = {
                            "success": True,
                            "to": phone,
                            "status": response.status,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        if alert_id:
                            result["alert_id"] = alert_id
                        if event:
                            result["event"] = event
                        try:
                            payload = json.loads(response_text)
                            if isinstance(payload, dict) and payload.get("sid"):
                                result["message_sid"] = payload["sid"]
                        except Exception:
                            result["response"] = response_text[:500]
                        return result

                    last_error = f"HTTP {response.status}: {response_text[:200]}"
                    self.logger.warning(
                        "Twilio returned %s (attempt %s/%s)",
                        response.status,
                        attempt,
                        self.config.retry_count,
                    )
            except Exception as exc:
                last_error = str(exc)
                self.logger.warning(
                    "Twilio request failed (attempt %s/%s): %s",
                    attempt,
                    self.config.retry_count,
                    exc,
                )

            if attempt < self.config.retry_count:
                await asyncio.sleep(self.config.retry_delay_seconds)

        return {
            "success": False,
            "error": last_error,
            "to": phone,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def send_alert_sms(self, alert: WeatherAlert, to: str) -> Dict[str, Any]:
        body = format_short_alert_message(alert, self.config.max_length)
        return await self.send_sms(to, body, alert_id=alert.id, event=alert.event)
