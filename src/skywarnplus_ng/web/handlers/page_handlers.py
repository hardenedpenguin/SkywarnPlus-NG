"""
HTML page handlers mixin for the web dashboard.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp.web import Request, Response

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PageHandlersMixin:
    async def dashboard_handler(self, request: Request) -> Response:
        """Handle dashboard page."""
        template = self.template_env.get_template("dashboard.html")
        content = template.render(
            title="SkywarnPlus-NG Dashboard",
            page="dashboard",
            config=self.config.model_dump(),
            is_authenticated=await self._is_authenticated(request),
        )
        return web.Response(text=content, content_type="text/html")

    async def alerts_handler(self, request: Request) -> Response:
        """Handle alerts page."""
        template = self.template_env.get_template("alerts.html")
        content = template.render(
            title="Active Alerts - SkywarnPlus-NG",
            page="alerts",
            config=self.config.model_dump(),
            is_authenticated=await self._is_authenticated(request),
        )
        return web.Response(text=content, content_type="text/html")

    async def alerts_history_handler(self, request: Request) -> Response:
        """Handle alerts history page."""
        template = self.template_env.get_template("alerts_history.html")
        content = template.render(
            title="Alert History - SkywarnPlus-NG",
            page="alerts_history",
            config=self.config.model_dump(),
            is_authenticated=await self._is_authenticated(request),
        )
        return web.Response(text=content, content_type="text/html")

    async def configuration_handler(self, request: Request) -> Response:
        """Handle configuration page."""
        template = self.template_env.get_template("configuration.html")
        content = template.render(
            title="Configuration - SkywarnPlus-NG",
            page="configuration",
            config=self.config.model_dump(),
            is_authenticated=await self._is_authenticated(request),
        )
        return web.Response(text=content, content_type="text/html")

    async def health_handler(self, request: Request) -> Response:
        """Handle health page."""
        template = self.template_env.get_template("health.html")
        content = template.render(
            title="System Health - SkywarnPlus-NG",
            page="health",
            config=self.config.model_dump(),
            is_authenticated=await self._is_authenticated(request),
        )
        return web.Response(text=content, content_type="text/html")

    async def logs_handler(self, request: Request) -> Response:
        """Handle logs page."""
        template = self.template_env.get_template("logs.html")
        content = template.render(
            title="Application Logs - SkywarnPlus-NG",
            page="logs",
            config=self.config.model_dump(),
            is_authenticated=await self._is_authenticated(request),
        )
        return web.Response(text=content, content_type="text/html")

    async def database_handler(self, request: Request) -> Response:
        """Handle database page."""
        template = self.template_env.get_template("database.html")
        content = template.render(
            title="Database - SkywarnPlus-NG",
            page="database",
            config=self.config.model_dump(),
            is_authenticated=await self._is_authenticated(request),
        )
        return web.Response(text=content, content_type="text/html")

    async def metrics_handler(self, request: Request) -> Response:
        """Handle metrics page."""
        template = self.template_env.get_template("metrics.html")
        content = template.render(
            title="Metrics - SkywarnPlus-NG",
            page="metrics",
            config=self.config.model_dump(),
            is_authenticated=await self._is_authenticated(request),
        )
        return web.Response(text=content, content_type="text/html")

    async def activity_handler(self, request: Request) -> Response:
        """Handle activity page (service summary and recent events)."""
        template = self.template_env.get_template("activity.html")
        content = template.render(
            title="Activity - SkywarnPlus-NG",
            page="activity",
            config=self.config.model_dump(),
            is_authenticated=await self._is_authenticated(request),
        )
        return web.Response(text=content, content_type="text/html")
