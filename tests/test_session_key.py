"""Dashboard session key persists across restarts when not configured."""

import stat
from unittest.mock import MagicMock

import pytest

pytest.importorskip("aiohttp")

from skywarnplus_ng.core.config import AppConfig, NWSApiConfig  # noqa: E402
from skywarnplus_ng.web.server import (  # noqa: E402
    SESSION_KEY_FILENAME,
    WebDashboard,
    load_or_create_session_key,
)


def _config(tmp_path, secret_key=None) -> AppConfig:
    config = AppConfig(nws=NWSApiConfig(user_agent="test"), data_dir=tmp_path / "data")
    config.monitoring.http_server.auth.secret_key = secret_key
    return config


def test_key_file_created_with_private_mode(tmp_path):
    path = tmp_path / "data" / SESSION_KEY_FILENAME
    key = load_or_create_session_key(path)
    assert len(bytes.fromhex(key)) == 32
    assert path.read_text(encoding="utf-8").strip() == key
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_or_create_session_key(path) == key


def test_invalid_key_file_is_replaced(tmp_path):
    path = tmp_path / SESSION_KEY_FILENAME
    path.write_text("not-hex\n", encoding="utf-8")
    key = load_or_create_session_key(path)
    assert len(bytes.fromhex(key)) == 32
    assert path.read_text(encoding="utf-8").strip() == key


def test_dashboard_reuses_key_across_restarts(tmp_path):
    first = WebDashboard(MagicMock(), _config(tmp_path))
    second = WebDashboard(MagicMock(), _config(tmp_path))
    key = first.config.monitoring.http_server.auth.secret_key
    assert key == second.config.monitoring.http_server.auth.secret_key
    assert (tmp_path / "data" / SESSION_KEY_FILENAME).exists()


def test_configured_key_is_not_overridden(tmp_path):
    configured = "ab" * 32
    dashboard = WebDashboard(MagicMock(), _config(tmp_path, configured))
    assert dashboard.config.monitoring.http_server.auth.secret_key == configured
    assert not (tmp_path / "data" / SESSION_KEY_FILENAME).exists()


def test_unwritable_data_dir_falls_back_to_ephemeral_key(tmp_path, monkeypatch):
    def boom(self):
        raise PermissionError("read-only")

    monkeypatch.setattr(WebDashboard, "_get_data_dir", boom)
    dashboard = WebDashboard(MagicMock(), _config(tmp_path))
    assert len(bytes.fromhex(dashboard.config.monitoring.http_server.auth.secret_key)) == 32


def test_invalid_configured_key_uses_persisted_key(tmp_path):
    persisted = load_or_create_session_key(tmp_path / "data" / SESSION_KEY_FILENAME)
    dashboard = WebDashboard(MagicMock(), _config(tmp_path, "short"))
    from aiohttp import web

    dashboard._configure_dashboard_app(web.Application(), "", "")
    assert dashboard.config.monitoring.http_server.auth.secret_key == persisted
