"""Tests for Debian postinst base_path migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts/debian/migrate_config_base_path.py"
)
_spec = importlib.util.spec_from_file_location("migrate_config_base_path", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
migrate_config = _mod.migrate_config
needs_migration = _mod.needs_migration


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("", True),
        ("   ", True),
        ("/skywarnplus-ng", False),
        ("/custom", False),
    ],
)
def test_needs_migration(value: object, expected: bool) -> None:
    assert needs_migration(value) is expected


def test_migrate_config_sets_missing_base_path(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    proxy = tmp_path / "skywarnplus-ng-proxy.conf"
    proxy.write_text("# proxy\n")
    config.write_text(
        "monitoring:\n"
        "  http_server:\n"
        "    port: 8100\n"
    )

    assert migrate_config(config, apache_proxy_conf=proxy) is True
    assert 'base_path: /skywarnplus-ng' in config.read_text()


def test_migrate_config_sets_empty_base_path(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    proxy = tmp_path / "skywarnplus-ng-proxy.conf"
    proxy.write_text("# proxy\n")
    config.write_text(
        "monitoring:\n"
        "  http_server:\n"
        "    base_path: \"\"\n"
        "    port: 8100\n"
    )

    assert migrate_config(config, apache_proxy_conf=proxy) is True
    text = config.read_text()
    assert 'base_path: /skywarnplus-ng' in text or 'base_path: "/skywarnplus-ng"' in text


def test_migrate_config_noop_when_base_path_set(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    proxy = tmp_path / "skywarnplus-ng-proxy.conf"
    proxy.write_text("# proxy\n")
    original = (
        "monitoring:\n"
        "  http_server:\n"
        "    base_path: \"/custom\"\n"
    )
    config.write_text(original)

    assert migrate_config(config, apache_proxy_conf=proxy) is False
    assert config.read_text() == original


def test_migrate_config_skips_without_apache_proxy(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("monitoring:\n  http_server:\n    port: 8100\n")

    assert migrate_config(config, apache_proxy_conf=tmp_path / "missing.conf") is False
