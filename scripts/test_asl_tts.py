#!/usr/bin/env python3
"""
Diagnostic script for asl-tts (asl3-tts package) used by SkywarnPlus-NG.

Example:
    scripts/test_asl_tts.py
    scripts/test_asl_tts.py --node 546050 --voice en_US-amy-low.onnx
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Test asl-tts installation")
    parser.add_argument("--binary", default="asl-tts", help="asl-tts command")
    parser.add_argument("--voice", default="en_US-amy-low.onnx", help="Voice filename")
    parser.add_argument(
        "--voices-dir", default="/var/lib/piper-tts", help="Piper voices directory"
    )
    parser.add_argument("--node", type=int, default=1, help="AllStar node number")
    args = parser.parse_args()

    binary = shutil.which(args.binary) or args.binary
    if not Path(binary).is_file() and not shutil.which(args.binary):
        print(f"✗ asl-tts not found: {args.binary}")
        print("  Install the asl3-tts package.")
        return 1
    print(f"✓ asl-tts: {binary}")

    voice_path = Path(args.voices_dir) / args.voice
    config_path = voice_path.with_suffix(voice_path.suffix + ".json")
    if not voice_path.is_file() or not config_path.is_file():
        print(f"✗ Voice missing: {voice_path} (+ .json sidecar)")
        return 1
    print(f"✓ Voice: {voice_path}")

    with tempfile.TemporaryDirectory(prefix="swp-tts-") as tmp:
        base = Path(tmp) / "test"
        cmd = [
            binary,
            "-n",
            str(args.node),
            "-t",
            "This is a SkywarnPlus test of asl-tts.",
            "-v",
            args.voice,
            "-f",
            str(base),
        ]
        print("Running:", " ".join(cmd))
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except subprocess.CalledProcessError as exc:
            print(f"✗ asl-tts failed: {(exc.stderr or exc.stdout or exc).strip()}")
            return 1
        ul = base.with_suffix(".ul")
        if not ul.is_file() or ul.stat().st_size == 0:
            print("✗ asl-tts did not produce .ul output")
            return 1
        print(f"✓ Generated {ul} ({ul.stat().st_size} bytes)")

    print("✓ asl-tts appears to be working")
    return 0


if __name__ == "__main__":
    sys.exit(main())
