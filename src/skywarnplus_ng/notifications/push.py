"""
Push notification system for SkywarnPlus-NG.

FCM legacy HTTP (server key → fcm/send) was retired by Google. Config fields remain
for forward-compatible UI storage; delivery is disabled until HTTP v1 lands.
Web Push remains unimplemented.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import aiohttp

from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)

LEGACY_FCM_RETIRED_MSG = (
    "FCM legacy HTTP API (server key / fcm/send) was retired by Google. "
    "SkywarnPlus-NG does not yet support FCM HTTP v1; use PushOver, email, SMS, or webhooks."
)


class PushProvider(Enum):
    """Supported push notification providers."""

    FCM = "fcm"
    WEB_PUSH = "web_push"


@dataclass
class PushConfig:
    """Push notification configuration."""

    provider: PushProvider
    enabled: bool = True
    timeout_seconds: int = 30
    retry_count: int = 3
    retry_delay_seconds: int = 5

    # Legacy FCM fields (no longer usable for send)
    fcm_server_key: str | None = None
    fcm_project_id: str | None = None

    # Web Push settings
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_email: str | None = None


class PushNotifier:
    """Push notification system (FCM legacy disabled; Web Push not implemented)."""

    def __init__(self, config: PushConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{config.provider.value}")
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def send_alert_push(
        self,
        alert: WeatherAlert,
        device_tokens: list[str],
        custom_title: str | None = None,
        custom_body: str | None = None,
    ) -> dict[str, Any]:
        """Send weather alert push notification."""
        try:
            if self.config.provider == PushProvider.FCM:
                return await self._send_fcm_alert(alert, device_tokens, custom_title, custom_body)
            if self.config.provider == PushProvider.WEB_PUSH:
                return await self._send_web_push_alert(
                    alert, device_tokens, custom_title, custom_body
                )
            raise ValueError(f"Unsupported push provider: {self.config.provider}")

        except Exception as e:
            self.logger.error(f"Failed to send push notification: {e}")
            return {
                "success": False,
                "error": str(e),
                "alert_id": alert.id,
                "provider": self.config.provider.value,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def send_notification_push(
        self, title: str, body: str, device_tokens: list[str], data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send general push notification."""
        try:
            if self.config.provider == PushProvider.FCM:
                return await self._send_fcm_notification(title, body, device_tokens, data)
            if self.config.provider == PushProvider.WEB_PUSH:
                return await self._send_web_push_notification(title, body, device_tokens, data)
            raise ValueError(f"Unsupported push provider: {self.config.provider}")

        except Exception as e:
            self.logger.error(f"Failed to send push notification: {e}")
            return {
                "success": False,
                "error": str(e),
                "provider": self.config.provider.value,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def _send_fcm_alert(
        self,
        alert: WeatherAlert,
        device_tokens: list[str],
        custom_title: str | None = None,
        custom_body: str | None = None,
    ) -> dict[str, Any]:
        """FCM alert send — legacy API retired."""
        del alert, device_tokens, custom_title, custom_body
        raise RuntimeError(LEGACY_FCM_RETIRED_MSG)

    async def _send_fcm_notification(
        self, title: str, body: str, device_tokens: list[str], data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """FCM notification send — legacy API retired."""
        del title, body, device_tokens, data
        raise RuntimeError(LEGACY_FCM_RETIRED_MSG)

    async def _send_web_push_alert(
        self,
        alert: WeatherAlert,
        device_tokens: list[str],
        custom_title: str | None = None,
        custom_body: str | None = None,
    ) -> dict[str, Any]:
        """Send Web Push alert notification."""
        del device_tokens, custom_title, custom_body
        self.logger.warning("Web Push notifications not yet implemented")
        return {
            "success": False,
            "error": "Web Push notifications not yet implemented",
            "alert_id": alert.id,
            "provider": "web_push",
        }

    async def _send_web_push_notification(
        self, title: str, body: str, device_tokens: list[str], data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send Web Push general notification."""
        del title, body, device_tokens, data
        self.logger.warning("Web Push notifications not yet implemented")
        return {
            "success": False,
            "error": "Web Push notifications not yet implemented",
            "provider": "web_push",
        }

    async def test_push_notification(self, device_token: str) -> bool:
        """Test push notification delivery."""
        try:
            result = await self.send_notification_push(
                title="SkywarnPlus-NG Test",
                body="This is a test notification from SkywarnPlus-NG",
                device_tokens=[device_token],
                data={"test": True},
            )

            if result.get("success", False):
                self.logger.info(
                    f"Push notification test successful for {self.config.provider.value}"
                )
                return True
            self.logger.error(
                f"Push notification test failed: {result.get('error', 'Unknown error')}"
            )
            return False

        except Exception as e:
            self.logger.error(
                f"Push notification test failed for {self.config.provider.value}: {e}"
            )
            return False

    @classmethod
    def create_fcm_config(
        cls, fcm_server_key: str, fcm_project_id: str | None = None
    ) -> PushConfig:
        """Create FCM config object (delivery still disabled until HTTP v1)."""
        return PushConfig(
            provider=PushProvider.FCM, fcm_server_key=fcm_server_key, fcm_project_id=fcm_project_id
        )

    @classmethod
    def create_web_push_config(
        cls, vapid_public_key: str, vapid_private_key: str, vapid_email: str
    ) -> PushConfig:
        """Create Web Push configuration."""
        return PushConfig(
            provider=PushProvider.WEB_PUSH,
            vapid_public_key=vapid_public_key,
            vapid_private_key=vapid_private_key,
            vapid_email=vapid_email,
        )
