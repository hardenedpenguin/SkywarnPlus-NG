"""
Build dashboard/API alert payloads from application state.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Set

from ..core.config import AppConfig


def _county_name_to_code_map(config: AppConfig) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for county in config.counties:
        if not county.enabled or not county.name:
            continue
        normalized_name = county.name.replace(" County", "").replace(" county", "").lower()
        mapping[normalized_name] = county.code
        base_name = re.sub(
            r"\s+(island|islands|peninsula|beach|beaches)\s*$",
            "",
            normalized_name,
            flags=re.IGNORECASE,
        )
        if base_name != normalized_name:
            mapping[base_name] = county.code
    return mapping


def _match_county_codes_from_area(area_desc: str, county_name_to_code: Dict[str, str]) -> List[str]:
    if not area_desc:
        return []
    matched_codes: List[str] = []
    area_parts = [part.strip() for part in re.split(r"[;,]", area_desc)]
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
            continue
        for county_name, code in county_name_to_code.items():
            if county_name in normalized_area or normalized_area in county_name:
                if code not in matched_codes:
                    matched_codes.append(code)
    return matched_codes


def _filter_alert_for_monitored_counties(
    alert_data: Dict[str, Any],
    monitored_county_codes: Set[str],
    config: AppConfig,
) -> Optional[Dict[str, Any]]:
    """Return a copy of alert_data scoped to monitored counties, or None to omit."""
    if not monitored_county_codes:
        return copy.deepcopy(alert_data)

    original_codes = alert_data.get("county_codes", [])
    filtered_codes = [code for code in original_codes if code in monitored_county_codes]

    if not filtered_codes:
        area_desc = alert_data.get("area_desc", "")
        if area_desc:
            filtered_codes = _match_county_codes_from_area(
                area_desc, _county_name_to_code_map(config)
            )
            filtered_codes = [code for code in filtered_codes if code in monitored_county_codes]

    if not filtered_codes:
        return None

    filtered_alert = copy.deepcopy(alert_data)
    filtered_alert["county_codes"] = filtered_codes

    area_desc = filtered_alert.get("area_desc", "")
    if area_desc:
        county_code_to_name = {
            county.code: county.name for county in config.counties if county.enabled and county.name
        }
        area_parts = [part.strip() for part in re.split(r"[;,]", area_desc)]
        filtered_parts: List[str] = []

        for part in area_parts:
            if not part:
                continue
            part_lower = part.lower().strip()
            matched = False
            for code, name in county_code_to_name.items():
                if not name:
                    continue
                name_lower = name.lower().strip()
                if (
                    part_lower == name_lower
                    or part_lower == name_lower.replace(" county", "")
                    or part_lower == name_lower.replace(" county", "").replace(" ", "")
                ):
                    filtered_parts.append(part)
                    matched = True
                    break
            if not matched:
                for code in monitored_county_codes:
                    if code.lower() in part_lower:
                        filtered_parts.append(part)
                        matched = True
                        break

        if filtered_parts:
            filtered_alert["area_desc"] = "; ".join(filtered_parts)
        elif len(filtered_codes) < len(original_codes):
            county_names = [
                county_code_to_name[code] for code in filtered_codes if code in county_code_to_name
            ]
            if county_names:
                filtered_alert["area_desc"] = "; ".join(county_names)

    return filtered_alert


def _enrich_alert_payload(alert_data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    alert_id = alert_data.get("id")
    payload = copy.deepcopy(alert_data)
    last_sayalert = state.get("last_sayalert") or []
    alertscript_alerts = state.get("alertscript_alerts") or []
    payload["announced"] = bool(alert_id and alert_id in last_sayalert)
    payload["script_executed"] = bool(alert_id and alert_id in alertscript_alerts)
    return payload


def build_active_alerts_payload(
    state: Dict[str, Any],
    config: Optional[AppConfig] = None,
) -> List[Dict[str, Any]]:
    """
    Build the active alert list for API and WebSocket clients.

    Uses refreshed ``last_alerts`` snapshots and applies the same county filtering
    and metadata enrichment everywhere the dashboard reads live alerts.
    """
    active_alert_ids = state.get("active_alerts", [])
    last_alerts = state.get("last_alerts", {})
    alerts_data: List[Dict[str, Any]] = []

    monitored_county_codes: Set[str] = set()
    if config is not None:
        monitored_county_codes = {county.code for county in config.counties if county.enabled}

    for alert_id in active_alert_ids:
        raw = last_alerts.get(alert_id) if isinstance(last_alerts, dict) else None
        if not raw:
            continue

        if monitored_county_codes and config is not None:
            filtered = _filter_alert_for_monitored_counties(raw, monitored_county_codes, config)
            if filtered is None:
                continue
            alerts_data.append(_enrich_alert_payload(filtered, state))
        else:
            alerts_data.append(_enrich_alert_payload(raw, state))

    return alerts_data
