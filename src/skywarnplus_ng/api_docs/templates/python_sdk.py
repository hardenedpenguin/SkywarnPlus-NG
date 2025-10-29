"""
Official Python SDK for SkywarnPlus-NG API.
"""

import requests
import json
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from datetime import datetime
import websockets
import asyncio


@dataclass
class WeatherAlert:
    """Weather alert data model."""
    id: str
    event: str
    headline: Optional[str] = None
    description: Optional[str] = None
    area_desc: str = ""
    severity: str = "Minor"
    urgency: str = "Future"
    certainty: str = "Possible"
    status: str = "Actual"
    category: str = "Met"
    effective: Optional[datetime] = None
    expires: Optional[datetime] = None
    sent: Optional[datetime] = None
    onset: Optional[datetime] = None
    ends: Optional[datetime] = None
    instruction: Optional[str] = None
    sender: Optional[str] = None
    sender_name: Optional[str] = None
    county_codes: List[str] = None
    geocode: List[str] = None


@dataclass
class Subscriber:
    """Subscriber data model."""
    subscriber_id: str
    name: str
    email: str
    status: str = "active"
    preferences: Dict[str, Any] = None
    phone: Optional[str] = None
    webhook_url: Optional[str] = None
    push_tokens: List[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SkywarnPlusError(Exception):
    """SkywarnPlus-NG API error."""
    pass


class SkywarnPlusClient:
    """Official Python client for SkywarnPlus-NG API."""
    
    def __init__(self, base_url: str = "{{ base_url }}", timeout: int = 30):
        """
        Initialize the SkywarnPlus-NG client.
        
        Args:
            base_url: Base URL of the SkywarnPlus-NG API
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': f'SkywarnPlus-Python-SDK/{{ version }}'
        })
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to API."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.request(
                method, url, timeout=self.timeout, **kwargs
            )
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
    
    def get_status(self) -> Dict[str, Any]:
        """Get system status."""
        return self._make_request('GET', '/api/status')
    
    def get_health(self) -> Dict[str, Any]:
        """Get system health information."""
        return self._make_request('GET', '/api/health')
    
    def get_alerts(self, county: Optional[str] = None, severity: Optional[str] = None) -> List[WeatherAlert]:
        """Get active weather alerts."""
        params = {}
        if county:
            params['county'] = county
        if severity:
            params['severity'] = severity
        
        response = self._make_request('GET', '/api/alerts', params=params)
        return [WeatherAlert(**alert) for alert in response]
    
    def get_alert_history(self, limit: int = 100, offset: int = 0, 
                         start_date: Optional[str] = None, 
                         end_date: Optional[str] = None) -> Dict[str, Any]:
        """Get alert history."""
        params = {'limit': limit, 'offset': offset}
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        
        return self._make_request('GET', '/api/alerts/history', params=params)
    
    def get_configuration(self) -> Dict[str, Any]:
        """Get system configuration."""
        return self._make_request('GET', '/api/config')
    
    def update_configuration(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update system configuration."""
        return self._make_request('POST', '/api/config', json=config)
    
    def reset_configuration(self) -> Dict[str, Any]:
        """Reset configuration to defaults."""
        return self._make_request('POST', '/api/config/reset')
    
    def test_email_connection(self, email_config: Dict[str, Any]) -> Dict[str, Any]:
        """Test email SMTP connection."""
        return self._make_request('POST', '/api/notifications/test-email', json=email_config)
    
    def get_subscribers(self) -> List[Subscriber]:
        """Get all notification subscribers."""
        response = self._make_request('GET', '/api/notifications/subscribers')
        return [Subscriber(**subscriber) for subscriber in response]
    
    def add_subscriber(self, subscriber_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new notification subscriber."""
        return self._make_request('POST', '/api/notifications/subscribers', json=subscriber_data)
    
    def update_subscriber(self, subscriber_id: str, subscriber_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing subscriber."""
        return self._make_request('PUT', f'/api/notifications/subscribers/{subscriber_id}', json=subscriber_data)
    
    def delete_subscriber(self, subscriber_id: str) -> Dict[str, Any]:
        """Delete a subscriber."""
        return self._make_request('DELETE', f'/api/notifications/subscribers/{subscriber_id}')
    
    def get_templates(self) -> Dict[str, Any]:
        """Get all notification templates."""
        return self._make_request('GET', '/api/notifications/templates')
    
    def add_template(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new notification template."""
        return self._make_request('POST', '/api/notifications/templates', json=template_data)
    
    def get_logs(self, level: Optional[str] = None, limit: int = 100, 
                since: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get system logs."""
        params = {'limit': limit}
        if level:
            params['level'] = level
        if since:
            params['since'] = since
        
        return self._make_request('GET', '/api/logs', params=params)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get system metrics."""
        return self._make_request('GET', '/api/metrics')
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        return self._make_request('GET', '/api/database/stats')
    
    async def connect_websocket(self, on_message=None, on_error=None):
        """Connect to WebSocket for real-time updates."""
        ws_url = self.base_url.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws'
        
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


def quick_status(base_url: str = "{{ base_url }}") -> Dict[str, Any]:
    """Quick status check."""
    client = create_client(base_url)
    return client.get_status()


def quick_alerts(base_url: str = "{{ base_url }}", county: Optional[str] = None) -> List[WeatherAlert]:
    """Quick alerts check."""
    client = create_client(base_url)
    return client.get_alerts(county=county)
