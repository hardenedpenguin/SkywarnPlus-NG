#!/usr/bin/env python3
"""Ensure debian/changelog top version matches pyproject.toml (Debian revision -1)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "debian" / "changelog"
PYPROJECT = ROOT / "pyproject.toml"


def read_upstream_version() -> str:
    if tomllib is None:
        for line in PYPROJECT.read_text().splitlines():
            if line.strip().startswith("version ="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
        raise SystemExit("Could not read version from pyproject.toml")
    data = tomllib.loads(PYPROJECT.read_text())
    return str(data["project"]["version"])


def main() -> None:
    upstream = read_upstream_version()
    debian_version = f"{upstream}-1"
    text = CHANGELOG.read_text()
    lines = text.splitlines()
    if not lines:
        raise SystemExit("debian/changelog is empty")

    match = re.match(r"^(\S+) \(([^)]+)\)", lines[0])
    if not match:
        raise SystemExit(f"Could not parse first changelog line: {lines[0]!r}")

    pkg_name, current = match.group(1), match.group(2)
    if current == debian_version:
        print(f"debian/changelog already at {debian_version}")
        return

    lines[0] = f"{pkg_name} ({debian_version}) unstable; urgency=medium"
    CHANGELOG.write_text("\n".join(lines) + "\n")
    print(f"Updated debian/changelog: {current} -> {debian_version}")


if __name__ == "__main__":
    main()
