#!/bin/bash
# Normalize packaged venv paths for install on ASL3 nodes (not CI build dirs).
set -euo pipefail

VENV_DIR="${1:?usage: fix-venv-paths.sh <venv-dir> [install-prefix]}"
INSTALL_PREFIX="${2:-/var/lib/skywarnplus-ng/venv}"

if [[ ! -d "${VENV_DIR}/bin" ]]; then
  echo "venv bin directory missing: ${VENV_DIR}/bin" >&2
  exit 1
fi

python_bin="${INSTALL_PREFIX}/bin/python"

# Activate helpers are not used by the systemd service and embed build-time paths.
rm -f \
  "${VENV_DIR}/bin/activate" \
  "${VENV_DIR}/bin/activate.csh" \
  "${VENV_DIR}/bin/activate.fish" \
  "${VENV_DIR}/bin/Activate.ps1"

# Rewrite console-script shebangs (text files only; skip copied python binaries).
for entry in "${VENV_DIR}/bin/"*; do
  [[ -f "${entry}" && ! -L "${entry}" ]] || continue
  [[ -x "${entry}" ]] || continue
  # ELF / binary interpreters embed build paths; leave them alone.
  if ! head -c 2 "${entry}" 2>/dev/null | grep -q '^#!'; then
    continue
  fi
  first_line="$(head -n 1 "${entry}" 2>/dev/null || true)"
  [[ "${first_line}" == \#!*python* ]] || continue
  sed -i "1s|^#!.*|#!${python_bin}|" "${entry}"
done

if [[ -f "${VENV_DIR}/pyvenv.cfg" ]]; then
  py_version="$(grep -E '^version\s*=' "${VENV_DIR}/pyvenv.cfg" | sed -E 's/^version\s*=\s*//' | tr -d ' ')"
  if [[ -z "${py_version}" ]]; then
    py_version="3.13"
  fi
  cat >"${VENV_DIR}/pyvenv.cfg" <<EOF
home = ${INSTALL_PREFIX}/bin
include-system-site-packages = false
version = ${py_version}
executable = ${INSTALL_PREFIX}/bin/python3
command = ${INSTALL_PREFIX}/bin/python3 -m venv --copies ${INSTALL_PREFIX}
EOF
fi

# Fail if CI paths leaked into text launchers (not ELF interpreters).
leaked=0
for entry in "${VENV_DIR}/bin/"*; do
  [[ -f "${entry}" && ! -L "${entry}" ]] || continue
  if ! head -c 2 "${entry}" 2>/dev/null | grep -q '^#!'; then
    continue
  fi
  if grep -q '/home/runner/' "${entry}" 2>/dev/null \
    || grep -q '/opt/hostedtoolcache/' "${entry}" 2>/dev/null; then
    echo "${entry}" >&2
    leaked=1
  fi
done
if [[ "${leaked}" -ne 0 ]]; then
  echo "CI build paths remain in ${VENV_DIR}/bin launchers" >&2
  exit 1
fi

if grep -q '/opt/hostedtoolcache/' "${VENV_DIR}/pyvenv.cfg" 2>/dev/null \
  || grep -q '/home/runner/' "${VENV_DIR}/pyvenv.cfg" 2>/dev/null; then
  echo "CI build paths remain in ${VENV_DIR}/pyvenv.cfg" >&2
  exit 1
fi

echo "Venv paths normalized for ${INSTALL_PREFIX}"
