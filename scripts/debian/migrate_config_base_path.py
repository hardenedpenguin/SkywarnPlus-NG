#!/usr/bin/env python3
"""Ensure monitoring.http_server.base_path matches the Apache reverse proxy prefix."""

from __future__ import annotations

import sys
from pathlib import Path

from ruamel.yaml import YAML

DEFAULT_BASE_PATH = "/skywarnplus-ng"
APACHE_PROXY_CONF = Path("/etc/apache2/conf-available/skywarnplus-ng-proxy.conf")


def needs_migration(base_path: object) -> bool:
    if base_path is None:
        return True
    if isinstance(base_path, str):
        return base_path.strip() == ""
    return False


def migrate_config(
    config_path: Path,
    *,
    apache_proxy_conf: Path = APACHE_PROXY_CONF,
    default_base_path: str = DEFAULT_BASE_PATH,
) -> bool:
    """Set base_path when missing/empty and the packaged Apache proxy is present."""
    if not config_path.is_file():
        return False
    if not apache_proxy_conf.is_file():
        return False

    yaml = YAML()
    yaml.preserve_quotes = True
    data = yaml.load(config_path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {config_path}")

    monitoring = data.setdefault("monitoring", {})
    if not isinstance(monitoring, dict):
        raise ValueError("monitoring must be a mapping")
    http_server = monitoring.setdefault("http_server", {})
    if not isinstance(http_server, dict):
        raise ValueError("monitoring.http_server must be a mapping")

    if not needs_migration(http_server.get("base_path")):
        return False

    http_server["base_path"] = default_base_path
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.dump(data, handle)
    return True


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: migrate-config-base-path.py <config.yaml> [apache-proxy.conf]", file=sys.stderr)
        return 2

    config_path = Path(args[0])
    apache_proxy_conf = Path(args[1]) if len(args) > 1 else APACHE_PROXY_CONF

    try:
        migrated = migrate_config(config_path, apache_proxy_conf=apache_proxy_conf)
    except (OSError, ValueError) as exc:
        print(f"base_path migration failed: {exc}", file=sys.stderr)
        return 1

    if migrated:
        print(
            f"Set monitoring.http_server.base_path to {DEFAULT_BASE_PATH!r} in {config_path}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
