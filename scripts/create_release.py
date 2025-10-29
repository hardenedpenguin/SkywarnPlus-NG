#!/usr/bin/env python3
"""
Create a release tarball for SkywarnPlus-NG

This script creates a production-ready tarball with all necessary files
for deployment on target systems.
"""

import os
import sys
import tarfile
import shutil
from pathlib import Path
from datetime import datetime


def create_release():
    """Create a release tarball."""
    # Get version from pyproject.toml
    version = "3.0.0"  # Default version
    try:
        with open("pyproject.toml", "r") as f:
            for line in f:
                if line.strip().startswith("version ="):
                    version = line.split("=")[1].strip().strip('"')
                    break
    except Exception as e:
        print(f"Warning: Could not read version from pyproject.toml: {e}")
    
    release_name = f"skywarnplus-ng-{version}"
    tarball_name = f"{release_name}.tar.gz"
    
    print(f"Creating release: {release_name}")
    print("=" * 50)
    
    # Remove existing release directory and tarball
    if os.path.exists(release_name):
        shutil.rmtree(release_name)
    if os.path.exists(tarball_name):
        os.remove(tarball_name)
    
    # Create release directory
    print("Creating release directory...")
    os.makedirs(release_name, exist_ok=True)
    
    # Copy source files
    print("Copying source files...")
    shutil.copytree("src", f"{release_name}/src")
    shutil.copytree("config", f"{release_name}/config")
    shutil.copytree("SOUNDS", f"{release_name}/SOUNDS")
    
    # Copy configuration and documentation files
    files_to_copy = [
        "pyproject.toml",
        "README.md",
        "SERVER_DEPLOYMENT.md",
        "SKYDESCRIBE.md",
        "NWS_CLIENT_README.md",
        "install.sh",
        "restart.sh"
    ]
    
    for file in files_to_copy:
        if os.path.exists(file):
            shutil.copy2(file, f"{release_name}/{file}")
            print(f"  ✅ {file}")
        else:
            print(f"  ⚠️  {file} (not found)")
    
    # Copy scripts directory
    if os.path.exists("scripts"):
        shutil.copytree("scripts", f"{release_name}/scripts")
        print("  ✅ scripts/")
    
    # Make scripts executable
    print("Setting script permissions...")
    for root, dirs, files in os.walk(release_name):
        for file in files:
            if file.endswith(('.sh', '.py')):
                file_path = os.path.join(root, file)
                os.chmod(file_path, 0o755)
                print(f"  ✅ {file}")
    
    # Create tarball
    print(f"Creating tarball: {tarball_name}")
    with tarfile.open(tarball_name, "w:gz") as tar:
        tar.add(release_name, arcname=release_name)
    
    # Clean up release directory
    print("Cleaning up...")
    shutil.rmtree(release_name)
    
    # Show results
    print("\nRelease created successfully!")
    print("=" * 30)
    print(f"Tarball: {tarball_name}")
    print(f"Size: {os.path.getsize(tarball_name) / 1024 / 1024:.1f} MB")
    print(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("To install on target system:")
    print(f"  tar -xzf {tarball_name}")
    print(f"  cd {release_name}")
    print("  ./install.sh")
    print()
    print("The installation script will:")
    print("  - Install system dependencies")
    print("  - Create Python virtual environment")
    print("  - Install SkywarnPlus-NG and dependencies")
    print("  - Set up required directories")
    print("  - Start the web dashboard on port 8100")


if __name__ == "__main__":
    try:
        create_release()
    except KeyboardInterrupt:
        print("\nRelease creation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError creating release: {e}")
        sys.exit(1)
