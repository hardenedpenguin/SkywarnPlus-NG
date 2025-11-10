#!/usr/bin/env python3
"""
Create a release tarball for SkywarnPlus-NG.

The script assembles a reproducible release directory from the repository
contents and bundles it into a gzip-compressed tarball.
"""

from __future__ import annotations

import shutil
import sys
import tarfile
from datetime import datetime
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    tomllib = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_DIRS = ("src", "config")
OPTIONAL_DIRS = ("SOUNDS", "scripts")
BASE_FILES = ("pyproject.toml", "README.md", "CountyCodes.md", "install.sh")


def _read_version(pyproject_path: Path) -> str:
    if not pyproject_path.exists():
        return "0.0.0"

    if tomllib is None:
        # Fallback: best effort by scanning the file to avoid an extra dependency
        for line in pyproject_path.read_text().splitlines():
            clean = line.strip()
            if clean.startswith("version ="):
                return clean.split("=", maxsplit=1)[1].strip().strip('"').strip("'")
        return "0.0.0"

    try:
        data = tomllib.loads(pyproject_path.read_text())
        return data.get("project", {}).get("version", "0.0.0")
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Warning: could not parse version from {pyproject_path}: {exc}")
        return "0.0.0"


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    shutil.copytree(source, destination)


def _copy_files(files: tuple[str, ...], destination: Path) -> None:
    for name in files:
        src = PROJECT_ROOT / name
        if src.exists():
            shutil.copy2(src, destination / name)
            print(f"  ✅ {name}")


def _set_script_permissions(release_dir: Path) -> None:
    for path in release_dir.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".sh"}:
            path.chmod(0o755)


def create_release() -> None:
    version = _read_version(PROJECT_ROOT / "pyproject.toml")
    release_name = f"skywarnplus-ng-{version}"
    release_dir = PROJECT_ROOT / release_name
    tarball_path = PROJECT_ROOT / f"{release_name}.tar.gz"

    print(f"Creating release: {release_name}")
    print("=" * 50)

    shutil.rmtree(release_dir, ignore_errors=True)
    tarball_path.unlink(missing_ok=True)

    print("Creating release directory...")
    release_dir.mkdir(parents=True, exist_ok=True)

    print("Copying source directories...")
    for directory in REQUIRED_DIRS:
        _copy_tree(PROJECT_ROOT / directory, release_dir / directory)

    for directory in OPTIONAL_DIRS:
        _copy_tree(PROJECT_ROOT / directory, release_dir / directory)

    print("Copying metadata files...")
    _copy_files(BASE_FILES, release_dir)

    print("Setting script permissions...")
    _set_script_permissions(release_dir)

    print(f"Creating tarball: {tarball_path.name}")
    with tarfile.open(tarball_path, "w:gz") as tar:
        tar.add(release_dir, arcname=release_name)

    print("Cleaning up staging directory...")
    shutil.rmtree(release_dir)

    print("\nRelease created successfully!")
    print("=" * 30)
    size_mb = tarball_path.stat().st_size / 1024 / 1024
    print(f"Tarball: {tarball_path.name}")
    print(f"Size: {size_mb:.1f} MB")
    print(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("To install on target system:")
    print(f"  tar -xzf {tarball_path.name}")
    print(f"  cd {release_name}")
    print("  ./install.sh")


if __name__ == "__main__":
    try:
        create_release()
    except KeyboardInterrupt:
        print("\nRelease creation cancelled by user")
        sys.exit(1)
    except Exception as exc:
        print(f"\nError creating release: {exc}")
        sys.exit(1)
