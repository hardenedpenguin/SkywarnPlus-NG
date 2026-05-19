"""Tests for dashboard setup / configured detection."""

from __future__ import annotations

from skywarnplus_ng.core.config import (
    AppConfig,
    AuthConfig,
    CountyConfig,
    HttpServerConfig,
    MonitoringConfig,
)
from skywarnplus_ng.web.auth_security import DEFAULT_DASHBOARD_PASSWORD
from skywarnplus_ng.web.setup_status import is_dashboard_configured


def _config(**kwargs) -> AppConfig:
    return AppConfig(**kwargs)


def test_not_configured_without_counties() -> None:
    assert not is_dashboard_configured(_config())


def test_configured_when_flag_set() -> None:
    cfg = _config(dashboard_setup_complete=True)
    assert is_dashboard_configured(cfg, lambda a, b: a == b)


def test_not_configured_fresh_install_with_default_password() -> None:
    cfg = _config(
        counties=[CountyConfig(code="TXC039", name="Brazoria", enabled=True)],
        monitoring=MonitoringConfig(
            http_server=HttpServerConfig(
                auth=AuthConfig(enabled=True, password=DEFAULT_DASHBOARD_PASSWORD)
            )
        ),
    )
    assert not is_dashboard_configured(cfg, lambda a, b: a == b)


def test_legacy_configured_with_counties_and_custom_password() -> None:
    cfg = _config(
        counties=[CountyConfig(code="TXC001", name="Mine", enabled=True)],
        monitoring=MonitoringConfig(
            http_server=HttpServerConfig(auth=AuthConfig(enabled=True, password="not-the-default"))
        ),
    )
    assert is_dashboard_configured(cfg, lambda a, b: a == b)
