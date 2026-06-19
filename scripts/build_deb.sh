#!/bin/bash
# Build skywarnplus-ng .deb package (amd64 or arm64 native builders only).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

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

echo "Building Debian package for ${ARCH}..."
export DEB_BUILD_OPTIONS=nocheck
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
echo "Debian package:"
ls -lh "${OUT_DIR}/"*.deb
echo ""
echo "Install on target node (${ARCH}):"
echo "  sudo apt install ./dist/debs/skywarnplus-ng_*_${ARCH}.deb"
