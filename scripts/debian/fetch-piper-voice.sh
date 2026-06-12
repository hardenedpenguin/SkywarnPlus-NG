#!/bin/bash
# Download Piper en_US-amy-low voice files for the voice Debian package.
set -euo pipefail

OUT_DIR="${1:?usage: fetch-piper-voice.sh <output-dir>}"
QUALITY="${PIPER_QUALITY:-low}"
MODEL="en_US-amy-${QUALITY}"
BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/${QUALITY}"

mkdir -p "${OUT_DIR}"
ONNX="${OUT_DIR}/${MODEL}.onnx"
JSON="${OUT_DIR}/${MODEL}.onnx.json"

if [[ -f "${ONNX}" && -f "${JSON}" ]]; then
  echo "Piper voice already present in ${OUT_DIR}"
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to fetch Piper voice files" >&2
  exit 1
fi

echo "Downloading ${MODEL} from Hugging Face..."
curl -fL -o "${ONNX}" "${BASE_URL}/${MODEL}.onnx"
curl -fL -o "${JSON}" "${BASE_URL}/${MODEL}.onnx.json"
echo "Piper voice ready: ${ONNX}"
