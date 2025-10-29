"""
Push notification system for SkywarnPlus-NG.
Uses Firebase Cloud Messaging (FCM) free tier.
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


class PushProvider(Enum):
    """Supported push notification providers."""
    FCM = "fcm"  # Firebase Cloud Messaging (free)
    WEB_PUSH = "web_push"  # Web Push Protocol (free)


@dataclass
class PushConfig:
    """Push notification configuration."""
    
    provider: PushProvider
    enabled: bool = True
    timeout_seconds: int = 30
    retry_count: int = 3
    retry_delay_seconds: int = 5
    
    # FCM-specific settings
    fcm_server_key: Optional[str] = None
    fcm_project_id: Optional[str] = None
    
    # Web Push settings
    vapid_public_key: Optional[str] = None
    vapid_private_key: Optional[str] = None
    vapid_email: Optional[str] = None


class PushNotifier:
    """Push notification system using free services."""
    
    def __init__(self, config: PushConfig):
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
    
    async def send_alert_push(
        self, 
        alert: WeatherAlert,
        device_tokens: List[str],
        custom_title: Optional[str] = None,
        custom_body: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send weather alert push notification.
        
        Args:
            alert: Weather alert to send
            device_tokens: List of device tokens/registration IDs
            custom_title: Custom notification title (optional)
            custom_body: Custom notification body (optional)
            
        Returns:
            Delivery result
        """
        try:
            if self.config.provider == PushProvider.FCM:
                return await self._send_fcm_alert(alert, device_tokens, custom_title, custom_body)
            elif self.config.provider == PushProvider.WEB_PUSH:
                return await self._send_web_push_alert(alert, device_tokens, custom_title, custom_body)
            else:
                raise ValueError(f"Unsupported push provider: {self.config.provider}")
                
        except Exception as e:
            self.logger.error(f"Failed to send push notification: {e}")
            return {
                "success": False,
                "error": str(e),
                "alert_id": alert.id,
                "provider": self.config.provider.value,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def send_notification_push(
        self,
        title: str,
        body: str,
        device_tokens: List[str],
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send general push notification.
        
        Args:
            title: Notification title
            body: Notification body
            device_tokens: List of device tokens/registration IDs
            data: Additional data payload (optional)
            
        Returns:
            Delivery result
        """
        try:
            if self.config.provider == PushProvider.FCM:
                return await self._send_fcm_notification(title, body, device_tokens, data)
            elif self.config.provider == PushProvider.WEB_PUSH:
                return await self._send_web_push_notification(title, body, device_tokens, data)
            else:
                raise ValueError(f"Unsupported push provider: {self.config.provider}")
                
        except Exception as e:
            self.logger.error(f"Failed to send push notification: {e}")
            return {
                "success": False,
                "error": str(e),
                "provider": self.config.provider.value,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _send_fcm_alert(
        self, 
        alert: WeatherAlert,
        device_tokens: List[str],
        custom_title: Optional[str] = None,
        custom_body: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send FCM alert notification."""
        if not self.config.fcm_server_key:
            raise ValueError("FCM server key not configured")
        
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            )
        
        # Create FCM payload
        title = custom_title or f"Weather Alert: {alert.event}"
        body = custom_body or f"{alert.area_desc} - {alert.severity.value} severity"
        
        # Determine notification icon and color based on severity
        icon_map = {
            "Minor": "⚠️",
            "Moderate": "⚠️", 
            "Severe": "🚨",
            "Extreme": "🚨"
        }
        color_map = {
            "Minor": "#ffc107",
            "Moderate": "#fd7e14",
            "Severe": "#dc3545", 
            "Extreme": "#6f42c1"
        }
        
        icon = icon_map.get(alert.severity.value, "⚠️")
        color = color_map.get(alert.severity.value, "#dc3545")
        
        payload = {
            "registration_ids": device_tokens,
            "notification": {
                "title": f"{icon} {title}",
                "body": body,
                "icon": "ic_weather_alert",
                "color": color,
                "sound": "default",
                "click_action": "WEATHER_ALERT_ACTIVITY"
            },
            "data": {
                "alert_id": alert.id,
                "event": alert.event,
                "area": alert.area_desc,
                "severity": alert.severity.value,
                "urgency": alert.urgency.value,
                "certainty": alert.certainty.value,
                "effective": alert.effective.isoformat() if alert.effective else None,
                "expires": alert.expires.isoformat() if alert.expires else None,
                "description": alert.description or "",
                "instruction": alert.instruction or "",
                "type": "weather_alert"
            },
            "priority": "high",
            "time_to_live": 3600  # 1 hour
        }
        
        # Send to FCM
        headers = {
            "Authorization": f"key={self.config.fcm_server_key}",
            "Content-Type": "application/json"
        }
        
        url = "https://fcm.googleapis.com/fcm/send"
        
        last_error = None
        for attempt in range(self.config.retry_count + 1):
            try:
                async with self.session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.logger.debug(f"FCM notification sent successfully (attempt {attempt + 1})")
                        return {
                            "success": True,
                            "sent_count": result.get("success", 0),
                            "failed_count": result.get("failure", 0),
                            "attempt": attempt + 1,
                            "fcm_response": result
                        }
                    else:
                        error_text = await response.text()
                        last_error = f"HTTP {response.status}: {error_text}"
                        self.logger.warning(f"FCM request failed with status {response.status} (attempt {attempt + 1})")
                        
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"FCM attempt {attempt + 1} failed: {e}")
            
            # Wait before retry (except on last attempt)
            if attempt < self.config.retry_count:
                await asyncio.sleep(self.config.retry_delay_seconds)
        
        # All attempts failed
        raise Exception(f"FCM notification failed after {self.config.retry_count + 1} attempts. Last error: {last_error}")
    
    async def _send_fcm_notification(
        self,
        title: str,
        body: str,
        device_tokens: List[str],
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send FCM general notification."""
        if not self.config.fcm_server_key:
            raise ValueError("FCM server key not configured")
        
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            )
        
        payload = {
            "registration_ids": device_tokens,
            "notification": {
                "title": title,
                "body": body,
                "icon": "ic_notification",
                "sound": "default"
            },
            "data": data or {},
            "priority": "normal"
        }
        
        headers = {
            "Authorization": f"key={self.config.fcm_server_key}",
            "Content-Type": "application/json"
        }
        
        url = "https://fcm.googleapis.com/fcm/send"
        
        last_error = None
        for attempt in range(self.config.retry_count + 1):
            try:
                async with self.session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.logger.debug(f"FCM notification sent successfully (attempt {attempt + 1})")
                        return {
                            "success": True,
                            "sent_count": result.get("success", 0),
                            "failed_count": result.get("failure", 0),
                            "attempt": attempt + 1,
                            "fcm_response": result
                        }
                    else:
                        error_text = await response.text()
                        last_error = f"HTTP {response.status}: {error_text}"
                        self.logger.warning(f"FCM request failed with status {response.status} (attempt {attempt + 1})")
                        
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"FCM attempt {attempt + 1} failed: {e}")
            
            # Wait before retry (except on last attempt)
            if attempt < self.config.retry_count:
                await asyncio.sleep(self.config.retry_delay_seconds)
        
        # All attempts failed
        raise Exception(f"FCM notification failed after {self.config.retry_count + 1} attempts. Last error: {last_error}")
    
    async def _send_web_push_alert(
        self, 
        alert: WeatherAlert,
        device_tokens: List[str],
        custom_title: Optional[str] = None,
        custom_body: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send Web Push alert notification."""
        # Web Push implementation would go here
        # This is a placeholder for future implementation
        self.logger.warning("Web Push notifications not yet implemented")
        return {
            "success": False,
            "error": "Web Push notifications not yet implemented",
            "alert_id": alert.id,
            "provider": "web_push"
        }
    
    async def _send_web_push_notification(
        self,
        title: str,
        body: str,
        device_tokens: List[str],
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send Web Push general notification."""
        # Web Push implementation would go here
        # This is a placeholder for future implementation
        self.logger.warning("Web Push notifications not yet implemented")
        return {
            "success": False,
            "error": "Web Push notifications not yet implemented",
            "provider": "web_push"
        }
    
    async def test_push_notification(self, device_token: str) -> bool:
        """Test push notification delivery."""
        try:
            result = await self.send_notification_push(
                title="SkywarnPlus-NG Test",
                body="This is a test notification from SkywarnPlus-NG",
                device_tokens=[device_token],
                data={"test": True}
            )
            
            if result.get("success", False):
                self.logger.info(f"Push notification test successful for {self.config.provider.value}")
                return True
            else:
                self.logger.error(f"Push notification test failed: {result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            self.logger.error(f"Push notification test failed for {self.config.provider.value}: {e}")
            return False
    
    @classmethod
    def create_fcm_config(
        cls,
        fcm_server_key: str,
        fcm_project_id: Optional[str] = None
    ) -> PushConfig:
        """Create FCM push notification configuration."""
        return PushConfig(
            provider=PushProvider.FCM,
            fcm_server_key=fcm_server_key,
            fcm_project_id=fcm_project_id
        )
    
    @classmethod
    def create_web_push_config(
        cls,
        vapid_public_key: str,
        vapid_private_key: str,
        vapid_email: str
    ) -> PushConfig:
        """Create Web Push configuration."""
        return PushConfig(
            provider=PushProvider.WEB_PUSH,
            vapid_public_key=vapid_public_key,
            vapid_private_key=vapid_private_key,
            vapid_email=vapid_email
        )
