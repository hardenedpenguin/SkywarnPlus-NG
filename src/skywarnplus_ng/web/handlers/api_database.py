"""
Database admin API handlers mixin.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp.web import Request, Response

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DatabaseApiMixin:
    async def api_database_stats_handler(self, request: Request) -> Response:
        """Handle API database stats endpoint."""
        try:
            if not self.app.database_manager:
                return web.json_response(
                    {
                        "connected": False,
                        "error": "Database not available",
                        "total_alerts": 0,
                        "active_alerts": 0,
                        "database_size_bytes": 0,
                    },
                    status=503,
                )

            stats = await self.app.database_manager.get_database_stats()

            # Add connection status and format for frontend
            enhanced_stats = {
                "connected": True,
                "total_alerts": stats.get("alerts_count", 0),
                "active_alerts": stats.get(
                    "alerts_count", 0
                ),  # For now, assume all alerts are active
                "database_size_bytes": stats.get("database_size_bytes", 0),
                "metrics_count": stats.get("metrics_count", 0),
                "health_checks_count": stats.get("health_checks_count", 0),
                "script_executions_count": stats.get("script_executions_count", 0),
                "configurations_count": stats.get("configurations_count", 0),
            }

            return web.json_response(enhanced_stats)
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return web.json_response(
                {
                    "connected": False,
                    "error": str(e),
                    "total_alerts": 0,
                    "active_alerts": 0,
                    "database_size_bytes": 0,
                },
                status=500,
            )

    async def api_database_cleanup_handler(self, request: Request) -> Response:
        """Handle API database cleanup endpoint."""
        try:
            if not self.app.database_manager:
                return web.json_response({"error": "Database not available"}, status=503)

            # Get days parameter from request body or use default
            try:
                if (
                    request.content_type == "application/json"
                    and request.content_length
                    and request.content_length > 0
                ):
                    data = await request.json()
                    if not isinstance(data, dict):
                        data = {}
                else:
                    data = {}
            except Exception:
                data = {}
            days = data.get("days", 30)
            try:
                days = int(days)
            except (TypeError, ValueError):
                return web.json_response({"error": "days must be an integer"}, status=400)
            if days < 1 or days > 3650:
                return web.json_response(
                    {"error": "days must be between 1 and 3650"},
                    status=400,
                )

            cleanup_stats = await self.app.database_manager.cleanup_old_data(days)
            return web.json_response(
                {
                    "success": True,
                    "message": "Database cleanup completed successfully",
                    "stats": cleanup_stats,
                }
            )
        except Exception as e:
            logger.error(f"Error cleaning up database: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_database_optimize_handler(self, request: Request) -> Response:
        """Handle API database optimize endpoint."""
        try:
            if not self.app.database_manager:
                return web.json_response({"error": "Database not available"}, status=503)

            optimization_stats = await self.app.database_manager.optimize_database()
            return web.json_response(
                {
                    "success": True,
                    "message": "Database optimization completed successfully",
                    "stats": optimization_stats,
                }
            )
        except Exception as e:
            logger.error(f"Error optimizing database: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_database_backup_handler(self, request: Request) -> Response:
        """Handle API database backup endpoint."""
        try:
            if not self.app.database_manager:
                return web.json_response({"error": "Database not available"}, status=503)

            backup_path = await self.app.database_manager.backup_database()
            return web.json_response(
                {
                    "success": True,
                    "message": "Database backup completed successfully",
                    "backup_path": str(backup_path),
                }
            )
        except Exception as e:
            logger.error(f"Error backing up database: {e}")
            return web.json_response({"error": str(e)}, status=500)
