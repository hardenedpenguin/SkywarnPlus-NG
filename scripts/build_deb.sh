#!/bin/bash
# Build skywarnplus-ng .deb package (amd64 or arm64 native builders only).
#
# Usage:
#   ./scripts/build_deb.sh [bookworm|trixie]
#   SKYWARN_DEB_SUITE=bookworm ./scripts/build_deb.sh
#
# Produces suite-specific packages (ASL3 naming):
#   skywarnplus-ng_<ver>-1.deb12_<arch>.deb  — Debian 12 Bookworm (Python 3.11)
#   skywarnplus-ng_<ver>-1.deb13_<arch>.deb  — Debian 13 Trixie (Python 3.13)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

SUITE="${1:-${SKYWARN_DEB_SUITE:-trixie}}"
# shellcheck source=/dev/null
source "${ROOT}/scripts/debian/suite-vars.sh" "${SUITE}"

ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
case "${ARCH}" in
  amd64|arm64) ;;
  x86_64) ARCH=amd64 ;;
  aarch64) ARCH=arm64 ;;
  *)
    echo "Unsupported architecture: ${ARCH} (only amd64 and arm64 are supported)" >&2
    exit 1
    ;;
esac

if ! command -v dpkg-buildpackage >/dev/null 2>&1; then
  echo "Install build tools: sudo apt install devscripts debhelper build-essential" >&2
  exit 1
fi

chmod +x scripts/debian/*.sh debian/rules

python3 scripts/debian/sync-changelog-version.py

UPSTREAM="$(python3 -c "
import re
from pathlib import Path
for line in Path('pyproject.toml').read_text().splitlines():
    if line.strip().startswith('version ='):
        print(re.sub(r'.*=\s*[\"\\']([^\"\\']+)[\"\\'].*', r'\\1', line.strip()))
        break
")"
DEB_PKG_VERSION="${UPSTREAM}-1.${SKYWARN_DEB_TAG}"

CHANGELOG_BAK="$(mktemp)"
cp debian/changelog "${CHANGELOG_BAK}"
restore_changelog() {
  mv -f "${CHANGELOG_BAK}" debian/changelog
}
trap restore_changelog EXIT

sed -i "1s/([^)]*)/(${DEB_PKG_VERSION})/" debian/changelog
"${ROOT}/scripts/debian/prepare-suite.sh" "${SKYWARN_DEB_SUITE}"

echo "Building Debian package for ${ARCH} (${SKYWARN_DEB_SUITE}, Python ${SKYWARN_PYTHON_MINOR})..."
export DEB_BUILD_OPTIONS=nocheck
export SKYWARN_DEB_SUITE SKYWARN_DEB_TAG SKYWARN_PYTHON_MINOR SKYWARN_LIBPYTHON_DEP
dpkg-buildpackage -us -uc -b

OUT_DIR="${ROOT}/dist/debs"
PARENT="$(dirname "${ROOT}")"
mkdir -p "${OUT_DIR}"

shopt -s nullglob
for deb in "${PARENT}"/skywarnplus-ng_*.deb; do
  mv -f "${deb}" "${OUT_DIR}/"
done

if ! compgen -G "${OUT_DIR}/*.deb" >/dev/null; then
  echo "No .deb files produced" >&2
  exit 1
fi

echo ""
echo "Debian package (${SKYWARN_DEB_SUITE}):"
ls -lh "${OUT_DIR}/"*"${SKYWARN_DEB_TAG}"*.deb 2>/dev/null || ls -lh "${OUT_DIR}/"*.deb
echo ""
echo "Install on ${SKYWARN_DEB_SUITE} node (${ARCH}):"
echo "  sudo apt install ./dist/debs/skywarnplus-ng_*_${SKYWARN_DEB_TAG}_${ARCH}.deb"
