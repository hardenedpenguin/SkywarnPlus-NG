"""
Dashboard authentication helpers (password policy, backup path validation).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

DEFAULT_DASHBOARD_PASSWORD = "skywarn123"


def request_is_https(request) -> bool:
    """True when the client connection is HTTPS (direct or via X-Forwarded-Proto)."""
    if getattr(request, "secure", False):
        return True
    forwarded = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    return forwarded == "https"


def uses_default_dashboard_password(
    verify_password: Callable[[str, str], bool], stored: Optional[str]
) -> bool:
    """Return True if stored credentials still match the factory default password."""
    if not stored:
        return False
    return verify_password(DEFAULT_DASHBOARD_PASSWORD, stored)


def incoming_sets_non_default_password(data: dict, is_bcrypt_hash: Callable[[str], bool]) -> bool:
    """True when the save payload sets a new admin password that is not the factory default."""
    try:
        mon = data.get("monitoring")
        if not isinstance(mon, dict):
            return False
        http = mon.get("http_server")
        if not isinstance(http, dict):
            return False
        auth = http.get("auth")
        if not isinstance(auth, dict):
            return False
        pwd = auth.get("password")
        if not isinstance(pwd, str) or not pwd.strip():
            return False
        if is_bcrypt_hash(pwd):
            return False
        return pwd.strip() != DEFAULT_DASHBOARD_PASSWORD
    except Exception:
        return False


def resolve_config_backup_path(config_path: Path, backup_path: Optional[str] = None) -> Path:
    """
    Resolve a configuration backup file under the config directory.

    Raises ValueError when the path escapes the config directory or is not a backup file.
    """
    config_path = config_path.resolve()
    parent = config_path.parent
    prefix = f"{config_path.name}.backup."

    if backup_path:
        candidate = Path(backup_path)
        if not candidate.is_absolute():
            candidate = parent / candidate
        resolved = candidate.resolve()
    else:
        backups = sorted(parent.glob(f"{config_path.name}.backup.*"), reverse=True)
        if not backups:
            raise ValueError("No configuration backup files found")
        resolved = backups[0].resolve()

    try:
        resolved.relative_to(parent)
    except ValueError as e:
        raise ValueError("Backup path must be inside the configuration directory") from e

    if not resolved.is_file():
        raise ValueError("Backup file not found")

    name = resolved.name
    if not (name.startswith(prefix) or name == config_path.name):
        raise ValueError("Path is not a configuration backup file")

    return resolved
