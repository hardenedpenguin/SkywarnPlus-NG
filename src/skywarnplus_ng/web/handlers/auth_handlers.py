"""
Auth-related HTTP handlers mixin for the web dashboard.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp.web import Request, Response
from aiohttp_session import get_session, new_session

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class AuthHandlersMixin:
    async def login_handler(self, request: Request) -> Response:
        """Handle login page."""
        if await self._is_authenticated(request):
            base_path = (
                request.app.get("base_path", "")
                or self.config.monitoring.http_server.base_path
                or ""
            )
            if base_path and not base_path.startswith("/"):
                base_path = "/" + base_path
            next_path = request.query.get("next", "").strip()
            if next_path and next_path.startswith("/") and not next_path.startswith("//"):
                loc = f"{base_path}{next_path}" if base_path else next_path
            else:
                loc = f"{base_path}/" if base_path else "/"
            return web.Response(status=302, headers={"Location": loc})

        template = self.template_env.get_template("login.html")
        content = template.render(title="Login - Configuration Access")
        return web.Response(text=content, content_type="text/html")

    async def api_login_handler(self, request: Request) -> Response:
        """Handle API login endpoint."""
        try:
            client_ip = self._client_ip(request)
            allowed, retry_after = await self._login_rate_limit.check(client_ip)
            if not allowed:
                headers = {}
                if retry_after is not None:
                    headers["Retry-After"] = str(max(1, int(retry_after) + 1))
                return web.json_response(
                    {"error": "Too many login attempts. Try again later."},
                    status=429,
                    headers=headers,
                )

            data = await request.json()
            if not isinstance(data, dict):
                return web.json_response({"error": "JSON body must be an object"}, status=400)
            username = data.get("username", "").strip()
            password = data.get("password", "")
            remember = data.get("remember", False)

            if not username or not password:
                return web.json_response({"error": "Username and password required"}, status=400)

            # Check credentials
            auth_config = self.config.monitoring.http_server.auth
            if username == auth_config.username and self._verify_password(
                password, auth_config.password
            ):
                if not self._is_bcrypt_hash(auth_config.password):
                    self._persist_dashboard_auth_password(self._hash_password(password))

                must_change = self._uses_default_dashboard_password()

                # Create session
                session = await new_session(request)
                session["user_id"] = username
                session["login_time"] = datetime.now(timezone.utc).isoformat()
                session["remember"] = remember

                logger.info(f"User {username} logged in successfully")
                body: dict = {"success": True, "message": "Login successful"}
                if must_change:
                    body["must_change_password"] = True
                return web.json_response(body)
            else:
                logger.warning(f"Failed login attempt for user: {username}")
                return web.json_response({"error": "Invalid username or password"}, status=401)

        except Exception as e:
            logger.error(f"Login error: {e}")
            return web.json_response({"error": "Login failed"}, status=500)

    async def api_logout_handler(self, request: Request) -> Response:
        """Handle API logout endpoint."""
        try:
            session = await get_session(request)
            user_id = session.get("user_id")

            if user_id:
                logger.info(f"User {user_id} logged out")
                session.clear()

            return web.json_response({"success": True, "message": "Logout successful"})
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return web.json_response({"error": "Logout failed"}, status=500)
