#!/bin/bash
# Map Debian suite (bookworm/trixie) to Python and libpython packaging variables.
# shellcheck disable=SC2034
set -euo pipefail

_suite="${1:-${SKYWARN_DEB_SUITE:-trixie}}"

case "${_suite}" in
  bookworm | deb12)
    SKYWARN_DEB_SUITE=bookworm
    SKYWARN_DEB_TAG=deb12
    SKYWARN_PYTHON_MINOR=3.11
    SKYWARN_LIBPYTHON_DEP='libpython3.11 (>= 3.11.0~)'
    ;;
  trixie | deb13)
    SKYWARN_DEB_SUITE=trixie
    SKYWARN_DEB_TAG=deb13
    SKYWARN_PYTHON_MINOR=3.13
    SKYWARN_LIBPYTHON_DEP='libpython3.13 (>= 3.13.0~)'
    ;;
  *)
    echo "Unknown Debian suite: ${_suite} (use bookworm or trixie)" >&2
    exit 1
    ;;
esac

export SKYWARN_DEB_SUITE SKYWARN_DEB_TAG SKYWARN_PYTHON_MINOR SKYWARN_LIBPYTHON_DEP
