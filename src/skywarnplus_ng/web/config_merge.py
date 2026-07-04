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


def is_blank_secret(value: Any) -> bool:
    """True when a secret field is missing or empty (UI redaction / leave-blank)."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def preserve_blank_notification_secrets(data: dict[str, Any], config: AppConfig) -> None:
    """Keep stored notification secrets when the browser sends blank values.

    Secrets are redacted to empty strings in GET /api/config. Without this,
    a save after load would wipe email/SMS/FCM credentials on disk.
    """
    notifications = data.get("notifications")
    if not isinstance(notifications, dict):
        return

    email = notifications.get("email")
    if isinstance(email, dict) and "password" in email and is_blank_secret(email.get("password")):
        email["password"] = config.notifications.email.password

    push = notifications.get("push")
    if (
        isinstance(push, dict)
        and "fcm_server_key" in push
        and is_blank_secret(push.get("fcm_server_key"))
    ):
        push["fcm_server_key"] = config.notifications.push.fcm_server_key

    sms = notifications.get("sms")
    if isinstance(sms, dict) and "auth_token" in sms and is_blank_secret(sms.get("auth_token")):
        sms["auth_token"] = config.notifications.sms.auth_token


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
    try:
        notifications = out.get("notifications")
        if isinstance(notifications, dict):
            email = notifications.get("email")
            if isinstance(email, dict) and email.get("password"):
                email["password"] = ""
            push_cfg = notifications.get("push")
            if isinstance(push_cfg, dict) and push_cfg.get("fcm_server_key"):
                push_cfg["fcm_server_key"] = ""
            sms_cfg = notifications.get("sms")
            if isinstance(sms_cfg, dict) and sms_cfg.get("auth_token"):
                sms_cfg["auth_token"] = ""
    except Exception:
        pass
    return out
