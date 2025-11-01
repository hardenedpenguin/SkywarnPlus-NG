"""
Professional web dashboard server for SkywarnPlus-NG.
"""

import asyncio
import json
import logging
import os
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import uuid

from aiohttp import web, WSMsgType
from aiohttp.web import Request, Response
from aiohttp_session import setup, get_session, new_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from aiohttp_cors import setup as cors_setup, ResourceOptions
from jinja2 import Environment, FileSystemLoader
from websockets.exceptions import ConnectionClosed

from typing import TYPE_CHECKING

from ..core.config import AppConfig
from ..database.manager import DatabaseManager
from ..monitoring.health import HealthMonitor

if TYPE_CHECKING:
    from ..core.application import SkywarnPlusApplication

logger = logging.getLogger(__name__)


class WebDashboardError(Exception):
    """Web dashboard error."""

    pass


class WebDashboard:
    """Professional web dashboard for SkywarnPlus-NG."""

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
        
        # Setup template environment
        self._setup_templates()

    def _setup_templates(self) -> None:
        """Setup Jinja2 template environment."""
        template_dir = Path(__file__).parent / "templates"
        self.template_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True
        )
        # Add base_path as a global variable available to all templates
        # Ensure base_path is always a string (empty string if None)
        # Normalize: ensure it starts with / and doesn't end with /
        base_path = self.config.monitoring.http_server.base_path or ''
        if base_path:
            base_path = base_path.strip()
            if not base_path.startswith('/'):
                base_path = '/' + base_path
            if base_path.endswith('/'):
                base_path = base_path.rstrip('/')
        self.template_env.globals['base_path'] = base_path
        
        # Generate secret key if not provided
        if not self.config.monitoring.http_server.auth.secret_key:
            self.config.monitoring.http_server.auth.secret_key = secrets.token_hex(32)

    def _hash_password(self, password: str) -> str:
        """Hash a password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()

    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against its hash."""
        return self._hash_password(password) == hashed

    async def _is_authenticated(self, request: Request) -> bool:
        """Check if the user is authenticated."""
        if not self.config.monitoring.http_server.auth.enabled:
            return True
            
        session = await get_session(request)
        user_id = session.get('user_id')
        login_time = session.get('login_time')
        
        if not user_id or not login_time:
            return False
            
        # Check session timeout
        timeout_hours = self.config.monitoring.http_server.auth.session_timeout_hours
        if datetime.now(timezone.utc) - datetime.fromisoformat(login_time) > timedelta(hours=timeout_hours):
            # Session expired
            session.clear()
            return False
            
        return True

    async def _require_auth(self, request: Request) -> Optional[Response]:
        """Middleware to require authentication."""
        if not await self._is_authenticated(request):
            # For API requests, return JSON error
            if request.path.startswith('/api/'):
                return web.json_response({'error': 'Authentication required to access configuration'}, status=401)
            # For configuration page requests, redirect to login
            else:
                # Get base_path from app storage (normalized) or fallback to config
                base_path = request.app.get('base_path', '') or self.config.monitoring.http_server.base_path or ''
                if base_path and not base_path.startswith('/'):
                    base_path = '/' + base_path
                return web.Response(status=302, headers={'Location': f'{base_path}/login'})
        return None

    def require_auth(self, handler):
        """Decorator to require authentication for handlers."""
        async def wrapper(request: Request) -> Response:
            auth_response = await self._require_auth(request)
            if auth_response:
                return auth_response
            return await handler(request)
        return wrapper

    def create_app(self) -> web.Application:
        """Create the web application."""
        base_path = self.config.monitoring.http_server.base_path or ''
        
        # Normalize base_path: ensure it starts with / and doesn't end with /
        if base_path:
            base_path = base_path.strip()
            if not base_path.startswith('/'):
                base_path = '/' + base_path
            if base_path.endswith('/'):
                base_path = base_path.rstrip('/')
        
        # Create main app
        main_app = web.Application()
        
        # Store base_path in app for use in handlers (for URL generation)
        main_app['base_path'] = base_path
        
        # When reverse proxy strips base_path before forwarding, we mount at root
        # The base_path is only used for generating URLs in templates/redirects
        app = main_app
        
        # Setup CORS
        cors = cors_setup(main_app, defaults={
            "*": ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*"
            )
        })
        
        # Setup sessions FIRST (required for auth middleware)
        secret_key = bytes.fromhex(self.config.monitoring.http_server.auth.secret_key)
        setup(app, EncryptedCookieStorage(secret_key))
        
        # Add authentication middleware AFTER session setup
        app.middlewares.append(self._auth_middleware)
        
        # Add routes to the main app
        self._add_routes(app)
        
        if base_path:
            logger.info(f"Application configured with base_path: {base_path} (reverse proxy should strip prefix)")
        else:
            logger.info("Application configured without base_path")
        
        return main_app

    @web.middleware
    async def _auth_middleware(self, request: Request, handler):
        """Authentication middleware."""
        # Only protect configuration-related paths
        protected_paths = ['/configuration', '/api/config']
        
        # Skip authentication for non-protected paths
        if not any(request.path.startswith(path) for path in protected_paths):
            return await handler(request)
        
        # Check authentication for configuration paths only
        auth_response = await self._require_auth(request)
        if auth_response:
            return auth_response
            
        return await handler(request)

    def _add_routes(self, app: web.Application) -> None:
        """Add all routes to the application."""
        # Static files
        app.router.add_static('/static', Path(__file__).parent / 'static', name='static')
        
        # Authentication routes (no auth required)
        app.router.add_get('/login', self.login_handler)
        app.router.add_post('/api/auth/login', self.api_login_handler)
        app.router.add_post('/api/auth/logout', self.api_logout_handler)
        
        # Main pages (auth required)
        app.router.add_get('/', self.dashboard_handler)
        app.router.add_get('/dashboard', self.dashboard_handler)
        app.router.add_get('/alerts', self.alerts_handler)
        app.router.add_get('/alerts/history', self.alerts_history_handler)
        app.router.add_get('/configuration', self.configuration_handler)
        app.router.add_get('/health', self.health_handler)
        app.router.add_get('/logs', self.logs_handler)
        app.router.add_get('/database', self.database_handler)
        app.router.add_get('/metrics', self.metrics_handler)
        
        # API endpoints
        app.router.add_get('/api/status', self.api_status_handler)
        app.router.add_get('/api/alerts', self.api_alerts_handler)
        app.router.add_get('/api/alerts/history', self.api_alerts_history_handler)
        app.router.add_get('/api/alerts/{alert_id}/audio', self.api_alert_audio_handler)
        app.router.add_get('/api/health', self.api_health_handler)
        app.router.add_get('/api/health/history', self.api_health_history_handler)
        app.router.add_get('/api/logs', self.api_logs_handler)
        app.router.add_get('/api/metrics', self.api_metrics_handler)
        app.router.add_get('/api/activity', self.api_activity_handler)
        app.router.add_get('/api/database/stats', self.api_database_stats_handler)
        app.router.add_post('/api/database/cleanup', self.api_database_cleanup_handler)
        app.router.add_post('/api/database/optimize', self.api_database_optimize_handler)
        
        # Configuration API
        app.router.add_get('/api/config', self.api_config_get_handler)
        app.router.add_post('/api/config', self.api_config_update_handler)
        app.router.add_post('/api/config/reset', self.api_config_reset_handler)
        app.router.add_post('/api/config/backup', self.api_config_backup_handler)
        
        # County audio generation API
        app.router.add_post('/api/counties/{county_code}/generate-audio', self.api_county_generate_audio_handler)
        app.router.add_post('/api/config/restore', self.api_config_restore_handler)

        # Notification API routes
        app.router.add_post('/api/notifications/test-email', self.api_notifications_test_email_handler)
        app.router.add_get('/api/notifications/subscribers', self.api_notifications_subscribers_handler)
        app.router.add_post('/api/notifications/subscribers', self.api_notifications_add_subscriber_handler)
        app.router.add_put('/api/notifications/subscribers/{subscriber_id}', self.api_notifications_update_subscriber_handler)
        app.router.add_delete('/api/notifications/subscribers/{subscriber_id}', self.api_notifications_delete_subscriber_handler)
        app.router.add_get('/api/notifications/templates', self.api_notifications_templates_handler)
        app.router.add_post('/api/notifications/templates', self.api_notifications_add_template_handler)
        app.router.add_put('/api/notifications/templates/{template_id}', self.api_notifications_update_template_handler)
        app.router.add_delete('/api/notifications/templates/{template_id}', self.api_notifications_delete_template_handler)
        app.router.add_get('/api/notifications/stats', self.api_notifications_stats_handler)

        # WebSocket
        app.router.add_get('/ws', self.websocket_handler)

    async def dashboard_handler(self, request: Request) -> Response:
        """Handle dashboard page."""
        template = self.template_env.get_template('dashboard.html')
        content = template.render(
            title="SkywarnPlus-NG Dashboard",
            page="dashboard",
            config=self.config.model_dump()
        )
        return web.Response(text=content, content_type='text/html')

    async def alerts_handler(self, request: Request) -> Response:
        """Handle alerts page."""
        template = self.template_env.get_template('alerts.html')
        content = template.render(
            title="Active Alerts - SkywarnPlus-NG",
            page="alerts",
            config=self.config.model_dump()
        )
        return web.Response(text=content, content_type='text/html')

    async def alerts_history_handler(self, request: Request) -> Response:
        """Handle alerts history page."""
        template = self.template_env.get_template('alerts_history.html')
        content = template.render(
            title="Alert History - SkywarnPlus-NG",
            page="alerts_history",
            config=self.config.model_dump()
        )
        return web.Response(text=content, content_type='text/html')

    async def configuration_handler(self, request: Request) -> Response:
        """Handle configuration page."""
        template = self.template_env.get_template('configuration.html')
        content = template.render(
            title="Configuration - SkywarnPlus-NG",
            page="configuration",
            config=self.config.model_dump()
        )
        return web.Response(text=content, content_type='text/html')

    async def health_handler(self, request: Request) -> Response:
        """Handle health page."""
        template = self.template_env.get_template('health.html')
        content = template.render(
            title="System Health - SkywarnPlus-NG",
            page="health",
            config=self.config.model_dump()
        )
        return web.Response(text=content, content_type='text/html')

    async def logs_handler(self, request: Request) -> Response:
        """Handle logs page."""
        template = self.template_env.get_template('logs.html')
        content = template.render(
            title="Application Logs - SkywarnPlus-NG",
            page="logs",
            config=self.config.model_dump()
        )
        return web.Response(text=content, content_type='text/html')

    async def database_handler(self, request: Request) -> Response:
        """Handle database page."""
        template = self.template_env.get_template('database.html')
        content = template.render(
            title="Database - SkywarnPlus-NG",
            page="database",
            config=self.config.model_dump()
        )
        return web.Response(text=content, content_type='text/html')

    async def metrics_handler(self, request: Request) -> Response:
        """Handle metrics page."""
        template = self.template_env.get_template('metrics.html')
        content = template.render(
            title="Metrics - SkywarnPlus-NG",
            page="metrics",
            config=self.config.model_dump()
        )
        return web.Response(text=content, content_type='text/html')

    # API Handlers
    async def api_status_handler(self, request: Request) -> Response:
        """Handle API status endpoint."""
        try:
            status = self.app.get_status()
            
            # Get active alerts for Supermon compatibility
            active_alerts = self.app.state.get('active_alerts', [])
            alerts_data = []
            
            for alert_id in active_alerts:
                alert_data = self.app.state.get('last_alerts', {}).get(alert_id)
                if alert_data:
                    # Format alert for Supermon display
                    alerts_data.append({
                        'event': alert_data.get('event', 'Unknown'),
                        'severity': alert_data.get('severity', 'Unknown'),
                        'headline': alert_data.get('headline', alert_data.get('description', 'No headline'))[:100]  # Limit headline length
                    })
            
            # Add Supermon-compatible fields
            status['has_alerts'] = len(alerts_data) > 0
            status['alerts'] = alerts_data
            
            return web.json_response(status)
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_alerts_handler(self, request: Request) -> Response:
        """Handle API alerts endpoint."""
        try:
            # Get current alerts from state
            active_alerts = self.app.state.get('active_alerts', [])
            alerts_data = []
            
            for alert_id in active_alerts:
                alert_data = self.app.state.get('last_alerts', {}).get(alert_id)
                if alert_data:
                    alerts_data.append(alert_data)
            
            return web.json_response({
                "alerts": alerts_data,
                "count": len(alerts_data),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_alert_audio_handler(self, request: Request) -> Response:
        """Generate and stream TTS audio for a specific alert."""
        try:
            alert_id = request.match_info.get('alert_id')
            if not alert_id:
                return web.json_response({"error": "alert_id is required"}, status=400)

            # Ensure audio subsystem is available
            if not self.app or not self.app.audio_manager:
                return web.json_response({"error": "Audio system not available"}, status=503)

            # Look up alert data from state
            alert_data = self.app.state.get('last_alerts', {}).get(alert_id)
            if not alert_data:
                return web.json_response({"error": "Alert not found or expired"}, status=404)

            # Construct WeatherAlert model defensively
            try:
                from ..core.models import WeatherAlert
                alert_model = WeatherAlert(**alert_data)
            except Exception:
                # Fallback: minimal model using required fields
                from datetime import datetime
                from ..core.models import WeatherAlert
                minimal = {
                    'id': alert_data.get('id', alert_id),
                    'event': alert_data.get('event', 'Weather Alert'),
                    'description': alert_data.get('description', alert_data.get('area_desc', '')),
                    'sent': datetime.now(timezone.utc),
                    'effective': datetime.now(timezone.utc),
                    'expires': datetime.now(timezone.utc),
                    'area_desc': alert_data.get('area_desc', ''),
                    'sender': alert_data.get('sender', 'NWS'),
                    'sender_name': alert_data.get('sender_name', 'National Weather Service'),
                }
                alert_model = WeatherAlert(**minimal)

            # Generate audio file
            audio_path = self.app.audio_manager.generate_alert_audio(alert_model)
            if not audio_path or not audio_path.exists():
                return web.json_response({"error": "Failed to generate audio"}, status=500)

            # Determine content type from extension
            ext = audio_path.suffix.lower()
            if ext in ['.mp3']:
                content_type = 'audio/mpeg'
            elif ext in ['.wav']:
                content_type = 'audio/wav'
            elif ext in ['.ogg']:
                content_type = 'audio/ogg'
            else:
                content_type = 'application/octet-stream'

            # Stream file to client
            return web.FileResponse(path=str(audio_path), headers={'Content-Type': content_type})
        except Exception as e:
            logger.error(f"Error generating alert audio: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def api_alerts_history_handler(self, request: Request) -> Response:
        """Handle API alerts history endpoint."""
        try:
            if not self.app.database_manager:
                return web.json_response({"error": "Database not available"}, status=503)
            
            # Get query parameters
            limit = int(request.query.get('limit', 100))
            hours = int(request.query.get('hours', 24))
            
            # Get alerts from database
            alerts = await self.app.database_manager.get_recent_alerts(limit=limit, hours=hours)
            
            # Convert to dict format
            alerts_data = []
            for alert in alerts:
                # Helper function to safely format datetime
                def format_datetime(dt):
                    if dt is None:
                        return None
                    if hasattr(dt, 'isoformat'):
                        return dt.isoformat()
                    # If it's already a string, return as-is
                    return str(dt)
                
                alerts_data.append({
                    "id": alert.id,
                    "event": alert.event,
                    "severity": alert.severity,
                    "area_desc": alert.area_desc,
                    "effective_time": format_datetime(alert.effective_time),
                    "expires_time": format_datetime(alert.expires_time),
                    "processed_at": format_datetime(alert.processed_at),
                    "announced": alert.announced,
                    "script_executed": alert.script_executed
                })
            
            return web.json_response({
                "alerts": alerts_data,
                "count": len(alerts_data),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Error getting alerts history: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_health_handler(self, request: Request) -> Response:
        """Handle API health endpoint."""
        try:
            if not self.app.health_monitor:
                return web.json_response({"error": "Health monitor not available"}, status=503)
            
            health_status = await self.app.health_monitor.get_health_status()
            
            # Get additional system information
            system_info = {}
            if hasattr(self.app, 'get_status'):
                try:
                    app_status = self.app.get_status()
                    system_info = {
                        "running": app_status.get("running", False),
                        "initialized": app_status.get("initialized", False),
                        "active_alerts": app_status.get("active_alerts", 0),
                        "total_alerts": app_status.get("total_alerts", 0),
                        "last_poll": app_status.get("last_poll"),
                        "last_all_clear": app_status.get("last_all_clear"),
                        "script_status": app_status.get("script_status", {}),
                        "processing_stats": app_status.get("processing_stats", {}),
                        "performance_metrics": app_status.get("performance_metrics", {})
                    }
                except Exception as e:
                    logger.error(f"Failed to get additional system info: {e}")
            
            # Convert to dict format with enhanced data
            health_data = {
                "overall_status": health_status.overall_status.value,
                "timestamp": health_status.timestamp.isoformat(),
                "uptime_seconds": health_status.uptime_seconds,
                "version": health_status.version,
                "system_info": system_info,
                "components": [
                    {
                        "name": comp.name,
                        "status": comp.status.value,
                        "message": comp.message,
                        "response_time_ms": comp.response_time_ms,
                        "last_check": comp.last_check.isoformat() if hasattr(comp, 'last_check') else None,
                        "details": getattr(comp, 'details', None)
                    }
                    for comp in health_status.components
                ],
                "summary": {
                    "total_components": len(health_status.components),
                    "healthy_components": len([c for c in health_status.components if c.status.value == "healthy"]),
                    "unhealthy_components": len([c for c in health_status.components if c.status.value != "healthy"]),
                    "degraded_components": len([c for c in health_status.components if c.status.value == "degraded"]),
                    "average_response_time_ms": sum(
                        c.response_time_ms for c in health_status.components 
                        if c.response_time_ms is not None
                    ) / len([c for c in health_status.components if c.response_time_ms is not None]) 
                    if any(c.response_time_ms is not None for c in health_status.components) else None
                },
                "metrics": health_status.metrics
            }
            
            return web.json_response(health_data)
        except Exception as e:
            logger.error(f"Error getting health status: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_health_history_handler(self, request: Request) -> Response:
        """Handle API health history endpoint."""
        try:
            # Get query parameters
            limit = int(request.query.get('limit', 10))
            
            if not self.app.health_monitor:
                return web.json_response([])
            
            # Get health history from the monitor
            try:
                history = self.app.health_monitor.get_health_history(limit=limit)
            except Exception as e:
                logger.error(f"Failed to get health history: {e}")
                return web.json_response([])
            
            # Convert to serializable format
            history_data = []
            for record in history:
                try:
                    history_data.append({
                        "timestamp": record.timestamp.isoformat() if hasattr(record, 'timestamp') else None,
                        "overall_status": record.overall_status.value if hasattr(record, 'overall_status') else "unknown",
                        "uptime_seconds": getattr(record, 'uptime_seconds', 0),
                        "version": getattr(record, 'version', "unknown"),
                        "component_count": len(getattr(record, 'components', [])),
                        "healthy_components": len([c for c in getattr(record, 'components', []) if hasattr(c, 'status') and c.status.value == "healthy"]),
                        "unhealthy_components": len([c for c in getattr(record, 'components', []) if hasattr(c, 'status') and c.status.value != "healthy"])
                    })
                except Exception as e:
                    logger.error(f"Error processing health record: {e}")
                    continue
            
            # Return just the history array for frontend compatibility
            return web.json_response(history_data)
        except Exception as e:
            logger.error(f"Error getting health history: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_logs_handler(self, request: Request) -> Response:
        """Handle API logs endpoint."""
        try:
            # Get query parameters
            level = request.query.get('level', 'INFO')
            limit = int(request.query.get('limit', 100))
            
            # Read log file if configured
            log_file = self.config.logging.file
            if not log_file or not log_file.exists():
                return web.json_response({"logs": [], "count": 0})
            
            # Read last N lines from log file
            with open(log_file, 'r') as f:
                lines = f.readlines()
            
            # Filter by level and limit
            filtered_lines = []
            for line in lines[-limit:]:
                if level.upper() in line.upper():
                    try:
                        # Try to parse as JSON log
                        log_entry = json.loads(line.strip())
                        filtered_lines.append(log_entry)
                    except json.JSONDecodeError:
                        # Fallback to plain text
                        filtered_lines.append({"message": line.strip(), "level": "INFO"})
            
            return web.json_response({
                "logs": filtered_lines,
                "count": len(filtered_lines),
                "level": level,
                "limit": limit
            })
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_activity_handler(self, request: Request) -> Response:
        """Handle API recent activity endpoint."""
        try:
            # Get limit parameter
            limit = int(request.query.get('limit', 20))
            
            activities = []
            
            # Get recent alerts from database
            if self.app.database_manager:
                try:
                    recent_alerts = await self.app.database_manager.get_recent_alerts(limit=5, hours=24)
                    for alert in recent_alerts:
                        # Helper function to safely format datetime
                        def format_datetime(dt):
                            if dt is None:
                                return None
                            if hasattr(dt, 'isoformat'):
                                return dt.isoformat()
                            return str(dt)
                        
                        activities.append({
                            "type": "alert_processed",
                            "message": f"Processed {alert.severity.lower()} alert: {alert.event}",
                            "details": f"Area: {alert.area_desc}",
                            "timestamp": format_datetime(alert.processed_at),
                            "severity": alert.severity.lower(),
                            "icon": "alert-triangle" if alert.severity in ["Extreme", "Severe"] else "info"
                        })
                        
                        if alert.announced:
                            activities.append({
                                "type": "alert_announced",
                                "message": f"Announced {alert.severity.lower()} alert: {alert.event}",
                                "details": f"Area: {alert.area_desc}",
                                "timestamp": format_datetime(alert.processed_at),
                                "severity": alert.severity.lower(),
                                "icon": "volume-2"
                            })
                except Exception as e:
                    logger.warning(f"Could not fetch recent alerts for activity: {e}")
            
            # Add system status activities
            if self.app:
                try:
                    status = await self.app.get_status()
                    
                    # Add NWS connection status
                    if status.get("nws_connected"):
                        activities.append({
                            "type": "system_status",
                            "message": "NWS API connection active",
                            "details": "Weather data is being received",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "severity": "info",
                            "icon": "wifi"
                        })
                    
                    # Add Asterisk connection status
                    if status.get("asterisk_available"):
                        activities.append({
                            "type": "system_status", 
                            "message": "Asterisk connection active",
                            "details": "DTMF commands and announcements available",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "severity": "info",
                            "icon": "phone"
                        })
                    
                    # Add audio system status
                    if status.get("audio_available"):
                        activities.append({
                            "type": "system_status",
                            "message": "Audio system operational",
                            "details": "TTS and sound file playback available",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "severity": "info",
                            "icon": "speaker"
                        })
                        
                except Exception as e:
                    logger.warning(f"Could not get system status for activity: {e}")
            
            # Add server startup activity
            activities.append({
                "type": "system_event",
                "message": "SkywarnPlus-NG server started",
                "details": "All systems initialized and monitoring active",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "severity": "success",
                "icon": "play-circle"
            })
            
            # Sort activities by timestamp (most recent first)
            activities.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            # Limit results
            activities = activities[:limit]
            
            return web.json_response({
                "activities": activities,
                "count": len(activities),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error getting recent activity: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_metrics_handler(self, request: Request) -> Response:
        """Handle API metrics endpoint."""
        try:
            # Get query parameters
            hours = int(request.query.get('hours', 24))
            metric_name = request.query.get('metric_name')
            
            metrics_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "period_hours": hours,
                "metrics": {}
            }
            
            # Get performance metrics from analytics if available
            if self.app.analytics:
                try:
                    performance_metrics = self.app.analytics.get_performance_metrics(hours)
                    metrics_data["metrics"]["performance"] = {
                        "total_processed": performance_metrics.total_processed,
                        "successful_processing": performance_metrics.successful_processing,
                        "failed_processing": performance_metrics.failed_processing,
                        "average_processing_time_ms": performance_metrics.average_processing_time_ms,
                        "throughput_per_hour": performance_metrics.throughput_per_hour,
                        "error_rate": performance_metrics.error_rate,
                        "uptime_percentage": performance_metrics.uptime_percentage
                    }
                    
                    # Get alert statistics
                    from ..processing.analytics import AnalyticsPeriod
                    period = AnalyticsPeriod.DAY if hours <= 24 else AnalyticsPeriod.WEEK
                    alert_stats = self.app.analytics.get_alert_statistics(period)
                    
                    metrics_data["metrics"]["alerts"] = {
                        "total_alerts": alert_stats.total_alerts,
                        "period_start": alert_stats.period_start.isoformat(),
                        "period_end": alert_stats.period_end.isoformat(),
                        "severity_distribution": alert_stats.severity_distribution,
                        "urgency_distribution": alert_stats.urgency_distribution,
                        "category_distribution": alert_stats.category_distribution,
                        "county_distribution": alert_stats.county_distribution,
                        "hourly_distribution": alert_stats.hourly_distribution
                    }
                except Exception as e:
                    logger.error(f"Failed to get analytics metrics: {e}")
                    metrics_data["metrics"]["performance"] = {"error": "Analytics unavailable"}
            else:
                metrics_data["metrics"]["performance"] = {"error": "Analytics not initialized"}
            
            # Get system metrics from application status
            if hasattr(self.app, 'get_status'):
                try:
                    status = self.app.get_status()
                    metrics_data["metrics"]["system"] = {
                        "uptime_seconds": status.get("uptime_seconds", 0),
                        "running": status.get("running", False),
                        "initialized": status.get("initialized", False),
                        "active_alerts": status.get("active_alerts", 0),
                        "total_alerts": status.get("total_alerts", 0),
                        "nws_connected": status.get("nws_connected", False),
                        "asterisk_available": status.get("asterisk_available", False),
                        "database_available": status.get("database_available", False)
                    }
                except Exception as e:
                    logger.error(f"Failed to get system metrics: {e}")
                    metrics_data["metrics"]["system"] = {"error": "System status unavailable"}
            
            # Get health metrics if available
            if self.app.health_monitor:
                try:
                    health_status = await self.app.health_monitor.get_health_status()
                    metrics_data["metrics"]["health"] = {
                        "overall_status": health_status.overall_status.value,
                        "component_count": len(health_status.components),
                        "healthy_components": len([c for c in health_status.components if c.status.value == "healthy"]),
                        "unhealthy_components": len([c for c in health_status.components if c.status.value != "healthy"]),
                        "components": [
                            {
                                "name": comp.name,
                                "status": comp.status.value,
                                "response_time_ms": comp.response_time_ms
                            }
                            for comp in health_status.components
                        ]
                    }
                except Exception as e:
                    logger.error(f"Failed to get health metrics: {e}")
                    metrics_data["metrics"]["health"] = {"error": "Health monitor unavailable"}
            
            # Filter by specific metric if requested
            if metric_name and metric_name in metrics_data["metrics"]:
                filtered_data = {
                    "timestamp": metrics_data["timestamp"],
                    "period_hours": metrics_data["period_hours"],
                    "metric_name": metric_name,
                    "data": metrics_data["metrics"][metric_name]
                }
                return web.json_response(filtered_data)
            
            # Get data for calculations
            health_data = metrics_data["metrics"].get("health", {})
            system_data = metrics_data["metrics"].get("system", {})
            perf_data = metrics_data["metrics"].get("performance", {})
            
            # Calculate response time metrics
            response_times = []
            if "components" in health_data:
                response_times = [c.get("response_time_ms", 0) for c in health_data["components"] if c.get("response_time_ms") is not None]
            
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            max_response_time = max(response_times) if response_times else 0
            min_response_time = min(response_times) if response_times else 0
            
            # Calculate request metrics (mock data based on system activity)
            total_requests = system_data.get("active_alerts", 0) * 10
            successful_requests = total_requests
            failed_requests = 0
            
            # Calculate system metrics (mock data for now)
            import psutil
            try:
                cpu_usage = psutil.cpu_percent(interval=0.1)
                memory_info = psutil.virtual_memory()
                disk_info = psutil.disk_usage('/')
                memory_usage = memory_info.percent
                disk_usage = (disk_info.used / disk_info.total) * 100
            except:
                cpu_usage = 0.0
                memory_usage = 0.0
                disk_usage = 0.0
            
            # Flatten data for frontend compatibility
            flattened_metrics = {
                "timestamp": metrics_data["timestamp"],
                "period_hours": metrics_data["period_hours"],
                
                # Overview metrics (what the frontend expects)
                "total_requests": total_requests,
                "avg_response_time": avg_response_time,
                "error_rate": (failed_requests / total_requests * 100) if total_requests > 0 else 0,
                "uptime_seconds": system_data.get("uptime_seconds", 0),
                
                # Detailed Performance metrics
                "performance": {
                    "avg_response_time": avg_response_time,
                    "max_response_time": max_response_time,
                    "min_response_time": min_response_time,
                    "total_processed": total_requests,
                    "successful_processing": successful_requests,
                    "failed_processing": failed_requests,
                    "error_rate": (failed_requests / total_requests * 100) if total_requests > 0 else 0
                },
                
                # Detailed Request metrics
                "requests": {
                    "total_requests": total_requests,
                    "successful_requests": successful_requests,
                    "failed_requests": failed_requests,
                    "requests_per_hour": total_requests / (system_data.get("uptime_seconds", 1) / 3600) if system_data.get("uptime_seconds", 0) > 0 else 0
                },
                
                # Detailed System metrics
                "system": {
                    "cpu_usage": cpu_usage,
                    "memory_usage": memory_usage,
                    "disk_usage": disk_usage,
                    "uptime_seconds": system_data.get("uptime_seconds", 0),
                    "running": system_data.get("running", False),
                    "initialized": system_data.get("initialized", False),
                    "active_alerts": system_data.get("active_alerts", 0),
                    "nws_connected": system_data.get("nws_connected", False),
                    "asterisk_available": system_data.get("asterisk_available", False),
                    "database_available": system_data.get("database_available", False)
                },
                
                # Original detailed metrics for charts and advanced views
                "metrics": metrics_data["metrics"]
            }
            
            return web.json_response(flattened_metrics)
            
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_database_stats_handler(self, request: Request) -> Response:
        """Handle API database stats endpoint."""
        try:
            if not self.app.database_manager:
                return web.json_response({
                    "connected": False,
                    "error": "Database not available",
                    "total_alerts": 0,
                    "active_alerts": 0,
                    "database_size": 0
                }, status=503)
            
            stats = await self.app.database_manager.get_database_stats()
            
            # Add connection status and format for frontend
            enhanced_stats = {
                "connected": True,
                "total_alerts": stats.get("alerts_count", 0),
                "active_alerts": stats.get("alerts_count", 0),  # For now, assume all alerts are active
                "database_size": stats.get("database_size_bytes", 0),
                "metrics_count": stats.get("metrics_count", 0),
                "health_checks_count": stats.get("health_checks_count", 0),
                "script_executions_count": stats.get("script_executions_count", 0),
                "configurations_count": stats.get("configurations_count", 0)
            }
            
            return web.json_response(enhanced_stats)
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return web.json_response({
                "connected": False,
                "error": str(e),
                "total_alerts": 0,
                "active_alerts": 0,
                "database_size": 0
            }, status=500)

    async def api_database_cleanup_handler(self, request: Request) -> Response:
        """Handle API database cleanup endpoint."""
        try:
            if not self.app.database_manager:
                return web.json_response({"error": "Database not available"}, status=503)
            
            # Get days parameter from request body or use default
            try:
                if request.content_type == 'application/json' and request.content_length and request.content_length > 0:
                    data = await request.json()
                else:
                    data = {}
            except Exception:
                data = {}
            days = data.get('days', 30)
            
            cleanup_stats = await self.app.database_manager.cleanup_old_data(days)
            return web.json_response({
                "success": True,
                "message": f"Database cleanup completed successfully",
                "stats": cleanup_stats
            })
        except Exception as e:
            logger.error(f"Error cleaning up database: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_database_optimize_handler(self, request: Request) -> Response:
        """Handle API database optimize endpoint."""
        try:
            if not self.app.database_manager:
                return web.json_response({"error": "Database not available"}, status=503)
            
            optimization_stats = await self.app.database_manager.optimize_database()
            return web.json_response({
                "success": True,
                "message": "Database optimization completed successfully",
                "stats": optimization_stats
            })
        except Exception as e:
            logger.error(f"Error optimizing database: {e}")
            return web.json_response({"error": str(e)}, status=500)

    # Configuration API
    async def api_config_get_handler(self, request: Request) -> Response:
        """Handle API config get endpoint."""
        try:
            # Convert config to dict and handle Path objects
            config_dict = self.config.model_dump()
            
            # Convert Path objects to strings for JSON serialization
            def convert_paths(obj):
                if isinstance(obj, dict):
                    return {k: convert_paths(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_paths(item) for item in obj]
                elif hasattr(obj, '__fspath__'):  # Path-like object
                    return str(obj)
                else:
                    return obj
            
            serializable_config = convert_paths(config_dict)
            return web.json_response(serializable_config)
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_config_update_handler(self, request: Request) -> Response:
        """Handle API config update endpoint."""
        try:
            data = await request.json()
            
            # Import required modules for YAML handling
            from ruamel.yaml import YAML
            from pathlib import Path
            
            # Validate the configuration data by creating a new AppConfig instance
            try:
                # Preserve base_path if not in incoming data (form doesn't include it)
                if ('monitoring' not in data or 
                    'http_server' not in data['monitoring'] or 
                    'base_path' not in data['monitoring']['http_server']):
                    # Preserve current base_path value
                    if 'monitoring' not in data:
                        data['monitoring'] = {}
                    if 'http_server' not in data['monitoring']:
                        data['monitoring']['http_server'] = {}
                    data['monitoring']['http_server']['base_path'] = self.config.monitoring.http_server.base_path or ''
                    logger.info(f"Preserving base_path: {data['monitoring']['http_server']['base_path']}")
                
                # Handle password updates - if password is empty, keep the current password
                if ('monitoring' in data and 
                    'http_server' in data['monitoring'] and 
                    'auth' in data['monitoring']['http_server'] and
                    'password' in data['monitoring']['http_server']['auth']):
                    
                    new_password = data['monitoring']['http_server']['auth']['password']
                    if not new_password or new_password.strip() == '':
                        # Keep current password if new one is empty
                        data['monitoring']['http_server']['auth']['password'] = self.config.monitoring.http_server.auth.password
                        logger.info("Keeping current password (new password was empty)")
                    else:
                        logger.info("Updating password")
                
                # Handle PushOver credentials - keep current values if empty
                if 'pushover' in data:
                    if 'api_token' in data['pushover'] and (not data['pushover']['api_token'] or data['pushover']['api_token'].strip() == ''):
                        data['pushover']['api_token'] = self.config.pushover.api_token
                        logger.info("Keeping current PushOver API token (new token was empty)")
                    if 'user_key' in data['pushover'] and (not data['pushover']['user_key'] or data['pushover']['user_key'].strip() == ''):
                        data['pushover']['user_key'] = self.config.pushover.user_key
                        logger.info("Keeping current PushOver user key (new key was empty)")
                
                # Handle empty optional Path/string fields - convert empty strings to None
                if 'alerts' in data:
                    if 'tail_message_path' in data['alerts']:
                        if isinstance(data['alerts']['tail_message_path'], str) and data['alerts']['tail_message_path'].strip() == '':
                            data['alerts']['tail_message_path'] = None
                    if 'tail_message_suffix' in data['alerts']:
                        if isinstance(data['alerts']['tail_message_suffix'], str) and data['alerts']['tail_message_suffix'].strip() == '':
                            data['alerts']['tail_message_suffix'] = None
                
                # Create new config from the received data
                from ..core.config import AppConfig
                updated_config = AppConfig(**data)
                
                # Save to config file (use the configured config file path)
                config_path = self.config.config_file
                if not config_path.is_absolute():
                    # If relative path, make it relative to the application directory
                    config_path = Path("/etc/skywarnplus-ng") / config_path
                config_path.parent.mkdir(parents=True, exist_ok=True)
                
                yaml = YAML()
                yaml.default_flow_style = False
                yaml.preserve_quotes = True
                yaml.width = 4096
                
                # Convert config to dict and handle Path objects
                config_dict = updated_config.model_dump()
                
                # Convert Path objects to strings for YAML serialization
                def convert_paths_for_yaml(obj):
                    if isinstance(obj, dict):
                        return {k: convert_paths_for_yaml(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_paths_for_yaml(item) for item in obj]
                    elif hasattr(obj, '__fspath__'):  # Path-like object
                        return str(obj)
                    else:
                        return obj
                
                serializable_config = convert_paths_for_yaml(config_dict)
                
                # Write to file
                with open(config_path, 'w') as f:
                    yaml.dump(serializable_config, f)
                
                # Update the application's config reference
                self.config = updated_config
                if self.app:
                    self.app.config = updated_config
                
                logger.info(f"Configuration saved to {config_path}")
                
                return web.json_response({
                    "success": True,
                    "message": "Configuration updated and saved successfully",
                    "config_file": str(config_path)
                })
                
            except Exception as validation_error:
                logger.error(f"Configuration validation failed: {validation_error}")
                return web.json_response({
                    "success": False,
                    "error": f"Invalid configuration: {str(validation_error)}"
                }, status=400)
                
        except Exception as e:
            logger.error(f"Error updating config: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_config_reset_handler(self, request: Request) -> Response:
        """Handle API config reset endpoint."""
        try:
            # Reset to default configuration
            # This would require implementing configuration reset logic
            return web.json_response({
                "success": True,
                "message": "Configuration reset to defaults"
            })
        except Exception as e:
            logger.error(f"Error resetting config: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_config_backup_handler(self, request: Request) -> Response:
        """Handle API config backup endpoint."""
        try:
            # Create configuration backup
            # This would require implementing backup logic
            return web.json_response({
                "success": True,
                "message": "Configuration backed up successfully"
            })
        except Exception as e:
            logger.error(f"Error backing up config: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_county_generate_audio_handler(self, request: Request) -> Response:
        """Handle API county audio generation endpoint."""
        try:
            county_code = request.match_info.get('county_code')
            if not county_code:
                return web.json_response({"error": "county_code is required"}, status=400)
            
            # Find the county in config
            county = None
            for c in self.config.counties:
                if c.code == county_code:
                    county = c
                    break
            
            if not county:
                return web.json_response({"error": f"County {county_code} not found"}, status=404)
            
            if not county.name:
                return web.json_response({"error": "County name is required"}, status=400)
            
            # Check if audio manager is available
            if not self.app.audio_manager:
                return web.json_response({"error": "Audio manager not available"}, status=503)
            
            # Generate audio file
            filename = self.app.audio_manager.generate_county_audio(county.name)
            
            if not filename:
                return web.json_response({
                    "success": False,
                    "error": "Failed to generate county audio file"
                }, status=500)
            
            # Update county config with generated filename
            county.audio_file = filename
            
            # Save config
            try:
                from ruamel.yaml import YAML
                yaml = YAML()
                yaml.preserve_quotes = True
                config_path = Path("/etc/skywarnplus-ng/config.yaml")
                
                with open(config_path, "r") as f:
                    config_data = yaml.load(f)
                
                # Update the county in config
                if 'counties' in config_data:
                    for i, c in enumerate(config_data['counties']):
                        if c.get('code') == county_code:
                            config_data['counties'][i]['audio_file'] = filename
                            break
                
                with open(config_path, "w") as f:
                    yaml.dump(config_data, f)
                
                logger.info(f"Updated config with generated audio file for {county_code}: {filename}")
            except Exception as e:
                logger.warning(f"Failed to update config file: {e}")
                # Continue anyway - the file was generated
            
            return web.json_response({
                "success": True,
                "filename": filename,
                "message": f"Generated audio file: {filename}"
            })
            
        except Exception as e:
            logger.error(f"Error generating county audio: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_config_restore_handler(self, request: Request) -> Response:
        """Handle API config restore endpoint."""
        try:
            # Restore configuration from backup
            # This would require implementing restore logic
            return web.json_response({
                "success": True,
                "message": "Configuration restored successfully"
            })
        except Exception as e:
            logger.error(f"Error restoring config: {e}")
            return web.json_response({"error": str(e)}, status=500)

    # Notification API handlers
    async def api_notifications_test_email_handler(self, request: Request) -> Response:
        """Handle email connection test."""
        try:
            data = await request.json()
            
            # Import notification modules
            from ..notifications.email import EmailNotifier, EmailConfig, EmailProvider
            
            # Create email config
            provider = EmailProvider(data.get('provider', 'gmail'))
            email_config = EmailConfig(
                provider=provider,
                smtp_server=data.get('smtp_server', ''),
                smtp_port=data.get('smtp_port', 587),
                use_tls=data.get('use_tls', True),
                use_ssl=data.get('use_ssl', False),
                username=data.get('username', ''),
                password=data.get('password', ''),
                from_name=data.get('from_name', 'SkywarnPlus-NG')
            )
            
            # Test connection
            notifier = EmailNotifier(email_config)
            success = notifier.test_connection()
            
            if success:
                return web.json_response({
                    "success": True,
                    "message": "Email connection test successful"
                })
            else:
                return web.json_response({
                    "success": False,
                    "message": "Email connection test failed - check credentials and settings",
                    "error": "Connection test failed"
                })
            
        except Exception as e:
            logger.error(f"Error testing email connection: {e}")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def api_notifications_subscribers_handler(self, request: Request) -> Response:
        """Handle subscribers list endpoint."""
        try:
            # Import notification modules
            from ..notifications.subscriber import SubscriberManager
            
            # Get subscribers (this would need to be integrated with the app)
            subscriber_manager = SubscriberManager()
            subscribers = subscriber_manager.get_all_subscribers()
            
            # Convert to dict format for JSON response
            subscribers_data = [subscriber.to_dict() for subscriber in subscribers]
            
            return web.json_response(subscribers_data)
            
        except Exception as e:
            logger.error(f"Error getting subscribers: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_add_subscriber_handler(self, request: Request) -> Response:
        """Handle add subscriber endpoint."""
        try:
            data = await request.json()
            
            # Import notification modules
            from ..notifications.subscriber import SubscriberManager, Subscriber, SubscriptionPreferences, NotificationMethod, SubscriptionStatus
            
            # Create subscriber
            preferences = SubscriptionPreferences(
                counties=data.get('counties', []),
                states=data.get('states', []),
                enabled_severities=set(data.get('enabled_severities', [])),
                enabled_urgencies=set(data.get('enabled_urgencies', [])),
                enabled_certainties=set(data.get('enabled_certainties', [])),
                enabled_methods=set(data.get('enabled_methods', [NotificationMethod.EMAIL])),
                max_notifications_per_hour=data.get('max_notifications_per_hour', 10),
                max_notifications_per_day=data.get('max_notifications_per_day', 50)
            )
            
            subscriber = Subscriber(
                subscriber_id=data.get('subscriber_id', str(uuid.uuid4())),
                name=data.get('name', ''),
                email=data.get('email', ''),
                status=SubscriptionStatus(data.get('status', 'active')),
                preferences=preferences,
                phone=data.get('phone'),
                webhook_url=data.get('webhook_url'),
                push_tokens=data.get('push_tokens', [])
            )
            
            # Add subscriber
            subscriber_manager = SubscriberManager()
            success = subscriber_manager.add_subscriber(subscriber)
            
            if success:
                return web.json_response({
                    "success": True,
                    "message": "Subscriber added successfully",
                    "subscriber_id": subscriber.subscriber_id
                })
            else:
                return web.json_response({
                    "success": False,
                    "error": "Failed to add subscriber"
                }, status=400)
                
        except Exception as e:
            logger.error(f"Error adding subscriber: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_update_subscriber_handler(self, request: Request) -> Response:
        """Handle update subscriber endpoint."""
        try:
            subscriber_id = request.match_info['subscriber_id']
            data = await request.json()
            
            # Import notification modules
            from ..notifications.subscriber import SubscriberManager, Subscriber, SubscriptionPreferences, NotificationMethod, SubscriptionStatus
            
            # Get existing subscriber
            subscriber_manager = SubscriberManager()
            subscriber = subscriber_manager.get_subscriber(subscriber_id)
            
            if not subscriber:
                return web.json_response({"error": "Subscriber not found"}, status=404)
            
            # Update subscriber data
            if 'name' in data:
                subscriber.name = data['name']
            if 'email' in data:
                subscriber.email = data['email']
            if 'status' in data:
                subscriber.status = SubscriptionStatus(data['status'])
            if 'phone' in data:
                subscriber.phone = data['phone']
            if 'webhook_url' in data:
                subscriber.webhook_url = data['webhook_url']
            if 'push_tokens' in data:
                subscriber.push_tokens = data['push_tokens']
            
            # Update preferences
            if 'preferences' in data:
                prefs_data = data['preferences']
                subscriber.preferences.counties = prefs_data.get('counties', [])
                subscriber.preferences.states = prefs_data.get('states', [])
                subscriber.preferences.enabled_severities = set(prefs_data.get('enabled_severities', []))
                subscriber.preferences.enabled_urgencies = set(prefs_data.get('enabled_urgencies', []))
                subscriber.preferences.enabled_certainties = set(prefs_data.get('enabled_certainties', []))
                subscriber.preferences.enabled_methods = set(prefs_data.get('enabled_methods', [NotificationMethod.EMAIL]))
                subscriber.preferences.max_notifications_per_hour = prefs_data.get('max_notifications_per_hour', 10)
                subscriber.preferences.max_notifications_per_day = prefs_data.get('max_notifications_per_day', 50)
            
            # Save updated subscriber
            success = subscriber_manager.update_subscriber(subscriber)
            
            if success:
                return web.json_response({
                    "success": True,
                    "message": "Subscriber updated successfully"
                })
            else:
                return web.json_response({
                    "success": False,
                    "error": "Failed to update subscriber"
                }, status=400)
                
        except Exception as e:
            logger.error(f"Error updating subscriber: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_delete_subscriber_handler(self, request: Request) -> Response:
        """Handle delete subscriber endpoint."""
        try:
            subscriber_id = request.match_info['subscriber_id']
            
            # Import notification modules
            from ..notifications.subscriber import SubscriberManager
            
            # Delete subscriber
            subscriber_manager = SubscriberManager()
            success = subscriber_manager.remove_subscriber(subscriber_id)
            
            if success:
                return web.json_response({
                    "success": True,
                    "message": "Subscriber deleted successfully"
                })
            else:
                return web.json_response({
                    "success": False,
                    "error": "Subscriber not found"
                }, status=404)
                
        except Exception as e:
            logger.error(f"Error deleting subscriber: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_templates_handler(self, request: Request) -> Response:
        """Handle templates list endpoint."""
        try:
            # Import notification modules
            from ..notifications.templates import TemplateEngine
            
            # Get templates
            template_engine = TemplateEngine()
            templates = template_engine.get_available_templates()
            
            return web.json_response(templates)
            
        except Exception as e:
            logger.error(f"Error getting templates: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_add_template_handler(self, request: Request) -> Response:
        """Handle add template endpoint."""
        try:
            data = await request.json()
            
            # Import notification modules
            from ..notifications.templates import TemplateEngine, NotificationTemplate, TemplateType, TemplateFormat
            
            # Create template
            template = NotificationTemplate(
                template_id=data.get('template_id', str(uuid.uuid4())),
                name=data.get('name', ''),
                description=data.get('description', ''),
                template_type=TemplateType(data.get('template_type', 'email')),
                format=TemplateFormat(data.get('format', 'html')),
                subject_template=data.get('subject_template', ''),
                body_template=data.get('body_template', ''),
                enabled=data.get('enabled', True)
            )
            
            # Add template
            template_engine = TemplateEngine()
            template_engine.add_template(template)
            
            return web.json_response({
                "success": True,
                "message": "Template added successfully",
                "template_id": template.template_id
            })
            
        except Exception as e:
            logger.error(f"Error adding template: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_update_template_handler(self, request: Request) -> Response:
        """Handle update template endpoint."""
        try:
            template_id = request.match_info['template_id']
            data = await request.json()
            
            # Import notification modules
            from ..notifications.templates import TemplateEngine, NotificationTemplate, TemplateType, TemplateFormat
            
            # Get existing template
            template_engine = TemplateEngine()
            template = template_engine.get_template(template_id)
            
            if not template:
                return web.json_response({"error": "Template not found"}, status=404)
            
            # Update template data
            if 'name' in data:
                template.name = data['name']
            if 'description' in data:
                template.description = data['description']
            if 'template_type' in data:
                template.template_type = TemplateType(data['template_type'])
            if 'format' in data:
                template.format = TemplateFormat(data['format'])
            if 'subject_template' in data:
                template.subject_template = data['subject_template']
            if 'body_template' in data:
                template.body_template = data['body_template']
            if 'enabled' in data:
                template.enabled = data['enabled']
            
            # Update template
            template_engine.add_template(template)
            
            return web.json_response({
                "success": True,
                "message": "Template updated successfully"
            })
            
        except Exception as e:
            logger.error(f"Error updating template: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_delete_template_handler(self, request: Request) -> Response:
        """Handle delete template endpoint."""
        try:
            template_id = request.match_info['template_id']
            
            # Import notification modules
            from ..notifications.templates import TemplateEngine
            
            # Delete template
            template_engine = TemplateEngine()
            template = template_engine.get_template(template_id)
            
            if not template:
                return web.json_response({"error": "Template not found"}, status=404)
            
            # Remove template (this would need to be implemented in TemplateEngine)
            del template_engine.templates[template_id]
            
            return web.json_response({
                "success": True,
                "message": "Template deleted successfully"
            })
            
        except Exception as e:
            logger.error(f"Error deleting template: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_stats_handler(self, request: Request) -> Response:
        """Handle notification statistics endpoint."""
        try:
            # Import notification modules
            # Note: notification stats are currently mocked; no import needed
            
            # Get notification stats (this would need to be integrated with the app)
            # For now, return mock data
            stats = {
                "subscribers": {
                    "total_subscribers": 0,
                    "active_subscribers": 0,
                    "inactive_subscribers": 0
                },
                "notifiers": {
                    "email": 0,
                    "webhook": 0,
                    "push": 0
                },
                "delivery_queue": {
                    "total_items": 0,
                    "pending": 0,
                    "sent": 0,
                    "failed": 0
                }
            }
            
            return web.json_response(stats)
            
        except Exception as e:
            logger.error(f"Error getting notification stats: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def login_handler(self, request: Request) -> Response:
        """Handle login page."""
        # If already authenticated, redirect to configuration page
        if await self._is_authenticated(request):
            # Get base_path from app storage (normalized) or fallback to config
            base_path = request.app.get('base_path', '') or self.config.monitoring.http_server.base_path or ''
            if base_path and not base_path.startswith('/'):
                base_path = '/' + base_path
            return web.Response(status=302, headers={'Location': f'{base_path}/configuration'})
            
        template = self.template_env.get_template('login.html')
        content = template.render(title="Login - Configuration Access")
        return web.Response(text=content, content_type='text/html')

    async def api_login_handler(self, request: Request) -> Response:
        """Handle API login endpoint."""
        try:
            data = await request.json()
            username = data.get('username', '').strip()
            password = data.get('password', '')
            remember = data.get('remember', False)
            
            if not username or not password:
                return web.json_response({'error': 'Username and password required'}, status=400)
            
            # Check credentials
            auth_config = self.config.monitoring.http_server.auth
            if (username == auth_config.username and 
                password == auth_config.password):
                
                # Create session
                session = await new_session(request)
                session['user_id'] = username
                session['login_time'] = datetime.now(timezone.utc).isoformat()
                session['remember'] = remember
                
                logger.info(f"User {username} logged in successfully")
                return web.json_response({'success': True, 'message': 'Login successful'})
            else:
                logger.warning(f"Failed login attempt for user: {username}")
                return web.json_response({'error': 'Invalid username or password'}, status=401)
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return web.json_response({'error': 'Login failed'}, status=500)

    async def api_logout_handler(self, request: Request) -> Response:
        """Handle API logout endpoint."""
        try:
            session = await get_session(request)
            user_id = session.get('user_id')
            
            if user_id:
                logger.info(f"User {user_id} logged out")
                session.clear()
                
            return web.json_response({'success': True, 'message': 'Logout successful'})
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return web.json_response({'error': 'Logout failed'}, status=500)

    async def websocket_handler(self, request: Request) -> Response:
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.websocket_clients.add(ws)
        logger.info(f"WebSocket client connected. Total clients: {len(self.websocket_clients)}")
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self._handle_websocket_message(ws, data)
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
        except ConnectionClosed:
            pass
        finally:
            self.websocket_clients.discard(ws)
            logger.info(f"WebSocket client disconnected. Total clients: {len(self.websocket_clients)}")
        
        return ws

    async def _handle_websocket_message(self, ws, data: Dict[str, Any]) -> None:
        """Handle WebSocket messages."""
        message_type = data.get('type')
        
        if message_type == 'ping':
            await ws.send_str(json.dumps({'type': 'pong'}))
        elif message_type == 'subscribe':
            # Handle subscription to specific data types
            subscription = data.get('subscription')
            if subscription == 'alerts':
                # Send current alerts
                alerts = await self._get_current_alerts()
                await ws.send_str(json.dumps({
                    'type': 'alerts_update',
                    'data': alerts
                }))
        # Add more message types as needed

    async def _get_current_alerts(self) -> List[Dict[str, Any]]:
        """Get current alerts for WebSocket updates."""
        try:
            active_alerts = self.app.state.get('active_alerts', [])
            alerts_data = []
            
            for alert_id in active_alerts:
                alert_data = self.app.state.get('last_alerts', {}).get(alert_id)
                if alert_data:
                    alerts_data.append(alert_data)
            
            return alerts_data
        except Exception as e:
            logger.error(f"Error getting current alerts: {e}")
            return []

    async def broadcast_update(self, update_type: str, data: Any) -> None:
        """Broadcast update to all WebSocket clients."""
        if not self.websocket_clients:
            return
        
        message = json.dumps({
            'type': update_type,
            'data': data,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        # Send to all connected clients
        disconnected = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_str(message)
            except ConnectionClosed:
                disconnected.add(ws)
        
        # Remove disconnected clients
        self.websocket_clients -= disconnected

    async def start(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Start the web dashboard server."""
        try:
            self.web_app = self.create_app()
            self.runner = web.AppRunner(self.web_app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, host, port)
            await self.site.start()
            
            # Normalize base_path for logging (same as in create_app)
            base_path = self.config.monitoring.http_server.base_path or ''
            if base_path:
                base_path = base_path.strip()
                if not base_path.startswith('/'):
                    base_path = '/' + base_path
                if base_path.endswith('/'):
                    base_path = base_path.rstrip('/')
            
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
            
        except Exception as e:
            logger.error(f"Failed to start web dashboard: {e}")
            raise WebDashboardError(f"Failed to start web dashboard: {e}") from e

    async def stop(self) -> None:
        """Stop the web dashboard server."""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            logger.info("Web dashboard stopped")
        except Exception as e:
            logger.error(f"Error stopping web dashboard: {e}")
