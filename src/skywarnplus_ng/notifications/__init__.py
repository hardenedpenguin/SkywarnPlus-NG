"""
Real-time notifications and communication system for SkywarnPlus-NG.
"""

from .delivery import DeliveryQueue, DeliveryStatus, RetryPolicy
from .email import EmailConfig, EmailNotifier, EmailProvider
from .factory import build_notification_manager
from .manager import NotificationError, NotificationManager
from .phone import normalize_phone_number, validate_phone_number
from .push import PushConfig, PushNotifier
from .sms import SmsConfig, SmsNotifier
from .subscriber import Subscriber, SubscriberManager, SubscriptionPreferences
from .templates import NotificationTemplate, TemplateEngine
from .webhook import WebhookConfig, WebhookNotifier

__all__ = [
    "DeliveryQueue",
    "DeliveryStatus",
    "EmailConfig",
    "EmailNotifier",
    "EmailProvider",
    "NotificationError",
    "NotificationManager",
    "NotificationTemplate",
    "PushConfig",
    "PushNotifier",
    "RetryPolicy",
    "SmsConfig",
    "SmsNotifier",
    "Subscriber",
    "SubscriberManager",
    "SubscriptionPreferences",
    "TemplateEngine",
    "WebhookConfig",
    "WebhookNotifier",
    "build_notification_manager",
    "normalize_phone_number",
    "validate_phone_number",
]
