"""
Subscriber management system for SkywarnPlus-NG.
Handles user subscriptions and notification preferences.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path

from ..core.models import WeatherAlert, AlertSeverity, AlertUrgency, AlertCertainty

logger = logging.getLogger(__name__)


class NotificationMethod(Enum):
    """Notification delivery methods."""
    EMAIL = "email"
    WEBHOOK = "webhook"
    PUSH = "push"
    SMS = "sms"  # Future implementation


class SubscriptionStatus(Enum):
    """Subscription status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    UNSUBSCRIBED = "unsubscribed"


@dataclass
class SubscriptionPreferences:
    """User subscription preferences."""
    
    # Geographic preferences
    counties: List[str] = field(default_factory=list)
    states: List[str] = field(default_factory=list)
    custom_areas: List[str] = field(default_factory=list)
    
    # Alert type preferences
    enabled_severities: Set[AlertSeverity] = field(default_factory=lambda: {
        AlertSeverity.MINOR, AlertSeverity.MODERATE, 
        AlertSeverity.SEVERE, AlertSeverity.EXTREME
    })
    enabled_urgencies: Set[AlertUrgency] = field(default_factory=lambda: {
        AlertUrgency.FUTURE, AlertUrgency.EXPECTED, AlertUrgency.IMMEDIATE
    })
    enabled_certainties: Set[AlertCertainty] = field(default_factory=lambda: {
        AlertCertainty.POSSIBLE, AlertCertainty.LIKELY, AlertCertainty.OBSERVED
    })
    
    # Event type preferences
    enabled_events: Set[str] = field(default_factory=set)  # Empty means all events
    blocked_events: Set[str] = field(default_factory=set)
    
    # Delivery preferences
    enabled_methods: Set[NotificationMethod] = field(default_factory=lambda: {NotificationMethod.EMAIL})
    immediate_delivery: bool = True
    batch_delivery: bool = False
    batch_interval_minutes: int = 15
    
    # Time preferences
    quiet_hours_start: Optional[str] = None  # HH:MM format
    quiet_hours_end: Optional[str] = None    # HH:MM format
    timezone: str = "UTC"
    
    # Frequency limits
    max_notifications_per_hour: int = 10
    max_notifications_per_day: int = 50
    
    def __post_init__(self):
        # Convert sets to lists for JSON serialization
        if isinstance(self.enabled_severities, set):
            self.enabled_severities = list(self.enabled_severities)
        if isinstance(self.enabled_urgencies, set):
            self.enabled_urgencies = list(self.enabled_urgencies)
        if isinstance(self.enabled_certainties, set):
            self.enabled_certainties = list(self.enabled_certainties)
        if isinstance(self.enabled_events, set):
            self.enabled_events = list(self.enabled_events)
        if isinstance(self.blocked_events, set):
            self.blocked_events = list(self.blocked_events)
        if isinstance(self.enabled_methods, set):
            self.enabled_methods = list(self.enabled_methods)


@dataclass
class Subscriber:
    """Subscriber information."""
    
    subscriber_id: str
    name: str
    email: str
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    preferences: SubscriptionPreferences = field(default_factory=SubscriptionPreferences)
    
    # Contact information
    phone: Optional[str] = None
    webhook_url: Optional[str] = None
    push_tokens: List[str] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_notification: Optional[datetime] = None
    notification_count_today: int = 0
    notification_count_hour: int = 0
    
    # Rate limiting
    last_hour_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_day_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self):
        if not self.preferences:
            self.preferences = SubscriptionPreferences()
    
    def should_receive_alert(self, alert: WeatherAlert) -> bool:
        """Check if subscriber should receive this alert."""
        # Check if subscriber is active
        if self.status != SubscriptionStatus.ACTIVE:
            return False
        
        # Check rate limits
        if not self._check_rate_limits():
            return False
        
        # Check quiet hours
        if not self._check_quiet_hours():
            return False
        
        # Check geographic preferences
        if not self._check_geographic_preferences(alert):
            return False
        
        # Check severity preferences
        if alert.severity not in self.preferences.enabled_severities:
            return False
        
        # Check urgency preferences
        if alert.urgency not in self.preferences.enabled_urgencies:
            return False
        
        # Check certainty preferences
        if alert.certainty not in self.preferences.enabled_certainties:
            return False
        
        # Check event type preferences
        if not self._check_event_preferences(alert):
            return False
        
        return True
    
    def _check_rate_limits(self) -> bool:
        """Check if subscriber is within rate limits."""
        now = datetime.now(timezone.utc)
        
        # Reset hourly counter if needed
        if (now - self.last_hour_reset).total_seconds() >= 3600:
            self.notification_count_hour = 0
            self.last_hour_reset = now
        
        # Reset daily counter if needed
        if (now - self.last_day_reset).total_seconds() >= 86400:
            self.notification_count_today = 0
            self.last_day_reset = now
        
        # Check limits
        if self.notification_count_hour >= self.preferences.max_notifications_per_hour:
            return False
        
        if self.notification_count_today >= self.preferences.max_notifications_per_day:
            return False
        
        return True
    
    def _check_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours."""
        if not self.preferences.quiet_hours_start or not self.preferences.quiet_hours_end:
            return True
        
        try:
            from datetime import time
            now = datetime.now(timezone.utc)
            
            # Convert to subscriber's timezone (simplified - in real implementation use pytz)
            current_time = now.time()
            
            start_time = time.fromisoformat(self.preferences.quiet_hours_start)
            end_time = time.fromisoformat(self.preferences.quiet_hours_end)
            
            # Handle quiet hours that cross midnight
            if start_time <= end_time:
                return not (start_time <= current_time <= end_time)
            else:
                return not (current_time >= start_time or current_time <= end_time)
                
        except Exception as e:
            logger.warning(f"Error checking quiet hours for subscriber {self.subscriber_id}: {e}")
            return True  # Default to allowing notifications
    
    def _check_geographic_preferences(self, alert: WeatherAlert) -> bool:
        """Check if alert matches geographic preferences."""
        # Check counties
        if self.preferences.counties:
            alert_counties = set(alert.county_codes or [])
            if not alert_counties.intersection(set(self.preferences.counties)):
                return False
        
        # Check states (extract from county codes)
        if self.preferences.states:
            alert_states = set()
            if alert.county_codes:
                for county in alert.county_codes:
                    if len(county) >= 2:
                        alert_states.add(county[:2])
            
            if not alert_states.intersection(set(self.preferences.states)):
                return False
        
        # Check custom areas (simplified text matching)
        if self.preferences.custom_areas:
            area_desc_lower = alert.area_desc.lower()
            if not any(area.lower() in area_desc_lower for area in self.preferences.custom_areas):
                return False
        
        return True
    
    def _check_event_preferences(self, alert: WeatherAlert) -> bool:
        """Check if alert matches event type preferences."""
        # Check blocked events
        if self.preferences.blocked_events:
            for blocked_event in self.preferences.blocked_events:
                if blocked_event.lower() in alert.event.lower():
                    return False
        
        # Check enabled events (if specified)
        if self.preferences.enabled_events:
            for enabled_event in self.preferences.enabled_events:
                if enabled_event.lower() in alert.event.lower():
                    return True
            return False
        
        return True
    
    def record_notification(self) -> None:
        """Record that a notification was sent."""
        self.notification_count_hour += 1
        self.notification_count_today += 1
        self.last_notification = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert subscriber to dictionary for JSON serialization."""
        return {
            "subscriber_id": self.subscriber_id,
            "name": self.name,
            "email": self.email,
            "status": self.status.value,
            "preferences": {
                "counties": self.preferences.counties,
                "states": self.preferences.states,
                "custom_areas": self.preferences.custom_areas,
                "enabled_severities": [s.value for s in self.preferences.enabled_severities],
                "enabled_urgencies": [u.value for u in self.preferences.enabled_urgencies],
                "enabled_certainties": [c.value for c in self.preferences.enabled_certainties],
                "enabled_events": self.preferences.enabled_events,
                "blocked_events": self.preferences.blocked_events,
                "enabled_methods": [m.value for m in self.preferences.enabled_methods],
                "immediate_delivery": self.preferences.immediate_delivery,
                "batch_delivery": self.preferences.batch_delivery,
                "batch_interval_minutes": self.preferences.batch_interval_minutes,
                "quiet_hours_start": self.preferences.quiet_hours_start,
                "quiet_hours_end": self.preferences.quiet_hours_end,
                "timezone": self.preferences.timezone,
                "max_notifications_per_hour": self.preferences.max_notifications_per_hour,
                "max_notifications_per_day": self.preferences.max_notifications_per_day
            },
            "phone": self.phone,
            "webhook_url": self.webhook_url,
            "push_tokens": self.push_tokens,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_notification": self.last_notification.isoformat() if self.last_notification else None,
            "notification_count_today": self.notification_count_today,
            "notification_count_hour": self.notification_count_hour
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Subscriber":
        """Create subscriber from dictionary."""
        # Convert string values back to enums
        preferences_data = data.get("preferences", {})
        
        enabled_severities = {
            AlertSeverity(severity) for severity in preferences_data.get("enabled_severities", [])
        }
        enabled_urgencies = {
            AlertUrgency(urgency) for urgency in preferences_data.get("enabled_urgencies", [])
        }
        enabled_certainties = {
            AlertCertainty(certainty) for certainty in preferences_data.get("enabled_certainties", [])
        }
        enabled_methods = {
            NotificationMethod(method) for method in preferences_data.get("enabled_methods", [])
        }
        
        preferences = SubscriptionPreferences(
            counties=preferences_data.get("counties", []),
            states=preferences_data.get("states", []),
            custom_areas=preferences_data.get("custom_areas", []),
            enabled_severities=enabled_severities,
            enabled_urgencies=enabled_urgencies,
            enabled_certainties=enabled_certainties,
            enabled_events=set(preferences_data.get("enabled_events", [])),
            blocked_events=set(preferences_data.get("blocked_events", [])),
            enabled_methods=enabled_methods,
            immediate_delivery=preferences_data.get("immediate_delivery", True),
            batch_delivery=preferences_data.get("batch_delivery", False),
            batch_interval_minutes=preferences_data.get("batch_interval_minutes", 15),
            quiet_hours_start=preferences_data.get("quiet_hours_start"),
            quiet_hours_end=preferences_data.get("quiet_hours_end"),
            timezone=preferences_data.get("timezone", "UTC"),
            max_notifications_per_hour=preferences_data.get("max_notifications_per_hour", 10),
            max_notifications_per_day=preferences_data.get("max_notifications_per_day", 50)
        )
        
        subscriber = cls(
            subscriber_id=data["subscriber_id"],
            name=data["name"],
            email=data["email"],
            status=SubscriptionStatus(data.get("status", "active")),
            preferences=preferences,
            phone=data.get("phone"),
            webhook_url=data.get("webhook_url"),
            push_tokens=data.get("push_tokens", [])
        )
        
        # Set timestamps
        if "created_at" in data:
            subscriber.created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        if "updated_at" in data:
            subscriber.updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        if "last_notification" in data and data["last_notification"]:
            subscriber.last_notification = datetime.fromisoformat(data["last_notification"].replace("Z", "+00:00"))
        
        subscriber.notification_count_today = data.get("notification_count_today", 0)
        subscriber.notification_count_hour = data.get("notification_count_hour", 0)
        
        return subscriber


class SubscriberManager:
    """Manages subscribers and their preferences."""
    
    def __init__(self, data_file: Optional[Path] = None):
        self.data_file = data_file or Path("subscribers.json")
        self.subscribers: Dict[str, Subscriber] = {}
        self.logger = logging.getLogger(__name__)
        self._load_subscribers()
    
    def _load_subscribers(self) -> None:
        """Load subscribers from file."""
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for subscriber_data in data.get("subscribers", []):
                    subscriber = Subscriber.from_dict(subscriber_data)
                    self.subscribers[subscriber.subscriber_id] = subscriber
                
                self.logger.info(f"Loaded {len(self.subscribers)} subscribers")
            else:
                self.logger.info("No subscribers file found, starting with empty list")
                
        except Exception as e:
            self.logger.error(f"Failed to load subscribers: {e}")
            self.subscribers = {}
    
    def _save_subscribers(self) -> None:
        """Save subscribers to file."""
        try:
            data = {
                "subscribers": [subscriber.to_dict() for subscriber in self.subscribers.values()],
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            self.logger.debug(f"Saved {len(self.subscribers)} subscribers")
            
        except Exception as e:
            self.logger.error(f"Failed to save subscribers: {e}")
    
    def add_subscriber(self, subscriber: Subscriber) -> bool:
        """Add a new subscriber."""
        try:
            if subscriber.subscriber_id in self.subscribers:
                self.logger.warning(f"Subscriber {subscriber.subscriber_id} already exists")
                return False
            
            self.subscribers[subscriber.subscriber_id] = subscriber
            self._save_subscribers()
            self.logger.info(f"Added subscriber {subscriber.subscriber_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add subscriber: {e}")
            return False
    
    def update_subscriber(self, subscriber: Subscriber) -> bool:
        """Update an existing subscriber."""
        try:
            if subscriber.subscriber_id not in self.subscribers:
                self.logger.warning(f"Subscriber {subscriber.subscriber_id} not found")
                return False
            
            subscriber.updated_at = datetime.now(timezone.utc)
            self.subscribers[subscriber.subscriber_id] = subscriber
            self._save_subscribers()
            self.logger.info(f"Updated subscriber {subscriber.subscriber_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update subscriber: {e}")
            return False
    
    def remove_subscriber(self, subscriber_id: str) -> bool:
        """Remove a subscriber."""
        try:
            if subscriber_id not in self.subscribers:
                self.logger.warning(f"Subscriber {subscriber_id} not found")
                return False
            
            del self.subscribers[subscriber_id]
            self._save_subscribers()
            self.logger.info(f"Removed subscriber {subscriber_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove subscriber: {e}")
            return False
    
    def get_subscriber(self, subscriber_id: str) -> Optional[Subscriber]:
        """Get a subscriber by ID."""
        return self.subscribers.get(subscriber_id)
    
    def get_subscriber_by_email(self, email: str) -> Optional[Subscriber]:
        """Get a subscriber by email address."""
        for subscriber in self.subscribers.values():
            if subscriber.email.lower() == email.lower():
                return subscriber
        return None
    
    def get_subscribers_for_alert(self, alert: WeatherAlert) -> List[Subscriber]:
        """Get subscribers who should receive this alert."""
        matching_subscribers = []
        
        for subscriber in self.subscribers.values():
            if subscriber.should_receive_alert(alert):
                matching_subscribers.append(subscriber)
        
        self.logger.debug(f"Found {len(matching_subscribers)} subscribers for alert {alert.id}")
        return matching_subscribers
    
    def get_all_subscribers(self) -> List[Subscriber]:
        """Get all subscribers."""
        return list(self.subscribers.values())
    
    def get_subscriber_count(self) -> int:
        """Get total number of subscribers."""
        return len(self.subscribers)
    
    def get_active_subscriber_count(self) -> int:
        """Get number of active subscribers."""
        return sum(1 for s in self.subscribers.values() if s.status == SubscriptionStatus.ACTIVE)
    
    def get_subscriber_stats(self) -> Dict[str, Any]:
        """Get subscriber statistics."""
        total = len(self.subscribers)
        active = sum(1 for s in self.subscribers.values() if s.status == SubscriptionStatus.ACTIVE)
        inactive = sum(1 for s in self.subscribers.values() if s.status == SubscriptionStatus.INACTIVE)
        suspended = sum(1 for s in self.subscribers.values() if s.status == SubscriptionStatus.SUSPENDED)
        unsubscribed = sum(1 for s in self.subscribers.values() if s.status == SubscriptionStatus.UNSUBSCRIBED)
        
        return {
            "total_subscribers": total,
            "active_subscribers": active,
            "inactive_subscribers": inactive,
            "suspended_subscribers": suspended,
            "unsubscribed_subscribers": unsubscribed,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
