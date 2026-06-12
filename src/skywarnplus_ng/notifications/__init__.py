"""
Real-time notifications and communication system for SkywarnPlus-NG.
"""

from .manager import NotificationManager, NotificationError
from .factory import build_notification_manager
from .email import EmailNotifier, EmailConfig, EmailProvider
from .webhook import WebhookNotifier, WebhookConfig
from .push import PushNotifier, PushConfig
from .subscriber import SubscriberManager, Subscriber, SubscriptionPreferences
from .templates import NotificationTemplate, TemplateEngine
from .delivery import DeliveryQueue, DeliveryStatus, RetryPolicy

__all__ = [
    "NotificationManager",
    "NotificationError",
    "build_notification_manager",
    "EmailNotifier",
    "EmailConfig",
    "EmailProvider",
    "WebhookNotifier",
    "WebhookConfig",
    "PushNotifier",
    "PushConfig",
    "SubscriberManager",
    "Subscriber",
    "SubscriptionPreferences",
    "NotificationTemplate",
    "TemplateEngine",
    "DeliveryQueue",
    "DeliveryStatus",
    "RetryPolicy",
]
