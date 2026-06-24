"""
Professional web dashboard server for SkywarnPlus-NG.
"""

import asyncio
import hashlib
import logging
import secrets
from urllib.parse import quote

import bcrypt as bcrypt_lib
import aiohttp
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from aiohttp import web
from aiohttp.web import Request, Response
from aiohttp_session import setup, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from aiohttp_cors import setup as cors_setup, ResourceOptions
from jinja2 import Environment, FileSystemLoader

from .. import __version__ as _PACKAGE_VERSION
from ..core.config import AppConfig
from ..core.models import AlertCertainty, AlertSeverity, AlertUrgency
from ..notifications.subscriber import (
    NotificationMethod,
    SubscriberManager,
    SubscriptionPreferences,
)
from ..notifications.templates import TemplateEngine
from ..utils.rate_limit import SlidingWindowRateLimiter
from ..utils.url_security import validate_public_https_webhook_url

from .handlers.api_alerts import AlertsApiMixin
from .handlers.api_tts_voices import TtsVoicesApiMixin
from .handlers.api_config import ConfigApiMixin
from .handlers.api_database import DatabaseApiMixin
from .handlers.api_health_logs import HealthLogsApiMixin
from .handlers.api_notifications import NotificationsApiMixin
from .handlers.api_status import StatusApiMixin
from .handlers.api_updates_metrics import UpdatesMetricsApiMixin
from .handlers.auth_handlers import AuthHandlersMixin
from .handlers.page_handlers import PageHandlersMixin
from .auth_security import (
    external_path_for_request,
    path_requires_auth,
    request_is_https,
)
from .handlers.websocket_handlers import WebsocketHandlersMixin
from .routes import register_dashboard_routes

if TYPE_CHECKING:
    from ..core.application import SkywarnPlusApplication

logger = logging.getLogger(__name__)


class WebDashboardError(Exception):
    """Web dashboard error."""

    pass


class WebDashboard(
    WebsocketHandlersMixin,
    AuthHandlersMixin,
    NotificationsApiMixin,
    ConfigApiMixin,
    TtsVoicesApiMixin,
    DatabaseApiMixin,
    UpdatesMetricsApiMixin,
    HealthLogsApiMixin,
    AlertsApiMixin,
    StatusApiMixin,
    PageHandlersMixin,
):
    """Professional web dashboard for SkywarnPlus-NG."""

    PREFERENCE_FIELDS = [
        "counties",
        "states",
        "custom_areas",
        "enabled_severities",
        "enabled_urgencies",
        "enabled_certainties",
        "enabled_events",
        "blocked_events",
        "enabled_methods",
        "immediate_delivery",
        "batch_delivery",
        "batch_interval_minutes",
        "quiet_hours_start",
        "quiet_hours_end",
        "timezone",
        "max_notifications_per_hour",
        "max_notifications_per_day",
    ]

    DEFAULT_SEVERITIES = {
        AlertSeverity.MINOR,
        AlertSeverity.MODERATE,
        AlertSeverity.SEVERE,
        AlertSeverity.EXTREME,
    }

    DEFAULT_URGENCIES = {
        AlertUrgency.FUTURE,
        AlertUrgency.EXPECTED,
        AlertUrgency.IMMEDIATE,
    }

    DEFAULT_CERTAINTIES = {
        AlertCertainty.POSSIBLE,
        AlertCertainty.LIKELY,
        AlertCertainty.OBSERVED,
    }

    DEFAULT_METHODS = {NotificationMethod.EMAIL}

    def __init__(self, app_instance: "SkywarnPlusApplication", config: AppConfig):
        """
        Initialize web dashboard.

        Args:
            app_instance: SkywarnPlus application instance
            config: Application configuration
        """
        self.app = app_instance
        self.config = config
        self.web_app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.websocket_clients: set = set()
        self.template_env: Optional[Environment] = None
        # Rate limits (per client IP): login attempts, authenticated config saves
        self._login_rate_limit = SlidingWindowRateLimiter(max_calls=20, window_seconds=900)
        self._config_rate_limit = SlidingWindowRateLimiter(max_calls=120, window_seconds=3600)
        self._update_check_lock = asyncio.Lock()
        self._update_check_task: Optional[asyncio.Task] = None
        self._github_http_session: Optional[aiohttp.ClientSession] = None

        # Setup template environment
        self._setup_templates()

    @staticmethod
    def _client_ip(request: Request) -> str:
        """Best-effort client IP (first X-Forwarded-For hop if present)."""
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()[:200] or "unknown"
        return (request.remote or "unknown")[:200]

    @staticmethod
    def _subscriber_webhook_validation_error(url) -> Optional[str]:
        """Return error message if webhook URL is non-empty but not allowed; else None."""
        if url is None:
            return None
        s = str(url).strip()
        if not s:
            return None
        ok, msg = validate_public_https_webhook_url(s)
        return None if ok else msg

    @staticmethod
    def _subscriber_phone_validation_error(
        phone, enabled_methods: Optional[list] = None
    ) -> Optional[str]:
        """Return error message if SMS is enabled but phone is missing or invalid."""
        from ..notifications.phone import normalize_phone_number, validate_phone_number

        methods = {str(m).lower() for m in (enabled_methods or [])}
        if "sms" not in methods:
            return None
        if phone is None or not str(phone).strip():
            return "Phone number is required when SMS is enabled (E.164, e.g. +15551234567)"
        ok, msg = validate_phone_number(phone)
        if not ok:
            return msg
        if not normalize_phone_number(phone):
            return "Phone must be a valid E.164 number (e.g. +15551234567)"
        return None

    def _setup_templates(self) -> None:
        """Setup Jinja2 template environment."""
        template_dir = Path(__file__).parent / "templates"
        self.template_env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
        # Add base_path as a global variable available to all templates
        # Ensure base_path is always a string (empty string if None)
        # Normalize: ensure it starts with / and doesn't end with /
        base_path = self.config.monitoring.http_server.base_path or ""
        if base_path:
            base_path = base_path.strip()
            if not base_path.startswith("/"):
                base_path = "/" + base_path
            if base_path.endswith("/"):
                base_path = base_path.rstrip("/")
        self.template_env.globals["base_path"] = base_path
        self.template_env.globals["app_version"] = _PACKAGE_VERSION

        # Generate secret key if not provided
        if not self.config.monitoring.http_server.auth.secret_key:
            self.config.monitoring.http_server.auth.secret_key = secrets.token_hex(32)

    def _get_data_dir(self) -> Path:
        """Resolve and ensure the data directory exists."""
        data_dir = Path(self.config.data_dir or "/var/lib/skywarnplus-ng/data")
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def _get_subscriber_manager(self) -> SubscriberManager:
        """Create a subscriber manager scoped to the data directory."""
        data_dir = self._get_data_dir()
        return SubscriberManager(data_dir / "subscribers.json")

    def _get_template_engine(self) -> TemplateEngine:
        """Create a template engine scoped to the data directory."""
        data_dir = self._get_data_dir()
        return TemplateEngine(storage_path=data_dir / "templates.json")

    @staticmethod
    def _normalize_list(value) -> List[str]:
        """Normalize incoming list-like data into a list of strings."""
        if value is None:
            return []

        if isinstance(value, (list, tuple, set)):
            iterable = value
        elif isinstance(value, str):
            text = value.replace(";", ",").replace("\n", ",")
            iterable = [item.strip() for item in text.split(",")]
        else:
            iterable = [value]

        result = []
        for item in iterable:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                result.append(text)
        return result

    @staticmethod
    def _normalize_bool(value, default: bool = False) -> bool:
        """Normalize truthy inputs."""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _to_int(value, default: int) -> int:
        """Convert value to int with default fallback."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _parse_enum_list(self, values, enum_cls, default_values) -> Set:
        """Convert incoming iterable into a set of enum members."""
        if values is None:
            return set(default_values)

        if not isinstance(values, (list, tuple, set)):
            values = [values]

        parsed = set()
        for item in values:
            if isinstance(item, enum_cls):
                parsed.add(item)
            else:
                try:
                    parsed.add(enum_cls(item))
                except ValueError:
                    logger.warning(f"Ignoring invalid {enum_cls.__name__} value: {item}")

        return parsed or set(default_values)

    def _build_preferences_state(self, prefs: Optional[SubscriptionPreferences]) -> Dict[str, Any]:
        """Create a mutable dict of the current preference state."""
        if not prefs:
            return {
                "counties": [],
                "states": [],
                "custom_areas": [],
                "enabled_severities": list(self.DEFAULT_SEVERITIES),
                "enabled_urgencies": list(self.DEFAULT_URGENCIES),
                "enabled_certainties": list(self.DEFAULT_CERTAINTIES),
                "enabled_events": [],
                "blocked_events": [],
                "enabled_methods": list(self.DEFAULT_METHODS),
                "immediate_delivery": True,
                "batch_delivery": False,
                "batch_interval_minutes": 15,
                "quiet_hours_start": None,
                "quiet_hours_end": None,
                "timezone": "UTC",
                "max_notifications_per_hour": 10,
                "max_notifications_per_day": 50,
            }

        return {
            "counties": list(prefs.counties or []),
            "states": list(prefs.states or []),
            "custom_areas": list(prefs.custom_areas or []),
            "enabled_severities": list(prefs.enabled_severities or []),
            "enabled_urgencies": list(prefs.enabled_urgencies or []),
            "enabled_certainties": list(prefs.enabled_certainties or []),
            "enabled_events": list(prefs.enabled_events or []),
            "blocked_events": list(prefs.blocked_events or []),
            "enabled_methods": list(prefs.enabled_methods or []),
            "immediate_delivery": prefs.immediate_delivery,
            "batch_delivery": prefs.batch_delivery,
            "batch_interval_minutes": prefs.batch_interval_minutes,
            "quiet_hours_start": prefs.quiet_hours_start,
            "quiet_hours_end": prefs.quiet_hours_end,
            "timezone": prefs.timezone,
            "max_notifications_per_hour": prefs.max_notifications_per_hour,
            "max_notifications_per_day": prefs.max_notifications_per_day,
        }

    def _parse_subscription_preferences(
        self, payload: Dict[str, Any], existing: Optional[SubscriptionPreferences] = None
    ) -> SubscriptionPreferences:
        """Parse incoming payload into a SubscriptionPreferences object."""
        prefs_payload = payload.get("preferences")
        if prefs_payload is None:
            prefs_payload = {key: payload[key] for key in self.PREFERENCE_FIELDS if key in payload}

        state = self._build_preferences_state(existing)
        for key, value in prefs_payload.items():
            if key in self.PREFERENCE_FIELDS:
                state[key] = value

        return SubscriptionPreferences(
            counties=self._normalize_list(state.get("counties")),
            states=self._normalize_list(state.get("states")),
            custom_areas=self._normalize_list(state.get("custom_areas")),
            enabled_severities=self._parse_enum_list(
                state.get("enabled_severities"), AlertSeverity, self.DEFAULT_SEVERITIES
            ),
            enabled_urgencies=self._parse_enum_list(
                state.get("enabled_urgencies"), AlertUrgency, self.DEFAULT_URGENCIES
            ),
            enabled_certainties=self._parse_enum_list(
                state.get("enabled_certainties"), AlertCertainty, self.DEFAULT_CERTAINTIES
            ),
            enabled_events=set(self._normalize_list(state.get("enabled_events"))),
            blocked_events=set(self._normalize_list(state.get("blocked_events"))),
            enabled_methods=self._parse_enum_list(
                state.get("enabled_methods"), NotificationMethod, self.DEFAULT_METHODS
            ),
            immediate_delivery=self._normalize_bool(state.get("immediate_delivery"), True),
            batch_delivery=self._normalize_bool(state.get("batch_delivery"), False),
            batch_interval_minutes=self._to_int(state.get("batch_interval_minutes"), 15),
            quiet_hours_start=state.get("quiet_hours_start") or None,
            quiet_hours_end=state.get("quiet_hours_end") or None,
            timezone=state.get("timezone") or "UTC",
            max_notifications_per_hour=self._to_int(state.get("max_notifications_per_hour"), 10),
            max_notifications_per_day=self._to_int(state.get("max_notifications_per_day"), 50),
        )

    def _hash_password(self, password: str) -> str:
        """Hash a password using SHA-256 then bcrypt (avoids bcrypt 72-byte limit). Uses bcrypt package directly to avoid passlib init issues with bcrypt 5.x."""
        digest = hashlib.sha256(password.encode()).hexdigest()
        hashed = bcrypt_lib.hashpw(digest.encode("utf-8"), bcrypt_lib.gensalt())
        return hashed.decode("utf-8")

    def _verify_password(self, password: str, stored: str) -> bool:
        """Verify a password against stored value (bcrypt hash or legacy plaintext)."""
        if stored is None:
            return False
        password = password.strip() if isinstance(password, str) else ""
        stored = stored.strip() if isinstance(stored, str) else ""
        if not password or not stored:
            return False
        if stored.startswith("$2") and len(stored) > 20:
            # Accept $2y$ (PHP/supermon-ng) by normalizing to $2b$ for Python bcrypt
            if stored.startswith("$2y$"):
                stored = "$2b$" + stored[4:]
            digest = hashlib.sha256(password.encode()).hexdigest()
            try:
                if bcrypt_lib.checkpw(digest.encode("utf-8"), stored.encode("utf-8")):
                    return True
            except Exception:
                pass
            try:
                return bcrypt_lib.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
            except Exception:
                return False
        # Legacy plaintext in YAML: verified above; caller should migrate to bcrypt on login.
        if password == stored:
            logger.warning(
                "Dashboard auth password is stored in plaintext; it will be hashed on next login"
            )
            return True
        return False

    def _uses_default_dashboard_password(self) -> bool:
        from .auth_security import uses_default_dashboard_password

        stored = self.config.monitoring.http_server.auth.password
        return uses_default_dashboard_password(self._verify_password, stored)

    def _persist_dashboard_auth_password(self, password_hash: str) -> None:
        """Write bcrypt hash to in-memory config and on-disk YAML."""
        from ruamel.yaml import YAML
        from ruamel.yaml.scalarstring import DoubleQuotedScalarString

        from .config_merge import resolve_config_path

        self.config.monitoring.http_server.auth.password = password_hash
        if self.app:
            self.app.config = self.config

        config_path = resolve_config_path(self.config)
        yaml = YAML()
        yaml.preserve_quotes = True
        with open(config_path, encoding="utf-8") as f:
            data = yaml.load(f) or {}
        mon = data.setdefault("monitoring", {}).setdefault("http_server", {}).setdefault("auth", {})
        mon["password"] = DoubleQuotedScalarString(password_hash)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        logger.info("Persisted hashed dashboard auth password to %s", config_path)

    def _should_use_secure_cookies(self, request: Request) -> bool:
        auth = self.config.monitoring.http_server.auth
        if auth.secure_cookies:
            return True
        if auth.cookie_secure_auto and request_is_https(request):
            return True
        return False

    def _is_bcrypt_hash(self, s: str) -> bool:
        """Return True if s looks like a bcrypt hash (never write plaintext)."""
        return isinstance(s, str) and len(s) > 20 and s.startswith("$2")

    def _ensure_auth_password_hashed_in_dict(self, d: dict) -> None:
        """Replace dashboard auth password with hash if it looks like plaintext. Mutates d."""
        try:
            mon = d.get("monitoring")
            if not isinstance(mon, dict):
                return
            http = mon.get("http_server")
            if not isinstance(http, dict):
                return
            auth = http.get("auth")
            if not isinstance(auth, dict):
                return
            pwd = auth.get("password")
            if not isinstance(pwd, str) or not pwd:
                return
            if self._is_bcrypt_hash(pwd):
                return
            auth["password"] = self._hash_password(pwd)
            logger.info("Hashed dashboard auth password before persist")
        except Exception as e:
            logger.warning("Could not hash auth password in dict: %s", e)

    async def _is_authenticated(self, request: Request) -> bool:
        """Check if the user is authenticated."""
        if not self.config.monitoring.http_server.auth.enabled:
            return True

        session = await get_session(request)
        user_id = session.get("user_id")
        login_time = session.get("login_time")

        if not user_id or not login_time:
            return False

        # Check session timeout
        timeout_hours = self.config.monitoring.http_server.auth.session_timeout_hours
        if datetime.now(timezone.utc) - datetime.fromisoformat(login_time) > timedelta(
            hours=timeout_hours
        ):
            # Session expired
            session.clear()
            return False

        return True

    async def _require_auth(self, request: Request) -> Optional[Response]:
        """Middleware to require authentication."""
        if not await self._is_authenticated(request):
            # For API requests, return JSON error
            if request.path.startswith("/api/"):
                return web.json_response({"error": "Authentication required"}, status=401)
            # For configuration page requests, redirect to login with ?next= for post-login redirect
            else:
                base_path = (
                    request.app.get("base_path", "")
                    or self.config.monitoring.http_server.base_path
                    or ""
                )
                if base_path and not base_path.startswith("/"):
                    base_path = "/" + base_path
                mount_prefix = request.app.get("mount_prefix", "")
                url_prefix = mount_prefix or base_path
                next_path = external_path_for_request(request.path or "/", url_prefix)
                loc = f"{url_prefix}/login?next={quote(next_path, safe='')}&reason=required"
                return web.Response(status=302, headers={"Location": loc})
        return None

    def require_auth(self, handler):
        """Decorator to require authentication for handlers."""

        async def wrapper(request: Request) -> Response:
            auth_response = await self._require_auth(request)
            if auth_response:
                return auth_response
            return await handler(request)

        return wrapper

    def _configure_dashboard_app(
        self, app: web.Application, base_path: str, mount_prefix: str
    ) -> None:
        """Attach session, auth middleware, and routes to a dashboard application."""
        app["base_path"] = base_path
        app["mount_prefix"] = mount_prefix

        secret_key = bytes.fromhex(self.config.monitoring.http_server.auth.secret_key)
        setup(app, EncryptedCookieStorage(secret_key))

        app.middlewares.append(self._auth_middleware)
        app.middlewares.append(self._secure_cookie_middleware)
        register_dashboard_routes(app, self)

    def create_app(self) -> web.Application:
        """Create the web application."""
        base_path = self.config.monitoring.http_server.base_path or ""

        # Normalize base_path: ensure it starts with / and doesn't end with /
        if base_path:
            base_path = base_path.strip()
            if not base_path.startswith("/"):
                base_path = "/" + base_path
            if base_path.endswith("/"):
                base_path = base_path.rstrip("/")

        main_app = web.Application()
        main_app["base_path"] = base_path

        # credentials cannot be used with allow_origin="*"; same-origin dashboard uses cookies without CORS.
        cors_setup(
            main_app,
            defaults={
                "*": ResourceOptions(
                    allow_credentials=False,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods="*",
                )
            },
        )

        # Routes at / for reverse proxies that strip base_path before forwarding.
        self._configure_dashboard_app(main_app, base_path, mount_prefix="")

        if base_path:
            # Routes at /skywarnplus-ng/... for proxies that keep the prefix (e.g. NPM).
            prefixed_app = web.Application()
            self._configure_dashboard_app(prefixed_app, base_path, mount_prefix=base_path)
            main_app.add_subapp(base_path, prefixed_app)
            logger.info(
                f"Application configured with base_path: {base_path} "
                "(mounted at root and under prefix)"
            )
        else:
            logger.info("Application configured without base_path")

        return main_app

    def _path_requires_auth(self, request: Request) -> bool:
        """Return True when the request must be authenticated."""
        auth = self.config.monitoring.http_server.auth
        return path_requires_auth(
            request.path or "",
            request.method,
            auth_enabled=auth.enabled,
            public_status_api=auth.public_status_api,
            base_path=self.config.monitoring.http_server.base_path or "",
        )

    @web.middleware
    async def _secure_cookie_middleware(self, request: Request, handler):
        """Add Secure / SameSite=Lax to session cookies when HTTPS is in use."""
        response = await handler(request)
        if not self._should_use_secure_cookies(request):
            return response
        raw = response.headers.getall("Set-Cookie", [])
        if not raw:
            return response
        response.headers.popall("Set-Cookie", None)
        for cookie in raw:
            if "Secure" not in cookie:
                cookie = f"{cookie}; Secure"
            if "SameSite" not in cookie:
                cookie = f"{cookie}; SameSite=Lax"
            response.headers.add("Set-Cookie", cookie)
        return response

    @web.middleware
    async def _auth_middleware(self, request: Request, handler):
        """Authentication middleware."""
        if not self._path_requires_auth(request):
            return await handler(request)

        auth_response = await self._require_auth(request)
        if auth_response:
            return auth_response

        return await handler(request)

    async def start(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Start the web dashboard server."""
        try:
            self.web_app = self.create_app()
            # Long keep-alive for HTTP; behind nginx use timeouts >= proxy (see nginx-proxy-manager-guide.md)
            self.runner = web.AppRunner(self.web_app, keepalive_timeout=3600)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, host, port)
            await self.site.start()

            # Normalize base_path for logging (same as in create_app)
            base_path = self.config.monitoring.http_server.base_path or ""
            if base_path:
                base_path = base_path.strip()
                if not base_path.startswith("/"):
                    base_path = "/" + base_path
                if base_path.endswith("/"):
                    base_path = base_path.rstrip("/")

            base_url = f"http://{host}:{port}{base_path}"

            logger.info(f"Web dashboard started on {base_url}")
            logger.info("Available pages:")
            logger.info(f"  {base_url}/ - Dashboard")
            logger.info(f"  {base_url}/alerts - Active Alerts")
            logger.info(f"  {base_url}/alerts/history - Alert History")
            logger.info(f"  {base_url}/configuration - Configuration")
            logger.info(f"  {base_url}/health - System Health")
            logger.info(f"  {base_url}/logs - Application Logs")
            logger.info(f"  {base_url}/database - Database")
            logger.info(f"  {base_url}/metrics - Metrics")

            self._github_http_session = aiohttp.ClientSession(
                headers={"User-Agent": "SkywarnPlus-NG-UpdateCheck/1.0"}
            )
            self._update_check_task = asyncio.create_task(self._update_check_background_loop())

        except Exception as e:
            logger.error(f"Failed to start web dashboard: {e}")
            raise WebDashboardError(f"Failed to start web dashboard: {e}") from e

    async def stop(self) -> None:
        """Stop the web dashboard server."""
        if self._update_check_task:
            self._update_check_task.cancel()
            try:
                await self._update_check_task
            except asyncio.CancelledError:
                pass
            self._update_check_task = None
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            logger.info("Web dashboard stopped")
        except Exception as e:
            logger.error(f"Error stopping web dashboard: {e}")
        finally:
            if self._github_http_session and not self._github_http_session.closed:
                await self._github_http_session.close()
            self._github_http_session = None
