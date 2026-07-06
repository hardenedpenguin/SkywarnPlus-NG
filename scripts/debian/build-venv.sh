#!/bin/bash
# Build an embedded virtualenv for the skywarnplus-ng Debian package.
set -euo pipefail

VENV_DIR="${1:?usage: build-venv.sh <venv-output-dir>}"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# shellcheck source=/dev/null
source "${PROJECT_ROOT}/scripts/debian/suite-vars.sh" "${SKYWARN_DEB_SUITE:-trixie}"

PY_MINOR="${SKYWARN_PYTHON_MINOR}"
PY_BIN="python${PY_MINOR}"

# Target ASL3 nodes: Python 3.11 on Debian 12 Bookworm, 3.13 on Debian 13 Trixie.
if [[ -z "${PYTHON:-}" ]]; then
  if command -v "${PY_BIN}" >/dev/null 2>&1; then
    PYTHON="$(command -v "${PY_BIN}")"
  elif [[ -n "${pythonLocation:-}" && -x "${pythonLocation}/bin/python3" ]]; then
    PYTHON="${pythonLocation}/bin/python3"
  elif [[ -x "/usr/bin/${PY_BIN}" ]]; then
    PYTHON="/usr/bin/${PY_BIN}"
  else
    echo "${PY_BIN} is required to build the Debian venv (${SKYWARN_DEB_SUITE})" >&2
    exit 1
  fi
fi

echo "Building virtualenv at ${VENV_DIR} (project: ${PROJECT_ROOT}, python: ${PYTHON})"

rm -rf "${VENV_DIR}"
# --copies: embed interpreter in the venv (no symlinks to CI paths or wrong system python3).
"${PYTHON}" -m venv --copies "${VENV_DIR}"

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
python -m pip install --upgrade --upgrade-strategy eager "${PROJECT_ROOT}"

# Trim packaging bulk (runtime does not need pip cache or bytecode caches).
find "${VENV_DIR}" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "${VENV_DIR}" -type f -name '*.pyc' -delete 2>/dev/null || true
rm -rf "${VENV_DIR}/lib"/python*/site-packages/pip 2>/dev/null || true
rm -rf "${VENV_DIR}/lib"/python*/site-packages/setuptools 2>/dev/null || true

if [[ -L "${VENV_DIR}/bin/python3" ]]; then
  echo "venv/bin/python3 must be a copied binary, not a symlink" >&2
  exit 1
fi

"${PROJECT_ROOT}/scripts/debian/fix-venv-paths.sh" "${VENV_DIR}"

echo "Virtualenv ready: $("${VENV_DIR}/bin/python" -c 'import skywarnplus_ng; print(skywarnplus_ng.__version__)')"
