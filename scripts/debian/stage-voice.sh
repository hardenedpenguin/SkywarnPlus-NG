#!/bin/bash
# Stage filesystem tree for the Piper voice add-on package.
set -euo pipefail

VOICE_SRC="${1:?usage: stage-voice.sh <voice-files-dir> <debian-staging-dir>}"
PKG_DIR="${2:?usage: stage-voice.sh <voice-files-dir> <debian-staging-dir>}"

rm -rf "${PKG_DIR}"
install -d -m 755 "${PKG_DIR}/var/lib/skywarnplus-ng/piper"
cp -a "${VOICE_SRC}/." "${PKG_DIR}/var/lib/skywarnplus-ng/piper/"
echo "Staged voice package under ${PKG_DIR}"
