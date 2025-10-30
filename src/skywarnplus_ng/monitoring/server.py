"""
Simple HTTP server for health monitoring and metrics.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from aiohttp import web
from aiohttp.web import Request, Response

from .health import HealthMonitor, HealthStatus


class MonitoringServer:
    """Simple HTTP server for health monitoring."""

    def __init__(self, health_monitor: HealthMonitor, host: str = "0.0.0.0", port: int = 8080):
        """
        Initialize monitoring server.

        Args:
            health_monitor: Health monitor instance
            host: Server host
            port: Server port
        """
        self.health_monitor = health_monitor
        self.host = host
        self.port = port
        self.logger = logging.getLogger(__name__)
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

    def create_app(self) -> web.Application:
        """Create the web application."""
        app = web.Application()
        
        # Add routes
        app.router.add_get('/health', self.health_handler)
        app.router.add_get('/health/detailed', self.detailed_health_handler)
        app.router.add_get('/health/history', self.health_history_handler)
        app.router.add_get('/metrics', self.metrics_handler)
        app.router.add_get('/status', self.status_handler)
        
        # Add CORS middleware
        app.middlewares.append(self.cors_middleware)
        
        return app

    async def cors_middleware(self, request: Request, handler):
        """CORS middleware."""
        response = await handler(request)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    async def health_handler(self, request: Request) -> Response:
        """Handle /health endpoint."""
        try:
            health_status = await self.health_monitor.get_health_status()
            
            # Return simple health status
            return web.json_response({
                "status": health_status.overall_status.value,
                "timestamp": health_status.timestamp.isoformat(),
                "uptime_seconds": health_status.uptime_seconds,
                "version": health_status.version
            })
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return web.json_response({
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }, status=500)

    async def detailed_health_handler(self, request: Request) -> Response:
        """Handle /health/detailed endpoint."""
        try:
            health_status = await self.health_monitor.get_health_status()
            
            # Convert to dict for JSON serialization
            health_dict = {
                "overall_status": health_status.overall_status.value,
                "timestamp": health_status.timestamp.isoformat(),
                "uptime_seconds": health_status.uptime_seconds,
                "version": health_status.version,
                "components": [
                    {
                        "name": comp.name,
                        "status": comp.status.value,
                        "message": comp.message,
                        "last_check": comp.last_check.isoformat(),
                        "response_time_ms": comp.response_time_ms,
                        "details": comp.details
                    }
                    for comp in health_status.components
                ],
                "metrics": health_status.metrics
            }
            
            return web.json_response(health_dict)
        except Exception as e:
            self.logger.error(f"Detailed health check failed: {e}")
            return web.json_response({
                "error": str(e)
            }, status=500)

    async def health_history_handler(self, request: Request) -> Response:
        """Handle /health/history endpoint."""
        try:
            limit = int(request.query.get('limit', 10))
            history = self.health_monitor.get_health_history(limit)
            
            history_dict = [
                {
                    "overall_status": status.overall_status.value,
                    "timestamp": status.timestamp.isoformat(),
                    "uptime_seconds": status.uptime_seconds,
                    "components": [
                        {
                            "name": comp.name,
                            "status": comp.status.value,
                            "message": comp.message,
                            "response_time_ms": comp.response_time_ms
                        }
                        for comp in status.components
                    ]
                }
                for status in history
            ]
            
            return web.json_response(history_dict)
        except Exception as e:
            self.logger.error(f"Health history failed: {e}")
            return web.json_response({
                "error": str(e)
            }, status=500)

    async def metrics_handler(self, request: Request) -> Response:
        """Handle /metrics endpoint (Prometheus format)."""
        try:
            health_status = await self.health_monitor.get_health_status()
            
            # Generate Prometheus-style metrics
            metrics = []
            
            # Overall status
            status_value = 1 if health_status.overall_status.value == "healthy" else 0
            metrics.append(f"skywarnplus_ng_healthy {status_value}")
            
            # Uptime
            metrics.append(f"skywarnplus_ng_uptime_seconds {health_status.uptime_seconds}")
            
            # Component status
            for comp in health_status.components:
                comp_status = 1 if comp.status.value == "healthy" else 0
                metrics.append(f'skywarnplus_ng_component_healthy{{component="{comp.name}"}} {comp_status}')
                
                if comp.response_time_ms is not None:
                    metrics.append(f'skywarnplus_ng_component_response_time_ms{{component="{comp.name}"}} {comp.response_time_ms}')
            
            # Configuration metrics
            for key, value in health_status.metrics.items():
                if isinstance(value, (int, float)):
                    metrics.append(f"skywarnplus_ng_config_{key} {value}")
            
            return web.Response(
                text="\n".join(metrics) + "\n",
                content_type="text/plain"
            )
        except Exception as e:
            self.logger.error(f"Metrics generation failed: {e}")
            return web.Response(
                text=f"# Error generating metrics: {e}\n",
                content_type="text/plain",
                status=500
            )

    async def status_handler(self, request: Request) -> Response:
        """Handle /status endpoint (simple status)."""
        try:
            summary = self.health_monitor.get_health_summary()
            return web.json_response(summary)
        except Exception as e:
            self.logger.error(f"Status check failed: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)

    async def start(self) -> None:
        """Start the monitoring server."""
        try:
            self.app = self.create_app()
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            
            self.logger.info(f"Monitoring server started on {self.host}:{self.port}")
            self.logger.info("Available endpoints:")
            self.logger.info(f"  http://{self.host}:{self.port}/health")
            self.logger.info(f"  http://{self.host}:{self.port}/health/detailed")
            self.logger.info(f"  http://{self.host}:{self.port}/health/history")
            self.logger.info(f"  http://{self.host}:{self.port}/metrics")
            self.logger.info(f"  http://{self.host}:{self.port}/status")
            
        except Exception as e:
            self.logger.error(f"Failed to start monitoring server: {e}")
            raise

    async def stop(self) -> None:
        """Stop the monitoring server."""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            self.logger.info("Monitoring server stopped")
        except Exception as e:
            self.logger.error(f"Error stopping monitoring server: {e}")
