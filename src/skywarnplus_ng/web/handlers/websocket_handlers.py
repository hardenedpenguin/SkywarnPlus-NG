"""
WebSocket handlers mixin for the web dashboard.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, TYPE_CHECKING

from aiohttp import web, WSMsgType
from aiohttp.web import Request, Response
from websockets.exceptions import ConnectionClosed

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class WebsocketHandlersMixin:
    async def websocket_handler(self, request: Request) -> Response:
        """Handle WebSocket connections."""
        # Protocol-level PING/PONG (browser answers automatically) so reverse proxies
        # (nginx default read timeouts, etc.) see regular upstream traffic. JSON app pings
        # from the client can be throttled when the tab is backgrounded.
        ws = web.WebSocketResponse(
            receive_timeout=None,
            heartbeat=20.0,
            autoping=True,
        )
        await ws.prepare(request)
        self.websocket_clients.add(ws)
        logger.info(f"WebSocket client connected. Total clients: {len(self.websocket_clients)}")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError as e:
                        logger.warning("WebSocket invalid JSON from client: %s", e)
                        continue
                    if not isinstance(data, dict):
                        logger.warning("WebSocket message body is not an object, ignoring")
                        continue
                    await self._handle_websocket_message(ws, data)
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
        except asyncio.CancelledError:
            raise
        except ConnectionClosed:
            pass
        except Exception as e:
            # aiohttp may raise other errors on disconnect; avoid noisy tracebacks
            logger.debug("WebSocket session ended: %s", e)
        finally:
            self.websocket_clients.discard(ws)
            logger.info(
                f"WebSocket client disconnected. Total clients: {len(self.websocket_clients)}"
            )

        return ws

    async def _handle_websocket_message(self, ws, data: Dict[str, Any]) -> None:
        """Handle WebSocket messages."""
        message_type = data.get("type")

        if message_type == "ping":
            await ws.send_str(json.dumps({"type": "pong"}))
        elif message_type == "subscribe":
            # Handle subscription to specific data types
            subscription = data.get("subscription")
            if subscription == "alerts":
                # Send current alerts
                alerts = await self._get_current_alerts()
                await ws.send_str(json.dumps({"type": "alerts_update", "data": alerts}))
        # Add more message types as needed

    async def _get_current_alerts(self) -> List[Dict[str, Any]]:
        """Get current alerts for WebSocket updates."""
        try:
            active_alerts = self.app.state.get("active_alerts", [])
            alerts_data = []

            for alert_id in active_alerts:
                alert_data = self.app.state.get("last_alerts", {}).get(alert_id)
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

        # Ensure status_update payload is JSON-serializable (same as API response)
        payload = data
        if update_type == "status_update" and isinstance(data, dict):
            payload = dict(data)
            if "asterisk_nodes" in payload:
                payload["asterisk_nodes"] = self._serialize_asterisk_nodes(
                    payload.get("asterisk_nodes", [])
                )

        # Helper function to serialize datetime and path-like objects
        def json_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if hasattr(obj, "__fspath__"):
                return str(obj)
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            raise TypeError(f"Type {type(obj)} not serializable")

        try:
            message = json.dumps(
                {
                    "type": update_type,
                    "data": payload,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                default=json_serializer,
            )
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize WebSocket message: {e}")
            logger.debug(f"Data type: {type(data)}, Data: {data}")
            return  # Skip sending if we can't serialize

        # Send to all connected clients
        disconnected = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_str(message)
            except ConnectionClosed:
                disconnected.add(ws)
            except Exception as e:
                logger.debug("WebSocket send failed, removing client: %s", e)
                disconnected.add(ws)

        # Remove disconnected clients
        self.websocket_clients -= disconnected

    async def broadcast_poll_updates(self, status: Dict[str, Any]) -> None:
        """After a successful NWS poll: status plus full alert list for live dashboard cards."""
        await self.broadcast_update("status_update", status)
        alerts = await self._get_current_alerts()
        await self.broadcast_update("alerts_update", alerts)
