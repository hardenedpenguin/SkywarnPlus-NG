"""
Status API handler mixin.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from aiohttp import web
from aiohttp.web import Request, Response

from ..setup_status import is_dashboard_configured

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class StatusApiMixin:
    async def api_status_handler(self, request: Request) -> Response:
        """Handle API status endpoint."""
        try:
            status = self.app.get_status()

            # Get active alerts for Supermon compatibility
            active_alerts = self.app.state.get("active_alerts", [])
            alerts_data = []

            # Build county code to name mapping for concise display
            county_code_to_name = {}
            if self.app and hasattr(self.app, "config"):
                county_code_to_name = {
                    county.code: county.name
                    for county in self.app.config.counties
                    if county.enabled and county.name
                }
            mobile_service = getattr(self.app, "mobile_county_service", None)
            if mobile_service and mobile_service.is_gps_active():
                gps_code = mobile_service.active_gps_county_code
                gps_name = mobile_service.active_gps_county_name
                if gps_code and gps_name:
                    county_code_to_name[gps_code] = gps_name

            # Build county_name_to_code once (used for area_desc matching)
            county_name_to_code = {}
            if self.app and hasattr(self.app, "config"):
                for county in self.app.config.counties:
                    if county.enabled and county.name:
                        normalized_name = (
                            county.name.replace(" County", "").replace(" county", "").lower()
                        )
                        county_name_to_code[normalized_name] = county.code
                        base_name = re.sub(
                            r"\s+(island|islands|peninsula|beach|beaches)\s*$",
                            "",
                            normalized_name,
                            flags=re.IGNORECASE,
                        )
                        if base_name != normalized_name:
                            county_name_to_code[base_name] = county.code

            def format_event_with_counties(
                event: str, county_codes: list, area_desc: str = None
            ) -> str:
                """Format event name with concise county information."""
                try:
                    if not county_codes or not isinstance(county_codes, list):
                        return event
                    county_names = []
                    for code in county_codes:
                        if not code:
                            continue
                        if code in county_code_to_name and county_code_to_name[code]:
                            name = (
                                str(county_code_to_name[code])
                                .replace(" County", "")
                                .replace(" county", "")
                            )
                            if name:
                                county_names.append(name)
                        else:
                            county_names.append(str(code))
                    if not county_names:
                        return event
                    if len(county_names) == 1:
                        return f"{event} ({county_names[0]})"
                    elif len(county_names) == 2:
                        return f"{event} ({', '.join(county_names)})"
                    elif len(county_names) <= 4:
                        return f"{event} ({', '.join(county_names[:3])}, +{len(county_names) - 3} more)"
                    else:
                        return f"{event} ({len(county_names)} counties)"
                except Exception as e:
                    logger.warning(f"Error formatting event with counties: {e}")
                    return event

            def build_alerts_data(allowed_county_codes: Optional[Set[str]]) -> List[Dict[str, Any]]:
                """Build alerts list filtered to counties allowed for this context (node or global)."""
                allowed = (
                    allowed_county_codes
                    if allowed_county_codes is not None
                    else set(county_code_to_name.keys())
                )
                result = []
                for alert_id in active_alerts:
                    try:
                        alert_data = self.app.state.get("last_alerts", {}).get(alert_id)
                        if not alert_data:
                            continue
                        all_county_codes = alert_data.get("county_codes", [])
                        if not isinstance(all_county_codes, list):
                            all_county_codes = []
                        county_codes = [c for c in all_county_codes if c in county_code_to_name]
                        area_desc = alert_data.get("area_desc", "")
                        if not county_codes and area_desc and county_name_to_code:
                            area_parts = [p.strip() for p in re.split(r"[;,]", area_desc)]
                            matched_codes = []
                            for area_part in area_parts:
                                normalized_area = (
                                    re.sub(
                                        r"\s+(island|islands|peninsula|beach|beaches|county)\s*$",
                                        "",
                                        area_part,
                                        flags=re.IGNORECASE,
                                    )
                                    .lower()
                                    .strip()
                                )
                                if normalized_area in county_name_to_code:
                                    code = county_name_to_code[normalized_area]
                                    if code not in matched_codes:
                                        matched_codes.append(code)
                                else:
                                    for county_name, code in county_name_to_code.items():
                                        if (
                                            county_name in normalized_area
                                            or normalized_area in county_name
                                        ):
                                            if code not in matched_codes:
                                                matched_codes.append(code)
                            if matched_codes:
                                county_codes = matched_codes
                        # Restrict to allowed counties (per-node or global)
                        overlap = [c for c in county_codes if c in allowed]
                        if not overlap:
                            continue
                        event = alert_data.get("event", "Unknown")
                        formatted_event = format_event_with_counties(event, overlap, area_desc)
                        result.append(
                            {
                                "event": formatted_event,
                                "severity": alert_data.get("severity", "Unknown"),
                                "headline": (
                                    alert_data.get("headline")
                                    or alert_data.get("description")
                                    or "No headline"
                                )[:100],
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Error processing alert {alert_id} for status: {e}")
                        continue
                return result

            # Global alerts (all enabled counties) – backward compatible
            alerts_data = build_alerts_data(None)
            status["has_alerts"] = len(alerts_data) > 0
            status["alerts"] = alerts_data

            # Per-node alerts for Supermon (per-node counties)
            alerts_by_node: Dict[str, Dict[str, Any]] = {}
            if self.app and hasattr(self.app, "config") and self.app.config.asterisk.enabled:
                for node in self.app.config.asterisk.get_nodes_list():
                    if mobile_service:
                        effective = mobile_service.get_effective_counties_for_node(node)
                        allowed = (
                            effective if effective is not None else set(county_code_to_name.keys())
                        )
                    else:
                        node_counties = self.app.config.asterisk.get_counties_for_node(node)
                        allowed = (
                            set(node_counties) if node_counties else set(county_code_to_name.keys())
                        )
                    node_alerts = build_alerts_data(allowed)
                    node_entry: Dict[str, Any] = {
                        "has_alerts": len(node_alerts) > 0,
                        "alerts": node_alerts,
                        "effective_counties": sorted(allowed) if allowed else [],
                    }
                    if mobile_service and mobile_service.get_gps_controlled_node() == node:
                        node_entry["gps"] = {
                            "active": mobile_service.is_gps_active(),
                            "county_code": mobile_service.active_gps_county_code,
                            "county_name": mobile_service.active_gps_county_name,
                            "gps_only": mobile_service.is_gps_only_node(node),
                        }
                    alerts_by_node[str(node)] = node_entry

            # Supermon compatibility: ?nodes=546051,546055,546056 requests status for specific nodes.
            # Ensure every requested node has an alerts_by_node entry (use per-node data if available,
            # otherwise global alerts). This fixes "doesn't return properly for all configured nodes".
            nodes_param = request.query.get("nodes", "").strip()
            if nodes_param:
                requested = [
                    str(n).strip() for n in nodes_param.split(",") if n and str(n).strip().isdigit()
                ]
                global_alerts = build_alerts_data(None)
                global_entry = {"has_alerts": len(global_alerts) > 0, "alerts": global_alerts}
                for node_key in requested:
                    if node_key and node_key not in alerts_by_node:
                        alerts_by_node[node_key] = global_entry

            status["alerts_by_node"] = alerts_by_node

            if mobile_service:
                status["gps"] = mobile_service.get_status()

            # Ensure asterisk_nodes is JSON-serializable (int | NodeConfig -> int | dict)
            status["asterisk_nodes"] = self._serialize_asterisk_nodes(
                status.get("asterisk_nodes", [])
            )

            # Convert datetime/path in status to JSON-friendly types
            def _json_friendly(obj):
                if hasattr(obj, "isoformat"):
                    return obj.isoformat()
                if hasattr(obj, "__fspath__"):
                    return str(obj)
                return obj

            for key in ("last_poll", "last_all_clear", "nws_last_error_at", "nhc_last_error_at"):
                if key in status and status[key] is not None:
                    status[key] = _json_friendly(status[key])

            status["is_configured"] = is_dashboard_configured(self.config, self._verify_password)

            return web.json_response(status)
        except (TypeError, ValueError, KeyError, AttributeError) as e:
            logger.error(f"Error building status response: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
        except Exception as e:
            logger.error(f"Error getting status: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
