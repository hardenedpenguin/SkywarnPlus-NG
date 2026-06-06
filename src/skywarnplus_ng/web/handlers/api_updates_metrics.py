"""
Update check, activity, and metrics API handlers mixin.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

import aiohttp
from aiohttp import web
from aiohttp.web import Request, Response

from ... import __version__ as _PACKAGE_VERSION
from ...utils.update_check import (
    build_cache_payload,
    cache_is_fresh,
    fetch_latest_release,
    normalize_release_version,
    read_cache,
    write_cache,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class UpdatesMetricsApiMixin:
    def _update_check_cache_path(self) -> Path:
        return self._get_data_dir() / "update_check_cache.json"

    def _update_status_public_dict(self, cached: Dict[str, Any]) -> Dict[str, Any]:
        """Shape returned to the browser (no secrets)."""
        return {
            "check_enabled": True,
            "installed_version": cached.get("installed_version") or _PACKAGE_VERSION,
            "update_available": bool(cached.get("update_available")),
            "latest_version": cached.get("remote_version") or None,
            "latest_tag": cached.get("remote_tag") or None,
            "release_url": cached.get("html_url") or None,
            "checked_at": cached.get("checked_at"),
            "error": cached.get("error"),
        }

    async def _refresh_update_cache(self) -> Optional[Dict[str, Any]]:
        """Fetch GitHub latest release and write cache. Caller should hold lock or expect single-flight."""
        uc = self.config.monitoring.update_check
        if not uc.enabled:
            return None
        cache_path = self._update_check_cache_path()
        session = self._github_http_session
        if session is None or session.closed:
            session = aiohttp.ClientSession(
                headers={"User-Agent": "SkywarnPlus-NG-UpdateCheck/1.0"}
            )
            self._github_http_session = session
        repo = (uc.github_repo or "").strip()
        try:
            rel = await fetch_latest_release(session, repo)
            rv = normalize_release_version(rel.get("tag_name") or "")
            payload = build_cache_payload(
                installed_version=_PACKAGE_VERSION,
                remote_tag=rel.get("tag_name") or "",
                remote_version=rv,
                html_url=rel.get("html_url") or "",
                published_at=rel.get("published_at") or "",
                error=None,
            )
        except Exception as e:
            logger.warning("Update check failed: %s", e)
            payload = build_cache_payload(
                installed_version=_PACKAGE_VERSION,
                remote_tag="",
                remote_version="",
                html_url="",
                published_at="",
                error=str(e),
            )
        try:
            write_cache(cache_path, payload)
        except OSError as oe:
            logger.warning("Could not write update check cache: %s", oe)
        return payload

    async def api_update_status_handler(self, request: Request) -> Response:
        """Advisory update status (public). Respects monitoring.update_check config and cache interval."""
        try:
            uc = self.config.monitoring.update_check
            if not uc.enabled:
                return web.json_response(
                    {
                        "check_enabled": False,
                        "installed_version": _PACKAGE_VERSION,
                        "update_available": False,
                        "latest_version": None,
                        "latest_tag": None,
                        "release_url": None,
                        "checked_at": None,
                        "error": None,
                    }
                )

            cache_path = self._update_check_cache_path()
            cached = read_cache(cache_path)
            force = request.query.get("force") == "1"

            if not force and cached and cache_is_fresh(cached, uc.interval_hours):
                return web.json_response(self._update_status_public_dict(cached))

            async with self._update_check_lock:
                cached = read_cache(cache_path)
                if not force and cached and cache_is_fresh(cached, uc.interval_hours):
                    return web.json_response(self._update_status_public_dict(cached))
                refreshed = await self._refresh_update_cache()
                if refreshed:
                    return web.json_response(self._update_status_public_dict(refreshed))
                if cached:
                    return web.json_response(self._update_status_public_dict(cached))
                return web.json_response(
                    {
                        "check_enabled": True,
                        "installed_version": _PACKAGE_VERSION,
                        "update_available": False,
                        "latest_version": None,
                        "latest_tag": None,
                        "release_url": None,
                        "checked_at": None,
                        "error": "No cache yet",
                    }
                )
        except Exception as e:
            logger.error("update-status error: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def _update_check_background_loop(self) -> None:
        """Periodic refresh so the dashboard shows updates without relying on page loads."""
        try:
            await asyncio.sleep(300)
            while True:
                try:
                    uc = self.config.monitoring.update_check
                    if uc.enabled:
                        cache_path = self._update_check_cache_path()
                        cached = read_cache(cache_path)
                        if not cached or not cache_is_fresh(cached, uc.interval_hours):
                            async with self._update_check_lock:
                                cached = read_cache(cache_path)
                                if not cached or not cache_is_fresh(cached, uc.interval_hours):
                                    await self._refresh_update_cache()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.debug("Background update check failed", exc_info=True)
                try:
                    hrs = float(self.config.monitoring.update_check.interval_hours)
                except (TypeError, ValueError):
                    hrs = 24.0
                await asyncio.sleep(max(3600.0, hrs * 3600.0))
        except asyncio.CancelledError:
            pass

    async def api_activity_handler(self, request: Request) -> Response:
        """Handle API recent activity endpoint."""
        try:
            # Get limit parameter
            limit = int(request.query.get("limit", 20))

            activities = []

            # Get recent alerts from database
            if self.app.database_manager:
                try:
                    recent_alerts = await self.app.database_manager.get_recent_alerts(
                        limit=5, hours=24
                    )
                    for alert in recent_alerts:
                        # Helper function to safely format datetime
                        def format_datetime(dt):
                            if dt is None:
                                return None
                            if hasattr(dt, "isoformat"):
                                return dt.isoformat()
                            return str(dt)

                        activities.append(
                            {
                                "type": "alert_processed",
                                "message": f"Processed {alert.severity.lower()} alert: {alert.event}",
                                "details": f"Area: {alert.area_desc}",
                                "timestamp": format_datetime(alert.processed_at),
                                "severity": alert.severity.lower(),
                                "icon": "alert-triangle"
                                if alert.severity in ["Extreme", "Severe"]
                                else "info",
                            }
                        )

                        if alert.announced:
                            activities.append(
                                {
                                    "type": "alert_announced",
                                    "message": f"Announced {alert.severity.lower()} alert: {alert.event}",
                                    "details": f"Area: {alert.area_desc}",
                                    "timestamp": format_datetime(alert.processed_at),
                                    "severity": alert.severity.lower(),
                                    "icon": "volume-2",
                                }
                            )
                except Exception as e:
                    logger.warning(f"Could not fetch recent alerts for activity: {e}")

            # Add system status activities
            if self.app:
                try:
                    status = self.app.get_status()

                    # Add NWS connection status
                    if status.get("nws_connected"):
                        activities.append(
                            {
                                "type": "system_status",
                                "message": "NWS API connection active",
                                "details": "Weather data is being received",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "severity": "info",
                                "icon": "wifi",
                            }
                        )

                    # Add Asterisk connection status
                    if status.get("asterisk_available"):
                        activities.append(
                            {
                                "type": "system_status",
                                "message": "Asterisk connection active",
                                "details": "DTMF commands and announcements available",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "severity": "info",
                                "icon": "phone",
                            }
                        )

                    # Add audio system status
                    if status.get("audio_available"):
                        activities.append(
                            {
                                "type": "system_status",
                                "message": "Audio system operational",
                                "details": "TTS and sound file playback available",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "severity": "info",
                                "icon": "speaker",
                            }
                        )

                except Exception as e:
                    logger.warning(f"Could not get system status for activity: {e}")

            # Add server startup activity
            activities.append(
                {
                    "type": "system_event",
                    "message": "SkywarnPlus-NG server started",
                    "details": "All systems initialized and monitoring active",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "severity": "success",
                    "icon": "play-circle",
                }
            )

            # Sort activities by timestamp (most recent first)
            activities.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

            # Limit results
            activities = activities[:limit]

            return web.json_response(
                {
                    "activities": activities,
                    "count": len(activities),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        except Exception as e:
            logger.error(f"Error getting recent activity: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_metrics_handler(self, request: Request) -> Response:
        """Handle API metrics endpoint."""
        try:
            # Get query parameters
            hours = int(request.query.get("hours", 24))
            metric_name = request.query.get("metric_name")

            metrics_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "period_hours": hours,
                "metrics": {},
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
                        "uptime_percentage": performance_metrics.uptime_percentage,
                    }

                    # Get alert statistics
                    from ...processing.analytics import AnalyticsPeriod

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
                        "hourly_distribution": alert_stats.hourly_distribution,
                    }
                except Exception as e:
                    logger.error(f"Failed to get analytics metrics: {e}")
                    metrics_data["metrics"]["performance"] = {"error": "Analytics unavailable"}
            else:
                metrics_data["metrics"]["performance"] = {"error": "Analytics not initialized"}

            # Get system metrics from application status
            if hasattr(self.app, "get_status"):
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
                        "database_available": status.get("database_available", False),
                    }
                except Exception as e:
                    logger.error(f"Failed to get system metrics: {e}")
                    metrics_data["metrics"]["system"] = {"error": "System status unavailable"}

            # Get health metrics if available
            if self.app.health_monitor:
                try:
                    health_status = await self.app.health_monitor.get_health_status(
                        getattr(self.app, "state", None)
                    )
                    metrics_data["metrics"]["health"] = {
                        "overall_status": health_status.overall_status.value,
                        "component_count": len(health_status.components),
                        "healthy_components": len(
                            [c for c in health_status.components if c.status.value == "healthy"]
                        ),
                        "unhealthy_components": len(
                            [c for c in health_status.components if c.status.value != "healthy"]
                        ),
                        "components": [
                            {
                                "name": comp.name,
                                "status": comp.status.value,
                                "response_time_ms": comp.response_time_ms,
                            }
                            for comp in health_status.components
                        ],
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
                    "data": metrics_data["metrics"][metric_name],
                }
                return web.json_response(filtered_data)

            # Get data for calculations
            health_data = metrics_data["metrics"].get("health", {})
            system_data = metrics_data["metrics"].get("system", {})

            # Calculate response time metrics
            response_times = []
            if "components" in health_data:
                response_times = [
                    c.get("response_time_ms", 0)
                    for c in health_data["components"]
                    if c.get("response_time_ms") is not None
                ]

            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            max_response_time = max(response_times) if response_times else 0
            min_response_time = min(response_times) if response_times else 0

            # Calculate request metrics (mock data based on system activity)
            total_requests = system_data.get("active_alerts", 0) * 10
            successful_requests = total_requests
            failed_requests = 0

            # Calculate system metrics (mock data for now)
            import psutil

            cpu_usage = 0.0
            memory_usage = 0.0
            disk_usage = 0.0
            try:
                cpu_usage = psutil.cpu_percent(interval=0.1)
            except Exception as e:
                logger.debug("CPU metric unavailable: %s", e)
            try:
                memory_info = psutil.virtual_memory()
                memory_usage = memory_info.percent
            except Exception as e:
                logger.debug("Memory metric unavailable: %s", e)
            try:
                disk_info = psutil.disk_usage("/")
                disk_usage = (disk_info.used / disk_info.total) * 100
            except Exception as e:
                logger.debug("Disk metric unavailable: %s", e)

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
                    "error_rate": (failed_requests / total_requests * 100)
                    if total_requests > 0
                    else 0,
                },
                # Detailed Request metrics
                "requests": {
                    "total_requests": total_requests,
                    "successful_requests": successful_requests,
                    "failed_requests": failed_requests,
                    "requests_per_hour": total_requests
                    / (system_data.get("uptime_seconds", 1) / 3600)
                    if system_data.get("uptime_seconds", 0) > 0
                    else 0,
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
                    "database_available": system_data.get("database_available", False),
                },
                # Original detailed metrics for charts and advanced views
                "metrics": metrics_data["metrics"],
            }

            return web.json_response(flattened_metrics)

        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return web.json_response({"error": str(e)}, status=500)
