"""
Health, history, and logs API handlers mixin.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp.web import Request, Response

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class HealthLogsApiMixin:
    async def api_health_handler(self, request: Request) -> Response:
        """Handle API health endpoint."""
        try:
            if not self.app.health_monitor:
                return web.json_response({"error": "Health monitor not available"}, status=503)

            health_status = await self.app.health_monitor.get_health_status(
                getattr(self.app, "state", None)
            )

            # Get additional system information
            system_info = {}
            if hasattr(self.app, "get_status"):
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
                        "performance_metrics": app_status.get("performance_metrics", {}),
                    }
                except Exception as e:
                    logger.error(f"Failed to get additional system info: {e}")

            # Sanitize component details for JSON (e.g. Asterisk stores nodes with NodeConfig)
            def _sanitize_details(details):
                if not details or not isinstance(details, dict):
                    return details
                out = dict(details)
                if "nodes" in out and out["nodes"] is not None:
                    out["nodes"] = self._serialize_asterisk_nodes(
                        out["nodes"] if isinstance(out["nodes"], list) else [out["nodes"]]
                    )
                return out

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
                        "last_check": comp.last_check.isoformat()
                        if hasattr(comp, "last_check")
                        else None,
                        "details": _sanitize_details(getattr(comp, "details", None)),
                    }
                    for comp in health_status.components
                ],
                "summary": {
                    "total_components": len(health_status.components),
                    "healthy_components": len(
                        [c for c in health_status.components if c.status.value == "healthy"]
                    ),
                    "unhealthy_components": len(
                        [c for c in health_status.components if c.status.value != "healthy"]
                    ),
                    "degraded_components": len(
                        [c for c in health_status.components if c.status.value == "degraded"]
                    ),
                    "average_response_time_ms": sum(
                        c.response_time_ms
                        for c in health_status.components
                        if c.response_time_ms is not None
                    )
                    / len([c for c in health_status.components if c.response_time_ms is not None])
                    if any(c.response_time_ms is not None for c in health_status.components)
                    else None,
                },
                "metrics": health_status.metrics,
            }

            return web.json_response(health_data)
        except Exception as e:
            logger.error(f"Error getting health status: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_health_history_handler(self, request: Request) -> Response:
        """Handle API health history endpoint."""
        try:
            # Get query parameters
            limit = min(max(int(request.query.get("limit", 10)), 1), 500)

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
                    history_data.append(
                        {
                            "timestamp": record.timestamp.isoformat()
                            if hasattr(record, "timestamp")
                            else None,
                            "overall_status": record.overall_status.value
                            if hasattr(record, "overall_status")
                            else "unknown",
                            "uptime_seconds": getattr(record, "uptime_seconds", 0),
                            "version": getattr(record, "version", "unknown"),
                            "component_count": len(getattr(record, "components", [])),
                            "healthy_components": len(
                                [
                                    c
                                    for c in getattr(record, "components", [])
                                    if hasattr(c, "status") and c.status.value == "healthy"
                                ]
                            ),
                            "unhealthy_components": len(
                                [
                                    c
                                    for c in getattr(record, "components", [])
                                    if hasattr(c, "status") and c.status.value != "healthy"
                                ]
                            ),
                        }
                    )
                except Exception as e:
                    logger.error(f"Error processing health record: {e}")
                    continue

            # Return just the history array for frontend compatibility
            return web.json_response(history_data)
        except Exception as e:
            logger.error(f"Error getting health history: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_logs_handler(self, request: Request) -> Response:
        """Handle API logs endpoint.

        Query params:
          level — empty or ALL = no level filter; otherwise minimum severity (DEBUG…CRITICAL).
          limit — max entries returned after filtering (default 100).
          q — optional case-insensitive substring match on JSON-serialized entry or message.
        """
        _LEVEL_RANK = {
            "DEBUG": 10,
            "INFO": 20,
            "WARNING": 30,
            "ERROR": 40,
            "CRITICAL": 50,
        }

        def _entry_level(entry: dict) -> str:
            lv = entry.get("level") or "INFO"
            return str(lv).upper() if isinstance(lv, str) else "INFO"

        def _meets_level(entry: dict, min_level: str) -> bool:
            if not min_level or min_level.upper() in ("ALL", ""):
                return True
            want = _LEVEL_RANK.get(min_level.upper(), 20)
            got = _LEVEL_RANK.get(_entry_level(entry), 20)
            return got >= want

        try:
            level_param = (request.query.get("level") or "").strip()
            limit = min(max(int(request.query.get("limit", 100)), 1), 5000)
            search_q = (request.query.get("q") or "").strip().lower()

            log_file = self.config.logging.file
            if not log_file or not log_file.exists():
                return web.json_response({"logs": [], "count": 0})

            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            parsed = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed.append(json.loads(line))
                except json.JSONDecodeError:
                    parsed.append({"message": line, "level": "INFO"})

            filtered = [e for e in parsed if _meets_level(e, level_param)]
            if search_q:

                def _matches(e: dict) -> bool:
                    msg = str(e.get("message") or "").lower()
                    if search_q in msg:
                        return True
                    try:
                        return search_q in json.dumps(e, default=str).lower()
                    except Exception:
                        return False

                filtered = [e for e in filtered if _matches(e)]

            tail = filtered[-limit:] if limit > 0 else []

            return web.json_response(
                {
                    "logs": tail,
                    "count": len(tail),
                    "level": level_param or "ALL",
                    "limit": limit,
                }
            )
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
            return web.json_response({"error": str(e)}, status=500)
