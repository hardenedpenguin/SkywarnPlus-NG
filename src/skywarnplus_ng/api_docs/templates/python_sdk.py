"""
Official Python SDK for SkywarnPlus-NG API.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests
import websockets


@dataclass
class WeatherAlert:
    """Weather alert data model."""

    id: str
    event: str
    headline: str | None = None
    description: str | None = None
    area_desc: str = ""
    severity: str = "Minor"
    urgency: str = "Future"
    certainty: str = "Possible"
    status: str = "Actual"
    category: str = "Met"
    effective: datetime | None = None
    expires: datetime | None = None
    sent: datetime | None = None
    onset: datetime | None = None
    ends: datetime | None = None
    instruction: str | None = None
    sender: str | None = None
    sender_name: str | None = None
    county_codes: list[str] = None
    geocode: list[str] = None


@dataclass
class Subscriber:
    """Subscriber data model."""

    subscriber_id: str
    name: str
    email: str
    status: str = "active"
    preferences: dict[str, Any] = None
    phone: str | None = None
    webhook_url: str | None = None
    push_tokens: list[str] = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SkywarnPlusError(Exception):
    """SkywarnPlus-NG API error."""


class SkywarnPlusClient:
    """Official Python client for SkywarnPlus-NG API."""

    def __init__(self, base_url: str = "{{ base_url }}", timeout: int = 30):
        """
        Initialize the SkywarnPlus-NG client.

        Args:
            base_url: Base URL of the SkywarnPlus-NG API
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "User-Agent": "SkywarnPlus-Python-SDK/{ version }"}
        )

    def _make_request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make HTTP request to API."""
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            try:
                error_data = e.response.json()
                raise SkywarnPlusError(f"API Error: {error_data.get('error', str(e))}")
            except (ValueError, KeyError):
                raise SkywarnPlusError(f"HTTP Error: {e}")
        except requests.exceptions.RequestException as e:
            raise SkywarnPlusError(f"Request failed: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get system status."""
        return self._make_request("GET", "/api/status")

    def get_health(self) -> dict[str, Any]:
        """Get system health information."""
        return self._make_request("GET", "/api/health")

    def get_alerts(
        self, county: str | None = None, severity: str | None = None
    ) -> list[WeatherAlert]:
        """Get active weather alerts."""
        params = {}
        if county:
            params["county"] = county
        if severity:
            params["severity"] = severity

        response = self._make_request("GET", "/api/alerts", params=params)
        return [WeatherAlert(**alert) for alert in response]

    def get_alert_history(
        self,
        limit: int = 100,
        offset: int = 0,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Get alert history."""
        params = {"limit": limit, "offset": offset}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        return self._make_request("GET", "/api/alerts/history", params=params)

    def get_configuration(self) -> dict[str, Any]:
        """Get system configuration."""
        return self._make_request("GET", "/api/config")

    def update_configuration(self, config: dict[str, Any]) -> dict[str, Any]:
        """Update system configuration."""
        return self._make_request("POST", "/api/config", json=config)

    def reset_configuration(self) -> dict[str, Any]:
        """Reset configuration to defaults."""
        return self._make_request("POST", "/api/config/reset")

    def test_email_connection(self, email_config: dict[str, Any]) -> dict[str, Any]:
        """Test email SMTP connection."""
        return self._make_request("POST", "/api/notifications/test-email", json=email_config)

    def get_subscribers(self) -> list[Subscriber]:
        """Get all notification subscribers."""
        response = self._make_request("GET", "/api/notifications/subscribers")
        return [Subscriber(**subscriber) for subscriber in response]

    def add_subscriber(self, subscriber_data: dict[str, Any]) -> dict[str, Any]:
        """Add a new notification subscriber."""
        return self._make_request("POST", "/api/notifications/subscribers", json=subscriber_data)

    def update_subscriber(
        self, subscriber_id: str, subscriber_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing subscriber."""
        return self._make_request(
            "PUT", f"/api/notifications/subscribers/{subscriber_id}", json=subscriber_data
        )

    def delete_subscriber(self, subscriber_id: str) -> dict[str, Any]:
        """Delete a subscriber."""
        return self._make_request("DELETE", f"/api/notifications/subscribers/{subscriber_id}")

    def get_templates(self) -> dict[str, Any]:
        """Get all notification templates."""
        return self._make_request("GET", "/api/notifications/templates")

    def add_template(self, template_data: dict[str, Any]) -> dict[str, Any]:
        """Add a new notification template."""
        return self._make_request("POST", "/api/notifications/templates", json=template_data)

    def get_logs(
        self, level: str | None = None, limit: int = 100, since: str | None = None
    ) -> list[dict[str, Any]]:
        """Get system logs."""
        params = {"limit": limit}
        if level:
            params["level"] = level
        if since:
            params["since"] = since

        return self._make_request("GET", "/api/logs", params=params)

    def get_metrics(self) -> dict[str, Any]:
        """Get system metrics."""
        return self._make_request("GET", "/api/metrics")

    def get_database_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        return self._make_request("GET", "/api/database/stats")

    async def connect_websocket(self, on_message=None, on_error=None):
        """Connect to WebSocket for real-time updates."""
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"

        try:
            async with websockets.connect(ws_url) as websocket:
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        if on_message:
                            await on_message(data)
                    except json.JSONDecodeError as e:
                        if on_error:
                            await on_error(f"Failed to parse message: {e}")
        except Exception as e:
            if on_error:
                await on_error(f"WebSocket error: {e}")


# Convenience functions
def create_client(base_url: str = "{{ base_url }}") -> SkywarnPlusClient:
    """Create a new SkywarnPlus-NG client."""
    return SkywarnPlusClient(base_url)


def quick_status(base_url: str = "{{ base_url }}") -> dict[str, Any]:
    """Quick status check."""
    client = create_client(base_url)
    return client.get_status()


def quick_alerts(base_url: str = "{{ base_url }}", county: str | None = None) -> list[WeatherAlert]:
    """Quick alerts check."""
    client = create_client(base_url)
    return client.get_alerts(county=county)
