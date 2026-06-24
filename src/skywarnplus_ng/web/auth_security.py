"""
Dashboard authentication helpers (password policy, backup path validation).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, FrozenSet, Optional, Tuple

DEFAULT_DASHBOARD_PASSWORD = "skywarn123"

# Dashboard pages anyone may view (read-only operational status).
_PUBLIC_PAGES: FrozenSet[str] = frozenset(
    {
        "/",
        "/dashboard",
        "/alerts",
        "/alerts/history",
        "/health",
        "/metrics",
        "/activity",
    }
)

# GET /api/* routes needed by public dashboard pages (no credentials or PII).
_PUBLIC_GET_API_EXACT: FrozenSet[str] = frozenset(
    {
        "/api/status",
        "/api/alerts",
        "/api/alerts/history",
        "/api/health",
        "/api/health/history",
        "/api/metrics",
        "/api/activity",
        "/api/update-status",
    }
)

# Page prefixes that always require a session (even for GET).
_SENSITIVE_PAGE_PREFIXES: Tuple[str, ...] = ("/configuration", "/logs", "/database")

# API prefixes that always require a session (read or write).
_SENSITIVE_API_PREFIXES: Tuple[str, ...] = (
    "/api/config",
    "/api/logs",
    "/api/database",
    "/api/notifications",
    "/api/tts",
    "/api/counties",
)


def strip_base_path(path: str, base_path: str = "") -> str:
    """Remove a configured reverse-proxy prefix so routes and auth rules match."""
    prefix = (base_path or "").rstrip("/")
    if not prefix:
        return path or ""
    current = path or ""
    if current == prefix:
        return "/"
    if current.startswith(prefix + "/"):
        return current[len(prefix) :] or "/"
    return current


def external_path_for_request(path: str, url_prefix: str = "") -> str:
    """Browser-facing path for redirects (adds mount prefix when the request used it)."""
    prefix = (url_prefix or "").rstrip("/")
    current = path or "/"
    if prefix and not current.startswith(prefix):
        return f"{prefix}{current if current.startswith('/') else '/' + current}"
    return current


def path_requires_auth(
    path: str,
    method: str,
    *,
    auth_enabled: bool,
    public_status_api: bool = True,
    base_path: str = "",
) -> bool:
    """
    Return True when unauthenticated requests must be rejected.

    With auth enabled, public users may view operational dashboard pages and their
    read-only APIs (active and past alerts, health, metrics). Configuration, logs,
    database, subscriber data, and all mutating requests require a session.
    GET /api/status stays public for supermon-ng when ``public_status_api`` is True.
    """
    if not auth_enabled:
        return False

    path = strip_base_path(path or "", base_path) if base_path else (path or "")
    method = method.upper()

    if path.startswith("/static"):
        return False
    if path == "/login" or path.startswith("/api/auth/"):
        return False
    if path == "/ws":
        return False

    if path.startswith(_SENSITIVE_PAGE_PREFIXES):
        return True
    if path.startswith(_SENSITIVE_API_PREFIXES):
        return True

    if method in ("POST", "PUT", "DELETE", "PATCH"):
        return True

    if method == "GET":
        if path in _PUBLIC_PAGES:
            return False
        if path in _PUBLIC_GET_API_EXACT:
            if path == "/api/status" and not public_status_api:
                return True
            return False
        if path.startswith("/api/alerts/") and path.endswith("/audio"):
            return False

    return True


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
