"""
HTTP route registration for the web dashboard.

Kept separate from server.py to keep handler methods grouped on WebDashboard
while centralizing the route table in one place.
"""

from pathlib import Path
from typing import Any

from aiohttp import web


def register_dashboard_routes(app: web.Application, dashboard: Any) -> None:
    """Register all dashboard routes on ``app`` (``dashboard`` is a WebDashboard instance)."""
    app.router.add_static("/static", Path(__file__).parent / "static", name="static")

    app.router.add_get("/login", dashboard.login_handler)
    app.router.add_post("/api/auth/login", dashboard.api_login_handler)
    app.router.add_post("/api/auth/logout", dashboard.api_logout_handler)

    app.router.add_get("/", dashboard.dashboard_handler)
    app.router.add_get("/dashboard", dashboard.dashboard_handler)
    app.router.add_get("/alerts", dashboard.alerts_handler)
    app.router.add_get("/alerts/history", dashboard.alerts_history_handler)
    app.router.add_get("/configuration", dashboard.configuration_handler)
    app.router.add_get("/health", dashboard.health_handler)
    app.router.add_get("/logs", dashboard.logs_handler)
    app.router.add_get("/database", dashboard.database_handler)
    app.router.add_get("/metrics", dashboard.metrics_handler)
    app.router.add_get("/activity", dashboard.activity_handler)

    app.router.add_get("/api/status", dashboard.api_status_handler)
    app.router.add_get("/api/alerts", dashboard.api_alerts_handler)
    app.router.add_get("/api/alerts/history", dashboard.api_alerts_history_handler)
    app.router.add_get("/api/alerts/{alert_id}/audio", dashboard.api_alert_audio_handler)
    app.router.add_get("/api/health", dashboard.api_health_handler)
    app.router.add_get("/api/health/history", dashboard.api_health_history_handler)
    app.router.add_get("/api/logs", dashboard.api_logs_handler)
    app.router.add_get("/api/metrics", dashboard.api_metrics_handler)
    app.router.add_get("/api/activity", dashboard.api_activity_handler)
    app.router.add_get("/api/update-status", dashboard.api_update_status_handler)
    app.router.add_get("/api/database/stats", dashboard.api_database_stats_handler)
    app.router.add_post("/api/database/cleanup", dashboard.api_database_cleanup_handler)
    app.router.add_post("/api/database/optimize", dashboard.api_database_optimize_handler)
    app.router.add_post("/api/database/backup", dashboard.api_database_backup_handler)

    app.router.add_get("/api/config", dashboard.api_config_get_handler)
    app.router.add_post("/api/config", dashboard.api_config_update_handler)
    app.router.add_post("/api/config/reset", dashboard.api_config_reset_handler)
    app.router.add_post("/api/config/backup", dashboard.api_config_backup_handler)

    app.router.add_post(
        "/api/counties/{county_code}/generate-audio",
        dashboard.api_county_generate_audio_handler,
    )
    app.router.add_post("/api/config/restore", dashboard.api_config_restore_handler)

    app.router.add_post(
        "/api/notifications/test-email", dashboard.api_notifications_test_email_handler
    )
    app.router.add_get(
        "/api/notifications/subscribers", dashboard.api_notifications_subscribers_handler
    )
    app.router.add_post(
        "/api/notifications/subscribers", dashboard.api_notifications_add_subscriber_handler
    )
    app.router.add_put(
        "/api/notifications/subscribers/{subscriber_id}",
        dashboard.api_notifications_update_subscriber_handler,
    )
    app.router.add_delete(
        "/api/notifications/subscribers/{subscriber_id}",
        dashboard.api_notifications_delete_subscriber_handler,
    )
    app.router.add_get(
        "/api/notifications/templates", dashboard.api_notifications_templates_handler
    )
    app.router.add_get(
        "/api/notifications/templates/{template_id}",
        dashboard.api_notifications_template_detail_handler,
    )
    app.router.add_post(
        "/api/notifications/templates", dashboard.api_notifications_add_template_handler
    )
    app.router.add_put(
        "/api/notifications/templates/{template_id}",
        dashboard.api_notifications_update_template_handler,
    )
    app.router.add_delete(
        "/api/notifications/templates/{template_id}",
        dashboard.api_notifications_delete_template_handler,
    )
    app.router.add_get("/api/notifications/stats", dashboard.api_notifications_stats_handler)

    app.router.add_get("/ws", dashboard.websocket_handler)
