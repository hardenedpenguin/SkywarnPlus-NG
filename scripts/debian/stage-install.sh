#!/bin/bash
# Stage filesystem tree for the main skywarnplus-ng binary package.
set -euo pipefail

VENV_SRC="${1:?usage: stage-install.sh <venv-dir> <debian-staging-dir>}"
PKG_DIR="${2:?usage: stage-install.sh <venv-dir> <debian-staging-dir>}"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

rm -rf "${PKG_DIR}"
mkdir -p "${PKG_DIR}"

install -d -m 755 "${PKG_DIR}/var/lib/skywarnplus-ng"
cp -a "${VENV_SRC}" "${PKG_DIR}/var/lib/skywarnplus-ng/venv"

if [[ -d "${PROJECT_ROOT}/SOUNDS" ]]; then
  cp -a "${PROJECT_ROOT}/SOUNDS" "${PKG_DIR}/var/lib/skywarnplus-ng/"
fi

if [[ -d "${PROJECT_ROOT}/scripts" ]]; then
  install -d -m 755 "${PKG_DIR}/var/lib/skywarnplus-ng/scripts"
  cp -a "${PROJECT_ROOT}/scripts/." "${PKG_DIR}/var/lib/skywarnplus-ng/scripts/"
  find "${PKG_DIR}/var/lib/skywarnplus-ng/scripts" -type f \( -name '*.py' -o -name '*.sh' \) -exec chmod 755 {} +
fi

install -d -m 755 "${PKG_DIR}/etc/skywarnplus-ng"
install -m 644 "${PROJECT_ROOT}/config/default.yaml" "${PKG_DIR}/etc/skywarnplus-ng/config.yaml.example"

install -d -m 755 "${PKG_DIR}/etc/apache2/conf-available"
install -m 644 "${PROJECT_ROOT}/config/apache/skywarnplus-ng-proxy.conf" \
  "${PKG_DIR}/etc/apache2/conf-available/skywarnplus-ng-proxy.conf"

install -d -m 755 "${PKG_DIR}/usr/share/doc/skywarnplus-ng"
install -m 644 "${PROJECT_ROOT}/README.md" "${PKG_DIR}/usr/share/doc/skywarnplus-ng/README.md"
install -m 644 "${PROJECT_ROOT}/CountyCodes.md" "${PKG_DIR}/usr/share/doc/skywarnplus-ng/CountyCodes.md"
install -m 644 "${PROJECT_ROOT}/LICENSE" "${PKG_DIR}/usr/share/doc/skywarnplus-ng/LICENSE"
if [[ -f "${PROJECT_ROOT}/docs/debian.md" ]]; then
  install -m 644 "${PROJECT_ROOT}/docs/debian.md" "${PKG_DIR}/usr/share/doc/skywarnplus-ng/debian.md"
fi

echo "Staged main package under ${PKG_DIR}"
