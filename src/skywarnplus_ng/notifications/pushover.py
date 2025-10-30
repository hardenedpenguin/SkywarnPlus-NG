"""
PushOver notification system for SkywarnPlus-NG.
Uses PushOver API for cross-platform notifications.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import aiohttp

from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)


@dataclass
class PushOverConfig:
    """PushOver notification configuration."""
    
    api_token: str
    user_key: str
    enabled: bool = True
    timeout_seconds: int = 30
    retry_count: int = 3
    retry_delay_seconds: int = 5
    priority: int = 0  # -2 to 2, 0 is normal
    sound: Optional[str] = None  # Use default sound if None


class PushOverNotifier:
    """PushOver notification system."""
    
    PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
    
    # Priority levels
    PRIORITY_LOWEST = -2  # No notification
    PRIORITY_LOW = -1     # No sound, no vibration
    PRIORITY_NORMAL = 0   # Default sound and vibration
    PRIORITY_HIGH = 1     # Bypass quiet hours, default sound
    PRIORITY_EMERGENCY = 2  # Require acknowledgment, repeat until acknowledged
    
    # Sound options (use None for default device sound)
    SOUNDS = {
        "pushover": "Pushover",
        "bike": "Bike",
        "bugle": "Bugle",
        "cashregister": "Cash Register",
        "classical": "Classical",
        "cosmic": "Cosmic",
        "falling": "Falling",
        "gamelan": "Gamelan",
        "incoming": "Incoming",
        "intermission": "Intermission",
        "magic": "Magic",
        "mechanical": "Mechanical",
        "pianobar": "Piano Bar",
        "siren": "Siren",
        "spacealarm": "Space Alarm",
        "tugboat": "Tug Boat",
        "alien": "Alien Alarm (long)",
        "climb": "Climb (long)",
        "persistent": "Persistent (long)",
        "echo": "Echo (long)",
        "updown": "Up Down (long)",
        "vibrate": "Vibrate Only",
        "none": "None (silent)"
    }
    
    def __init__(self, config: PushOverConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.PushOverNotifier")
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
    
    def _determine_priority_and_sound(self, alert: WeatherAlert) -> tuple[int, str]:
        """
        Determine priority level and sound based on alert severity.
        
        Returns:
            Tuple of (priority, sound)
        """
        # Determine priority based on severity
        if alert.severity.value == "Extreme":
            if alert.urgency.value == "Immediate":
                priority = self.PRIORITY_EMERGENCY
                sound = "siren"
            else:
                priority = self.PRIORITY_HIGH
                sound = "persistent"
        elif alert.severity.value == "Severe":
            if alert.urgency.value == "Immediate":
                priority = self.PRIORITY_HIGH
                sound = "persistent"
            else:
                priority = self.PRIORITY_NORMAL
                sound = "pianobar"
        elif alert.severity.value == "Moderate":
            priority = self.PRIORITY_NORMAL
            sound = "incoming"
        else:  # Minor or Unknown
            priority = self.PRIORITY_NORMAL
            sound = "magic"
        
        # Allow override from config
        if self.config.priority is not None:
            priority = self.config.priority
        if self.config.sound is not None:
            sound = self.config.sound
        
        return priority, sound
    
    async def send_alert_push(
        self, 
        alert: WeatherAlert,
        user_keys: Optional[List[str]] = None,
        custom_title: Optional[str] = None,
        custom_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send weather alert push notification via PushOver.
        
        Args:
            alert: Weather alert to send
            user_keys: List of PushOver user keys (uses config user_key if not provided)
            custom_title: Custom notification title (optional)
            custom_message: Custom notification message (optional)
            
        Returns:
            Delivery result dictionary
        """
        try:
            # Use provided user keys or fall back to config
            user_keys_to_use = user_keys or [self.config.user_key]
            
            priority, sound = self._determine_priority_and_sound(alert)
            
            # Create title
            title = custom_title or f"{alert.severity.value}: {alert.event}"
            
            # Create message (truncate description if needed)
            if custom_message:
                message = custom_message
            else:
                # Truncate description to PushOver's 1024 character limit
                max_length = 500  # Leave room for additional info
                description = alert.description[:max_length]
                if len(alert.description) > max_length:
                    description += "..."
                
                message = f"{alert.area_desc}\n\n{description}"
                if alert.instruction:
                    instruction = alert.instruction[:200]
                    message += f"\n\n📋 {instruction}"
            
            # Build URL with title for rich formatting
            url = f"https://alerts.weather.gov/details/{alert.id}"
            url_title = f"View full alert details"
            
            # Additional parameters for emergency priority
            additional_params = {}
            if priority == self.PRIORITY_EMERGENCY:
                # Emergency requires acknowledgment
                additional_params["retry"] = 300  # Retry every 5 minutes
                additional_params["expire"] = 3600  # Give up after 1 hour
            
            results = []
            
            # Send to each user
            for user_key in user_keys_to_use:
                payload = {
                    "token": self.config.api_token,
                    "user": user_key,
                    "title": title,
                    "message": message,
                    "priority": str(priority),
                    "sound": sound,
                    "url": url,
                    "url_title": url_title,
                    "timestamp": int(alert.effective.timestamp()) if alert.effective else int(datetime.now(timezone.utc).timestamp())
                }
                payload.update(additional_params)
                
                result = await self._send_pushover_message(payload)
                result["user_key"] = user_key
                results.append(result)
            
            # Aggregate results
            success_count = sum(1 for r in results if r.get("success", False))
            failed_count = len(results) - success_count
            
            return {
                "success": failed_count == 0,
                "sent_count": success_count,
                "failed_count": failed_count,
                "results": results,
                "alert_id": alert.id,
                "priority": priority,
                "sound": sound,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to send PushOver alert notification: {e}")
            return {
                "success": False,
                "error": str(e),
                "alert_id": alert.id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def send_notification_push(
        self,
        title: str,
        message: str,
        user_keys: Optional[List[str]] = None,
        priority: Optional[int] = None,
        sound: Optional[str] = None,
        url: Optional[str] = None,
        url_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send general push notification via PushOver.
        
        Args:
            title: Notification title
            message: Notification message
            user_keys: List of PushOver user keys (uses config user_key if not provided)
            priority: Notification priority (-2 to 2, uses config priority if not provided)
            sound: Sound name to use (uses config sound if not provided)
            url: URL to include with notification (optional)
            url_title: Title for the URL (optional)
            
        Returns:
            Delivery result dictionary
        """
        try:
            # Use provided user keys or fall back to config
            user_keys_to_use = user_keys or [self.config.user_key]
            
            # Use provided parameters or fall back to config
            priority_to_use = priority if priority is not None else self.config.priority
            sound_to_use = sound if sound is not None else (self.config.sound or "pushover")
            
            results = []
            
            # Send to each user
            for user_key in user_keys_to_use:
                payload = {
                    "token": self.config.api_token,
                    "user": user_key,
                    "title": title,
                    "message": message,
                    "priority": str(priority_to_use),
                    "sound": sound_to_use,
                    "timestamp": int(datetime.now(timezone.utc).timestamp())
                }
                
                if url:
                    payload["url"] = url
                if url_title:
                    payload["url_title"] = url_title
                
                result = await self._send_pushover_message(payload)
                result["user_key"] = user_key
                results.append(result)
            
            # Aggregate results
            success_count = sum(1 for r in results if r.get("success", False))
            failed_count = len(results) - success_count
            
            return {
                "success": failed_count == 0,
                "sent_count": success_count,
                "failed_count": failed_count,
                "results": results,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to send PushOver notification: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _send_pushover_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to PushOver API."""
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            )
        
        last_error = None
        for attempt in range(self.config.retry_count + 1):
            try:
                async with self.session.post(self.PUSHOVER_API_URL, data=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Check for errors in response
                        if result.get("status") == 1:
                            self.logger.debug(f"PushOver notification sent successfully (attempt {attempt + 1})")
                            return {
                                "success": True,
                                "request_id": result.get("request"),
                                "attempt": attempt + 1
                            }
                        else:
                            error_msg = result.get("errors", ["Unknown error"])
                            last_error = f"API error: {', '.join(error_msg)}"
                            self.logger.warning(f"PushOver API returned error (attempt {attempt + 1}): {last_error}")
                    else:
                        error_text = await response.text()
                        last_error = f"HTTP {response.status}: {error_text}"
                        self.logger.warning(f"PushOver request failed with status {response.status} (attempt {attempt + 1})")
                        
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"PushOver attempt {attempt + 1} failed: {e}")
            
            # Wait before retry (except on last attempt)
            if attempt < self.config.retry_count:
                await asyncio.sleep(self.config.retry_delay_seconds)
        
        # All attempts failed
        raise Exception(f"PushOver notification failed after {self.config.retry_count + 1} attempts. Last error: {last_error}")
    
    async def send_all_clear(self, counties: List[str]) -> Dict[str, Any]:
        """
        Send all-clear notification.
        
        Args:
            counties: List of county names that are now clear
            
        Returns:
            Delivery result dictionary
        """
        title = "All Clear - Weather Alerts Ended"
        message = f"Weather alerts have ended for: {', '.join(counties)}"
        
        # Use a gentler sound for all-clear
        return await self.send_notification_push(
            title=title,
            message=message,
            priority=self.PRIORITY_NORMAL,
            sound="magic"
        )
    
    async def test_pushover(self, user_key: Optional[str] = None) -> bool:
        """
        Test PushOver notification delivery.
        
        Args:
            user_key: Optional user key to test (uses config user_key if not provided)
            
        Returns:
            True if test was successful, False otherwise
        """
        try:
            result = await self.send_notification_push(
                title="SkywarnPlus-NG Test",
                message="This is a test notification from SkywarnPlus-NG. If you received this, PushOver integration is working correctly!",
                user_keys=[user_key] if user_key else None,
                sound="pushover"
            )
            
            if result.get("success", False):
                self.logger.info("PushOver notification test successful")
                return True
            else:
                self.logger.error(f"PushOver notification test failed: {result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            self.logger.error(f"PushOver notification test failed: {e}")
            return False
    
    @classmethod
    def create_config(
        cls,
        api_token: str,
        user_key: str,
        priority: int = 0,
        sound: Optional[str] = None,
        enabled: bool = True
    ) -> PushOverConfig:
        """Create PushOver configuration."""
        return PushOverConfig(
            api_token=api_token,
            user_key=user_key,
            priority=priority,
            sound=sound,
            enabled=enabled
        )

