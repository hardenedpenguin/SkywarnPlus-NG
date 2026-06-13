#!/bin/bash
# Build an embedded virtualenv for the skywarnplus-ng Debian package.
set -euo pipefail

VENV_DIR="${1:?usage: build-venv.sh <venv-output-dir>}"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Debian/CI builds must use distro python3, not actions/setup-python (hostedtoolcache paths break on nodes).
if [[ -z "${PYTHON:-}" && -x /usr/bin/python3 ]]; then
  PYTHON=/usr/bin/python3
else
  PYTHON="${PYTHON:-python3}"
fi

echo "Building virtualenv at ${VENV_DIR} (project: ${PROJECT_ROOT}, python: ${PYTHON})"

rm -rf "${VENV_DIR}"
"${PYTHON}" -m venv "${VENV_DIR}"

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
python -m pip install --upgrade --upgrade-strategy eager "${PROJECT_ROOT}"

# Trim packaging bulk (runtime does not need pip cache or bytecode caches).
find "${VENV_DIR}" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "${VENV_DIR}" -type f -name '*.pyc' -delete 2>/dev/null || true
rm -rf "${VENV_DIR}/lib"/python*/site-packages/pip 2>/dev/null || true
rm -rf "${VENV_DIR}/lib"/python*/site-packages/setuptools 2>/dev/null || true

echo "Virtualenv ready: $("${VENV_DIR}/bin/python" -c 'import skywarnplus_ng; print(skywarnplus_ng.__version__)')"
