"""
Webhook notification system for SkywarnPlus-NG.
Supports free webhook integrations like Slack, Discord, and Microsoft Teams.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import aiohttp
import json

from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)


class WebhookProvider(Enum):
    """Supported webhook providers."""
    SLACK = "slack"
    DISCORD = "discord"
    TEAMS = "teams"
    GENERIC = "generic"


@dataclass
class WebhookConfig:
    """Webhook configuration."""
    
    provider: WebhookProvider
    webhook_url: str
    enabled: bool = True
    timeout_seconds: int = 30
    retry_count: int = 3
    retry_delay_seconds: int = 5
    
    # Provider-specific settings
    channel: Optional[str] = None  # For Slack/Discord
    username: str = "SkywarnPlus-NG"
    icon_url: Optional[str] = None
    color: str = "#dc3545"  # Default red color for alerts


class WebhookNotifier:
    """Webhook notification system for free integrations."""
    
    def __init__(self, config: WebhookConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{config.provider.value}")
        self.session: Optional[aiohttp.ClientSession] = None
    
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
    
    async def send_alert_webhook(
        self, 
        alert: WeatherAlert,
        custom_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send weather alert via webhook.
        
        Args:
            alert: Weather alert to send
            custom_message: Custom message (optional)
            
        Returns:
            Delivery result
        """
        try:
            # Generate webhook payload
            payload = self._create_alert_payload(alert, custom_message)
            
            # Send webhook
            result = await self._send_webhook(payload)
            
            return {
                "success": True,
                "alert_id": alert.id,
                "provider": self.config.provider.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **result
            }
            
        except Exception as e:
            self.logger.error(f"Failed to send alert webhook: {e}")
            return {
                "success": False,
                "error": str(e),
                "alert_id": alert.id,
                "provider": self.config.provider.value,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def send_notification_webhook(
        self,
        title: str,
        message: str,
        color: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Send general notification via webhook.
        
        Args:
            title: Notification title
            message: Notification message
            color: Color for the notification (optional)
            fields: Additional fields (optional)
            
        Returns:
            Delivery result
        """
        try:
            # Generate webhook payload
            payload = self._create_notification_payload(title, message, color, fields)
            
            # Send webhook
            result = await self._send_webhook(payload)
            
            return {
                "success": True,
                "provider": self.config.provider.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **result
            }
            
        except Exception as e:
            self.logger.error(f"Failed to send notification webhook: {e}")
            return {
                "success": False,
                "error": str(e),
                "provider": self.config.provider.value,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def _create_alert_payload(self, alert: WeatherAlert, custom_message: Optional[str] = None) -> Dict[str, Any]:
        """Create webhook payload for weather alert."""
        if self.config.provider == WebhookProvider.SLACK:
            return self._create_slack_alert_payload(alert, custom_message)
        elif self.config.provider == WebhookProvider.DISCORD:
            return self._create_discord_alert_payload(alert, custom_message)
        elif self.config.provider == WebhookProvider.TEAMS:
            return self._create_teams_alert_payload(alert, custom_message)
        else:
            return self._create_generic_alert_payload(alert, custom_message)
    
    def _create_slack_alert_payload(self, alert: WeatherAlert, custom_message: Optional[str] = None) -> Dict[str, Any]:
        """Create Slack webhook payload."""
        # Determine color based on severity
        color_map = {
            "Minor": "#ffc107",
            "Moderate": "#fd7e14", 
            "Severe": "#dc3545",
            "Extreme": "#6f42c1"
        }
        color = color_map.get(alert.severity.value, self.config.color)
        
        # Create fields
        fields = [
            {
                "title": "Area",
                "value": alert.area_desc,
                "short": True
            },
            {
                "title": "Severity",
                "value": alert.severity.value,
                "short": True
            },
            {
                "title": "Urgency",
                "value": alert.urgency.value,
                "short": True
            },
            {
                "title": "Certainty",
                "value": alert.certainty.value,
                "short": True
            },
            {
                "title": "Effective",
                "value": alert.effective.strftime('%Y-%m-%d %H:%M UTC') if alert.effective else 'N/A',
                "short": True
            },
            {
                "title": "Expires",
                "value": alert.expires.strftime('%Y-%m-%d %H:%M UTC') if alert.expires else 'N/A',
                "short": True
            }
        ]
        
        # Add description if available
        if alert.description:
            fields.append({
                "title": "Description",
                "value": alert.description[:1000] + "..." if len(alert.description) > 1000 else alert.description,
                "short": False
            })
        
        # Add instructions if available
        if alert.instruction:
            fields.append({
                "title": "Instructions",
                "value": alert.instruction[:1000] + "..." if len(alert.instruction) > 1000 else alert.instruction,
                "short": False
            })
        
        payload = {
            "username": self.config.username,
            "icon_url": self.config.icon_url,
            "channel": self.config.channel,
            "attachments": [
                {
                    "color": color,
                    "title": f"⚠️ {alert.event}",
                    "title_link": f"https://www.weather.gov/alerts/{alert.id}",
                    "text": custom_message or f"Weather alert for {alert.area_desc}",
                    "fields": fields,
                    "footer": "SkywarnPlus-NG",
                    "ts": int(alert.sent.timestamp()) if alert.sent else int(datetime.now(timezone.utc).timestamp())
                }
            ]
        }
        
        return payload
    
    def _create_discord_alert_payload(self, alert: WeatherAlert, custom_message: Optional[str] = None) -> Dict[str, Any]:
        """Create Discord webhook payload."""
        # Determine color based on severity
        color_map = {
            "Minor": 0xffc107,
            "Moderate": 0xfd7e14,
            "Severe": 0xdc3545,
            "Extreme": 0x6f42c1
        }
        color = color_map.get(alert.severity.value, 0xdc3545)
        
        # Create embed
        embed = {
            "title": f"⚠️ {alert.event}",
            "description": custom_message or f"Weather alert for {alert.area_desc}",
            "color": color,
            "fields": [
                {
                    "name": "Area",
                    "value": alert.area_desc,
                    "inline": True
                },
                {
                    "name": "Severity",
                    "value": alert.severity.value,
                    "inline": True
                },
                {
                    "name": "Urgency",
                    "value": alert.urgency.value,
                    "inline": True
                },
                {
                    "name": "Certainty",
                    "value": alert.certainty.value,
                    "inline": True
                },
                {
                    "name": "Effective",
                    "value": alert.effective.strftime('%Y-%m-%d %H:%M UTC') if alert.effective else 'N/A',
                    "inline": True
                },
                {
                    "name": "Expires",
                    "value": alert.expires.strftime('%Y-%m-%d %H:%M UTC') if alert.expires else 'N/A',
                    "inline": True
                }
            ],
            "footer": {
                "text": "SkywarnPlus-NG"
            },
            "timestamp": alert.sent.isoformat() if alert.sent else datetime.now(timezone.utc).isoformat()
        }
        
        # Add description if available
        if alert.description:
            embed["fields"].append({
                "name": "Description",
                "value": alert.description[:1000] + "..." if len(alert.description) > 1000 else alert.description,
                "inline": False
            })
        
        # Add instructions if available
        if alert.instruction:
            embed["fields"].append({
                "name": "Instructions",
                "value": alert.instruction[:1000] + "..." if len(alert.instruction) > 1000 else alert.instruction,
                "inline": False
            })
        
        payload = {
            "username": self.config.username,
            "avatar_url": self.config.icon_url,
            "embeds": [embed]
        }
        
        return payload
    
    def _create_teams_alert_payload(self, alert: WeatherAlert, custom_message: Optional[str] = None) -> Dict[str, Any]:
        """Create Microsoft Teams webhook payload."""
        # Determine color based on severity
        color_map = {
            "Minor": "warning",
            "Moderate": "warning",
            "Severe": "attention",
            "Extreme": "attention"
        }
        color = color_map.get(alert.severity.value, "attention")
        
        # Create facts
        facts = [
            {"name": "Area", "value": alert.area_desc},
            {"name": "Severity", "value": alert.severity.value},
            {"name": "Urgency", "value": alert.urgency.value},
            {"name": "Certainty", "value": alert.certainty.value},
            {"name": "Effective", "value": alert.effective.strftime('%Y-%m-%d %H:%M UTC') if alert.effective else 'N/A'},
            {"name": "Expires", "value": alert.expires.strftime('%Y-%m-%d %H:%M UTC') if alert.expires else 'N/A'}
        ]
        
        # Add description if available
        if alert.description:
            facts.append({"name": "Description", "value": alert.description[:1000] + "..." if len(alert.description) > 1000 else alert.description})
        
        # Add instructions if available
        if alert.instruction:
            facts.append({"name": "Instructions", "value": alert.instruction[:1000] + "..." if len(alert.instruction) > 1000 else alert.instruction})
        
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": self.config.color,
            "summary": f"Weather Alert: {alert.event}",
            "sections": [
                {
                    "activityTitle": f"⚠️ {alert.event}",
                    "activitySubtitle": custom_message or f"Weather alert for {alert.area_desc}",
                    "activityImage": self.config.icon_url,
                    "facts": facts,
                    "markdown": True
                }
            ]
        }
        
        return payload
    
    def _create_generic_alert_payload(self, alert: WeatherAlert, custom_message: Optional[str] = None) -> Dict[str, Any]:
        """Create generic webhook payload."""
        return {
            "alert_type": "weather_alert",
            "event": alert.event,
            "area": alert.area_desc,
            "severity": alert.severity.value,
            "urgency": alert.urgency.value,
            "certainty": alert.certainty.value,
            "description": alert.description,
            "instruction": alert.instruction,
            "effective": alert.effective.isoformat() if alert.effective else None,
            "expires": alert.expires.isoformat() if alert.expires else None,
            "sent": alert.sent.isoformat() if alert.sent else None,
            "alert_id": alert.id,
            "message": custom_message or f"Weather alert: {alert.event} for {alert.area_desc}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "SkywarnPlus-NG"
        }
    
    def _create_notification_payload(
        self, 
        title: str, 
        message: str, 
        color: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Create webhook payload for general notification."""
        if self.config.provider == WebhookProvider.SLACK:
            return self._create_slack_notification_payload(title, message, color, fields)
        elif self.config.provider == WebhookProvider.DISCORD:
            return self._create_discord_notification_payload(title, message, color, fields)
        elif self.config.provider == WebhookProvider.TEAMS:
            return self._create_teams_notification_payload(title, message, color, fields)
        else:
            return self._create_generic_notification_payload(title, message, color, fields)
    
    def _create_slack_notification_payload(
        self, 
        title: str, 
        message: str, 
        color: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Create Slack notification payload."""
        payload = {
            "username": self.config.username,
            "icon_url": self.config.icon_url,
            "channel": self.config.channel,
            "attachments": [
                {
                    "color": color or self.config.color,
                    "title": title,
                    "text": message,
                    "fields": fields or [],
                    "footer": "SkywarnPlus-NG",
                    "ts": int(datetime.now(timezone.utc).timestamp())
                }
            ]
        }
        return payload
    
    def _create_discord_notification_payload(
        self, 
        title: str, 
        message: str, 
        color: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Create Discord notification payload."""
        color_map = {
            "red": 0xdc3545,
            "orange": 0xfd7e14,
            "yellow": 0xffc107,
            "green": 0x28a745,
            "blue": 0x007bff,
            "purple": 0x6f42c1
        }
        color_value = color_map.get(color, 0xdc3545) if color else 0xdc3545
        
        embed = {
            "title": title,
            "description": message,
            "color": color_value,
            "fields": fields or [],
            "footer": {
                "text": "SkywarnPlus-NG"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        payload = {
            "username": self.config.username,
            "avatar_url": self.config.icon_url,
            "embeds": [embed]
        }
        return payload
    
    def _create_teams_notification_payload(
        self, 
        title: str, 
        message: str, 
        color: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Create Teams notification payload."""
        facts = fields or []
        
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color or self.config.color,
            "summary": title,
            "sections": [
                {
                    "activityTitle": title,
                    "activitySubtitle": message,
                    "activityImage": self.config.icon_url,
                    "facts": facts,
                    "markdown": True
                }
            ]
        }
        return payload
    
    def _create_generic_notification_payload(
        self, 
        title: str, 
        message: str, 
        color: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Create generic notification payload."""
        return {
            "notification_type": "general",
            "title": title,
            "message": message,
            "color": color,
            "fields": fields or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "SkywarnPlus-NG"
        }
    
    async def _send_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send webhook with retry logic."""
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            )
        
        last_error = None
        
        for attempt in range(self.config.retry_count + 1):
            try:
                async with self.session.post(
                    self.config.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    # Accept 200 (OK) and 204 (No Content) as success
                    # Discord webhooks return 204 on success
                    if response.status in (200, 204):
                        self.logger.debug(f"Webhook sent successfully (attempt {attempt + 1}, status {response.status})")
                        return {
                            "status_code": response.status,
                            "attempt": attempt + 1
                        }
                    else:
                        error_text = await response.text()
                        last_error = f"HTTP {response.status}: {error_text}"
                        self.logger.warning(f"Webhook failed with status {response.status} (attempt {attempt + 1})")
                        
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"Webhook attempt {attempt + 1} failed: {e}")
            
            # Wait before retry (except on last attempt)
            if attempt < self.config.retry_count:
                await asyncio.sleep(self.config.retry_delay_seconds)
        
        # All attempts failed
        raise Exception(f"Webhook failed after {self.config.retry_count + 1} attempts. Last error: {last_error}")
    
    async def test_webhook(self) -> bool:
        """Test webhook connection."""
        try:
            test_payload = {
                "test": True,
                "message": "SkywarnPlus-NG webhook test",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            result = await self._send_webhook(test_payload)
            self.logger.info(f"Webhook test successful for {self.config.provider.value}")
            return True
            
        except Exception as e:
            self.logger.error(f"Webhook test failed for {self.config.provider.value}: {e}")
            return False
    
    @classmethod
    def create_slack_config(
        cls,
        webhook_url: str,
        channel: Optional[str] = None,
        username: str = "SkywarnPlus-NG",
        icon_url: Optional[str] = None
    ) -> WebhookConfig:
        """Create Slack webhook configuration."""
        return WebhookConfig(
            provider=WebhookProvider.SLACK,
            webhook_url=webhook_url,
            channel=channel,
            username=username,
            icon_url=icon_url
        )
    
    @classmethod
    def create_discord_config(
        cls,
        webhook_url: str,
        username: str = "SkywarnPlus-NG",
        icon_url: Optional[str] = None
    ) -> WebhookConfig:
        """Create Discord webhook configuration."""
        return WebhookConfig(
            provider=WebhookProvider.DISCORD,
            webhook_url=webhook_url,
            username=username,
            icon_url=icon_url
        )
    
    @classmethod
    def create_teams_config(
        cls,
        webhook_url: str,
        username: str = "SkywarnPlus-NG",
        icon_url: Optional[str] = None
    ) -> WebhookConfig:
        """Create Microsoft Teams webhook configuration."""
        return WebhookConfig(
            provider=WebhookProvider.TEAMS,
            webhook_url=webhook_url,
            username=username,
            icon_url=icon_url
        )
