"""
Helpers for dashboard configuration load/save (merge, paths, API redaction).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from ..core.config import AppConfig


def resolve_config_path(config: AppConfig) -> Path:
    """Resolve the on-disk config file path (matches skycontrol / api save)."""
    config_path = config.config_file
    if not config_path.is_absolute():
        config_path = Path("/etc/skywarnplus-ng") / config_path
    return config_path


def model_dump_for_merge(config: AppConfig) -> dict[str, Any]:
    """JSON-friendly model dump for deep merge (Path -> str)."""

    def convert_paths(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: convert_paths(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert_paths(item) for item in obj]
        if hasattr(obj, "__fspath__"):
            return str(obj)
        return obj

    return convert_paths(config.model_dump())


def deep_merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overlay into base; overlay values win at leaves."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def redact_config_for_api(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Remove secrets from config dict returned to the browser."""
    out = copy.deepcopy(config_dict)
    try:
        mon = out.get("monitoring")
        if isinstance(mon, dict):
            http = mon.get("http_server")
            if isinstance(http, dict):
                auth = http.get("auth")
                if isinstance(auth, dict):
                    if auth.get("password"):
                        auth["password"] = ""
                    if auth.get("secret_key"):
                        auth["secret_key"] = ""
    except Exception:
        pass
    try:
        push = out.get("pushover")
        if isinstance(push, dict):
            if push.get("api_token"):
                push["api_token"] = ""
            if push.get("user_key"):
                push["user_key"] = ""
    except Exception:
        pass
    return out
