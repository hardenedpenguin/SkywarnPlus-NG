"""Tests for dashboard auth security helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from skywarnplus_ng.web.auth_security import (
    DEFAULT_DASHBOARD_PASSWORD,
    incoming_sets_non_default_password,
    resolve_config_backup_path,
    uses_default_dashboard_password,
)


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
