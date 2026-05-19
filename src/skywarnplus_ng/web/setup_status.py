"""
Whether the operator has finished initial dashboard setup (for hiding first-run UI).
"""

from __future__ import annotations

from typing import Callable, Optional

from ..core.config import AppConfig
from .auth_security import uses_default_dashboard_password


def has_enabled_counties(config: AppConfig) -> bool:
    """True when at least one county is enabled with a non-empty FIPS code."""
    for county in config.counties:
        if county.enabled and str(county.code or "").strip():
            return True
    return False


def is_dashboard_configured(
    config: AppConfig,
    verify_password: Optional[Callable[[str, str], bool]] = None,
) -> bool:
    """
    Return True when initial dashboard setup is complete.

    Explicit ``dashboard_setup_complete`` is set on the first successful configuration
    save. For older installs without that flag, infer completion when counties are
    configured and the dashboard password is no longer the factory default (when auth
    is enabled).
    """
    if config.dashboard_setup_complete:
        return True

    if not has_enabled_counties(config):
        return False

    auth = config.monitoring.http_server.auth
    if auth.enabled and verify_password is not None:
        if uses_default_dashboard_password(verify_password, auth.password):
            return False

    # Counties present and auth OK — existing node configured before the flag existed.
    return True


def configuration_setup_hints_needed(
    config: AppConfig,
    verify_password: Optional[Callable[[str, str], bool]] = None,
) -> bool:
    """Inverse of is_dashboard_configured for UI that should hide when setup is done."""
    return not is_dashboard_configured(config, verify_password)
