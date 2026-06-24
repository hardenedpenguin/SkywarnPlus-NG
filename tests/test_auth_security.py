"""Tests for dashboard auth security helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from skywarnplus_ng.web.auth_security import (
    DEFAULT_DASHBOARD_PASSWORD,
    external_path_for_request,
    incoming_sets_non_default_password,
    path_requires_auth,
    resolve_config_backup_path,
    strip_base_path,
    uses_default_dashboard_password,
)


def test_path_requires_auth_disabled() -> None:
    assert not path_requires_auth("/api/config", "GET", auth_enabled=False)


def test_path_requires_auth_protects_sensitive_routes() -> None:
    assert path_requires_auth("/configuration", "GET", auth_enabled=True)
    assert path_requires_auth("/logs", "GET", auth_enabled=True)
    assert path_requires_auth("/database", "GET", auth_enabled=True)
    assert path_requires_auth("/api/config", "GET", auth_enabled=True)
    assert path_requires_auth("/api/logs", "GET", auth_enabled=True)
    assert path_requires_auth("/api/notifications/subscribers", "GET", auth_enabled=True)
    assert path_requires_auth("/api/alerts", "POST", auth_enabled=True)


def test_path_requires_auth_public_dashboard_read_only() -> None:
    assert not path_requires_auth("/", "GET", auth_enabled=True)
    assert not path_requires_auth("/dashboard", "GET", auth_enabled=True)
    assert not path_requires_auth("/alerts", "GET", auth_enabled=True)
    assert not path_requires_auth("/alerts/history", "GET", auth_enabled=True)
    assert not path_requires_auth("/health", "GET", auth_enabled=True)
    assert not path_requires_auth("/metrics", "GET", auth_enabled=True)
    assert not path_requires_auth("/activity", "GET", auth_enabled=True)
    assert not path_requires_auth("/api/alerts", "GET", auth_enabled=True)
    assert not path_requires_auth("/api/health", "GET", auth_enabled=True)
    assert not path_requires_auth("/api/metrics", "GET", auth_enabled=True)
    assert not path_requires_auth("/api/activity", "GET", auth_enabled=True)
    assert not path_requires_auth("/api/update-status", "GET", auth_enabled=True)
    assert not path_requires_auth("/api/alerts/abc123/audio", "GET", auth_enabled=True)
    assert not path_requires_auth("/ws", "GET", auth_enabled=True)


def test_path_requires_auth_public_routes() -> None:
    assert not path_requires_auth("/static/app.js", "GET", auth_enabled=True)
    assert not path_requires_auth("/login", "GET", auth_enabled=True)
    assert not path_requires_auth("/api/auth/login", "POST", auth_enabled=True)
    assert not path_requires_auth("/api/status", "GET", auth_enabled=True)
    assert not path_requires_auth("/api/status", "GET", auth_enabled=True, public_status_api=True)


def test_path_requires_auth_status_can_be_locked() -> None:
    assert path_requires_auth("/api/status", "GET", auth_enabled=True, public_status_api=False)
    assert path_requires_auth("/api/status", "POST", auth_enabled=True)


def test_strip_base_path() -> None:
    assert strip_base_path("/skywarnplus-ng/login", "/skywarnplus-ng") == "/login"
    assert strip_base_path("/skywarnplus-ng", "/skywarnplus-ng") == "/"
    assert strip_base_path("/login", "/skywarnplus-ng") == "/login"


def test_path_requires_auth_with_base_path_prefix() -> None:
    bp = "/skywarnplus-ng"
    assert not path_requires_auth(f"{bp}/login", "GET", auth_enabled=True, base_path=bp)
    assert not path_requires_auth(f"{bp}/alerts/history", "GET", auth_enabled=True, base_path=bp)
    assert not path_requires_auth(f"{bp}/api/alerts/history", "GET", auth_enabled=True, base_path=bp)
    assert path_requires_auth(f"{bp}/configuration", "GET", auth_enabled=True, base_path=bp)


def test_external_path_for_request() -> None:
    assert external_path_for_request("/configuration", "/skywarnplus-ng") == "/skywarnplus-ng/configuration"
    assert external_path_for_request("/login", "") == "/login"


def test_uses_default_dashboard_password_plaintext() -> None:
    assert uses_default_dashboard_password(lambda a, b: a == b, DEFAULT_DASHBOARD_PASSWORD)


def test_incoming_sets_non_default_password() -> None:
    data = {
        "monitoring": {
            "http_server": {
                "auth": {"password": "my-secure-password"},
            }
        }
    }
    assert incoming_sets_non_default_password(data, lambda s: s.startswith("$2"))
    assert not incoming_sets_non_default_password(
        {"monitoring": {"http_server": {"auth": {"password": DEFAULT_DASHBOARD_PASSWORD}}}},
        lambda s: s.startswith("$2"),
    )


def test_resolve_config_backup_path_latest(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("enabled: true\n", encoding="utf-8")
    backup = tmp_path / "config.yaml.backup.20260101-120000"
    backup.write_text("enabled: false\n", encoding="utf-8")
    resolved = resolve_config_backup_path(config)
    assert resolved == backup.resolve()


def test_resolve_config_backup_path_rejects_traversal(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("x: 1\n", encoding="utf-8")
    outside = tmp_path.parent / "evil.yaml.backup.stamp"
    outside.write_text("x: 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="inside the configuration directory"):
        resolve_config_backup_path(config, str(outside))
