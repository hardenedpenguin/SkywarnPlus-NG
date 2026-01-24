#!/usr/bin/env python3
"""
Diagnostic script to test Piper TTS installation and configuration.

This script helps diagnose issues with Piper TTS by:
1. Checking if piper-tts is installed
2. Testing model file loading
3. Testing synthesis with a short text
4. Verifying output file creation

Usage:
    # From install directory (use venv Python; piper-tts is not in system Python):
    venv/bin/python3 scripts/test_piper.py [model_path]

    # model_path optional when run from install dir: defaults to piper/en_US-amy-low.onnx
    venv/bin/python3 scripts/test_piper.py
    venv/bin/python3 scripts/test_piper.py piper/en_US-amy-low.onnx

    # With absolute path:
    venv/bin/python3 scripts/test_piper.py /var/lib/skywarnplus-ng/piper/en_US-amy-low.onnx
"""

import sys
import tempfile
import time
from pathlib import Path

def test_piper_import():
    """Test if piper-tts can be imported."""
    print("Testing Piper TTS library import...")
    try:
        from piper import PiperVoice
        print("✓ Piper TTS library imported successfully")
        return True, PiperVoice
    except ImportError as e:
        print(f"✗ Failed to import Piper TTS: {e}")
        print("  Install with: pip install piper-tts")
        return False, None

def test_model_loading(model_path: Path, piper_voice_class):
    """Test if model file can be loaded."""
    print(f"\nTesting model file loading: {model_path}")
    
    if not model_path.exists():
        print(f"✗ Model file does not exist: {model_path}")
        return False, None
    
    config_path = model_path.with_suffix(model_path.suffix + ".json")
    if not config_path.exists():
        print(f"⚠ Config file not found: {config_path}")
        print("  Attempting to load without config file...")
    
    try:
        if config_path.exists():
            print(f"  Loading with config: {config_path}")
            voice = piper_voice_class.load(str(model_path), config_path=str(config_path))
        else:
            print("  Loading without config file...")
            voice = piper_voice_class.load(str(model_path))
        
        print("✓ Model loaded successfully")
        return True, voice
    except Exception as e:
        print(f"✗ Failed to load model: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def _synthesize_v13(voice, text: str, output_path: Path) -> bool:
    """Piper 1.3+ API: synthesize(text, syn_config) yields AudioChunk; write WAV."""
    import inspect
    import wave
    from piper.config import SynthesisConfig

    sig = inspect.signature(voice.synthesize)
    params = list(sig.parameters.keys())
    if "syn_config" not in params:
        return False

    cfg = SynthesisConfig(length_scale=1.0)
    chunks = list(voice.synthesize(text, cfg))
    if not chunks:
        return False

    c = chunks[0]
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(c.sample_channels)
        wav.setsampwidth(c.sample_width)
        wav.setframerate(c.sample_rate)
        for ch in chunks:
            wav.writeframes(ch.audio_int16_bytes)
    return True


def _synthesize_legacy(voice, text: str, output_path: Path) -> bool:
    """Legacy Piper API: synthesize(text, file_handle, ...)."""
    import inspect

    sig = inspect.signature(voice.synthesize)
    params = list(sig.parameters.keys())
    with open(output_path, "wb") as f:
        if "length_scale" in params:
            voice.synthesize(text, f, length_scale=1.0)
        elif "speed" in params:
            voice.synthesize(text, f, speed=1.0)
        else:
            voice.synthesize(text, f)
    return True


def test_synthesis(voice, test_text: str = "Test", timeout: int = 10):
    """Test synthesis with a short text."""
    print(f"\nTesting synthesis with text: '{test_text}'")
    print(f"  Timeout: {timeout} seconds")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        print("  Starting synthesis...")
        start_time = time.time()

        import inspect
        sig = inspect.signature(voice.synthesize)
        params = list(sig.parameters.keys())
        print(f"  API signature parameters: {params}")

        if "syn_config" in params:
            ok = _synthesize_v13(voice, test_text, temp_path)
        else:
            ok = _synthesize_legacy(voice, test_text, temp_path)

        if not ok:
            print("  ✗ Synthesis produced no output")
            temp_path.unlink(missing_ok=True)
            return False

        elapsed = time.time() - start_time
        print(f"  Synthesis completed in {elapsed:.2f} seconds")

        if not temp_path.exists():
            print("  ✗ Output file was not created")
            return False

        file_size = temp_path.stat().st_size
        if file_size == 0:
            print("  ✗ Output file is empty")
            temp_path.unlink()
            return False

        print(f"  ✓ Output file created: {temp_path} ({file_size} bytes)")

        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_wav(str(temp_path))
            duration = len(audio) / 1000.0
            print(f"  ✓ Valid WAV file: {duration:.2f} seconds, {audio.frame_rate} Hz, {audio.channels} channel(s)")
        except Exception as e:
            print(f"  ⚠ Could not validate WAV file: {e}")

        temp_path.unlink()
        return True

    except Exception as e:
        elapsed = time.time() - start_time if "start_time" in locals() else 0
        print(f"  ✗ Synthesis failed after {elapsed:.2f} seconds: {e}")
        import traceback
        traceback.print_exc()
        temp_path.unlink(missing_ok=True)
        return False

def main():
    """Main diagnostic function."""
    print("=" * 60)
    print("Piper TTS Diagnostic Script")
    print("=" * 60)
    
    # Test import
    success, piper_voice_class = test_piper_import()
    if not success:
        print("\n  Hint: Use the venv Python (e.g. venv/bin/python3) when run from the install dir.")
        sys.exit(1)

    # Get model path: explicit arg, or default when run from install dir
    if len(sys.argv) > 1:
        model_path = Path(sys.argv[1])
    else:
        cwd = Path.cwd()
        for candidate in ("piper/en_US-amy-low.onnx", "piper/en_US-amy-medium.onnx"):
            p = (cwd / candidate).resolve()
            if p.exists():
                model_path = p
                print(f"\nNo model path given; using install default: {model_path}")
                break
        else:
            print("\nModel path not provided.")
            print("Usage: venv/bin/python3 scripts/test_piper.py [model_path]")
            print("  When run from install dir, model_path defaults to piper/en_US-amy-low.onnx")
            print("Example: venv/bin/python3 scripts/test_piper.py piper/en_US-amy-low.onnx")
            sys.exit(1)
    
    # Test model loading
    success, voice = test_model_loading(model_path, piper_voice_class)
    if not success:
        sys.exit(1)
    
    # Test synthesis
    success = test_synthesis(voice, "This is a test of Piper text to speech synthesis.")
    if not success:
        print("\n✗ Synthesis test failed")
        print("\nPossible issues:")
        print("  - Model file is corrupted")
        print("  - Incompatible Piper library version")
        print("  - Resource constraints (memory/CPU)")
        print("  - Model file format mismatch")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ All tests passed! Piper TTS appears to be working correctly.")
    print("=" * 60)

if __name__ == "__main__":
    main()


