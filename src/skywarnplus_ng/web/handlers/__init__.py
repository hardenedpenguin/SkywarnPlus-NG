"""HTTP handler mixins composed into ``WebDashboard``."""

from .api_alerts import AlertsApiMixin
from .api_config import ConfigApiMixin
from .api_tts_voices import TtsVoicesApiMixin
from .api_database import DatabaseApiMixin
from .api_health_logs import HealthLogsApiMixin
from .api_notifications import NotificationsApiMixin
from .api_status import StatusApiMixin
from .api_updates_metrics import UpdatesMetricsApiMixin
from .auth_handlers import AuthHandlersMixin
from .page_handlers import PageHandlersMixin
from .websocket_handlers import WebsocketHandlersMixin

__all__ = [
    "AlertsApiMixin",
    "AuthHandlersMixin",
    "ConfigApiMixin",
    "TtsVoicesApiMixin",
    "DatabaseApiMixin",
    "HealthLogsApiMixin",
    "NotificationsApiMixin",
    "PageHandlersMixin",
    "StatusApiMixin",
    "UpdatesMetricsApiMixin",
    "WebsocketHandlersMixin",
]
