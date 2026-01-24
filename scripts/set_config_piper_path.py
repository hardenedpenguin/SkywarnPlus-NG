#!/usr/bin/env python3
"""
Set Piper TTS model path and engine in SkywarnPlus-NG config.yaml.

Used by install.sh when creating a new config: installs en_US-amy-low (or medium)
and points audio.tts at the installed model.

Usage:
    python3 scripts/set_config_piper_path.py --config /etc/skywarnplus-ng/config.yaml --model-path /var/lib/skywarnplus-ng/piper/en_US-amy-low.onnx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set Piper TTS model path and engine in config.yaml",
    )
    parser.add_argument("--config", required=True, type=Path, help="Path to config.yaml")
    parser.add_argument("--model-path", required=True, type=Path, help="Absolute path to .onnx model")
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        return 1
    model_path = args.model_path.resolve()
    if not model_path.exists():
        print(f"Error: Model file not found: {model_path}", file=sys.stderr)
        return 1

    try:
        from ruamel.yaml import YAML
    except ImportError:
        print("Error: ruamel.yaml not found. Install with: pip install ruamel.yaml", file=sys.stderr)
        return 1

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    with open(args.config, "r", encoding="utf-8") as f:
        data = yaml.load(f)

    if "audio" not in data:
        data["audio"] = {}
    if "tts" not in data["audio"]:
        data["audio"]["tts"] = {}

    data["audio"]["tts"]["engine"] = "piper"
    data["audio"]["tts"]["model_path"] = str(model_path)

    with open(args.config, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

    print(f"Updated {args.config}: audio.tts.engine=piper, audio.tts.model_path={model_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
