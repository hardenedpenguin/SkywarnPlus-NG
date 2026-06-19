#!/usr/bin/env python3
"""
Set asl-tts voice and engine in SkywarnPlus-NG config.yaml.

Example:
    python3 scripts/set_config_asl_tts.py --config /etc/skywarnplus-ng/config.yaml --voice en_US-amy-low.onnx
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ruamel.yaml import YAML


def main() -> None:
    parser = argparse.ArgumentParser(description="Set asl-tts voice in config.yaml")
    parser.add_argument("--config", required=True, type=Path, help="Path to config.yaml")
    parser.add_argument(
        "--voice",
        default="en_US-amy-low.onnx",
        help="Piper voice filename under /var/lib/piper-tts",
    )
    parser.add_argument(
        "--node",
        type=int,
        default=None,
        help="AllStar node number for asl-tts -n",
    )
    args = parser.parse_args()

    yaml = YAML()
    yaml.preserve_quotes = True
    with open(args.config, encoding="utf-8") as f:
        data = yaml.load(f) or {}

    data.setdefault("audio", {}).setdefault("tts", {})
    data["audio"]["tts"]["engine"] = "asl-tts"
    data["audio"]["tts"]["voice"] = args.voice
    data["audio"]["tts"]["voices_dir"] = "/var/lib/piper-tts"
    data["audio"]["tts"]["asl_tts_binary"] = "asl-tts"
    if args.node is not None:
        data["audio"]["tts"]["node_number"] = args.node

    with open(args.config, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

    print(f"Updated {args.config}: audio.tts.engine=asl-tts, audio.tts.voice={args.voice}")


if __name__ == "__main__":
    main()
