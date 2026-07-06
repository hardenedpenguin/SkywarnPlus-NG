#!/bin/bash
# Build Bookworm and Trixie .deb packages for the current architecture.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for suite in bookworm trixie; do
  echo "=== Building ${suite} ==="
  "${ROOT}/scripts/build_deb.sh" "${suite}"
done

echo ""
echo "All suite packages:"
ls -lh "${ROOT}/dist/debs/"*.deb
