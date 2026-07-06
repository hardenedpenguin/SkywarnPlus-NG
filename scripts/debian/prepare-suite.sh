#!/bin/bash
# Generate debian/control for the target Debian suite (bookworm or trixie).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=/dev/null
source "${ROOT}/scripts/debian/suite-vars.sh" "${1:-${SKYWARN_DEB_SUITE:-trixie}}"

CONTROL_IN="${ROOT}/debian/control.in"
CONTROL_OUT="${ROOT}/debian/control"

if [[ ! -f "${CONTROL_IN}" ]]; then
  echo "Missing ${CONTROL_IN}" >&2
  exit 1
fi

sed "s|@LIBPYTHON_DEP@|${SKYWARN_LIBPYTHON_DEP}|g" "${CONTROL_IN}" >"${CONTROL_OUT}"
echo "Prepared ${CONTROL_OUT} for ${SKYWARN_DEB_SUITE} (${SKYWARN_LIBPYTHON_DEP})"
