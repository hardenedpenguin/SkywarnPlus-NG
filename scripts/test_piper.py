#!/usr/bin/env python3
"""
Diagnostic script to test Piper TTS installation and configuration.

This script helps diagnose issues with Piper TTS by:
1. Checking if piper-tts is installed
2. Testing model file loading
3. Testing synthesis with a short text
4. Verifying output file creation

Usage:
    python3 scripts/test_piper.py [model_path]
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

def test_synthesis(voice, test_text: str = "Test", timeout: int = 10):
    """Test synthesis with a short text."""
    print(f"\nTesting synthesis with text: '{test_text}'")
    print(f"  Timeout: {timeout} seconds")
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    
    try:
        print("  Starting synthesis...")
        start_time = time.time()
        
        # Attempt synthesis
        with open(temp_path, "wb") as audio_file:
            # Try to get the API signature
            import inspect
            try:
                sig = inspect.signature(voice.synthesize)
                params = list(sig.parameters.keys())
                print(f"  API signature parameters: {params}")
                
                # Try different parameter combinations
                if len(params) == 2:  # Just text and file
                    voice.synthesize(test_text, audio_file)
                elif 'length_scale' in params:
                    voice.synthesize(test_text, audio_file, length_scale=1.0)
                elif 'speed' in params:
                    voice.synthesize(test_text, audio_file, speed=1.0)
                else:
                    # Try basic call
                    voice.synthesize(test_text, audio_file)
            except Exception as e:
                print(f"  ✗ Error checking API signature: {e}")
                # Try basic call anyway
                voice.synthesize(test_text, audio_file)
        
        elapsed = time.time() - start_time
        print(f"  Synthesis completed in {elapsed:.2f} seconds")
        
        # Check output file
        if not temp_path.exists():
            print("  ✗ Output file was not created")
            return False
        
        file_size = temp_path.stat().st_size
        if file_size == 0:
            print("  ✗ Output file is empty")
            temp_path.unlink()
            return False
        
        print(f"  ✓ Output file created: {temp_path} ({file_size} bytes)")
        
        # Try to validate it's a valid WAV file
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_wav(str(temp_path))
            duration = len(audio) / 1000.0
            print(f"  ✓ Valid WAV file: {duration:.2f} seconds, {audio.frame_rate} Hz, {audio.channels} channel(s)")
        except Exception as e:
            print(f"  ⚠ Could not validate WAV file: {e}")
        
        # Clean up
        temp_path.unlink()
        return True
        
    except Exception as e:
        elapsed = time.time() - start_time if 'start_time' in locals() else 0
        print(f"  ✗ Synthesis failed after {elapsed:.2f} seconds: {e}")
        import traceback
        traceback.print_exc()
        
        # Clean up
        if temp_path.exists():
            temp_path.unlink()
        
        return False

def main():
    """Main diagnostic function."""
    print("=" * 60)
    print("Piper TTS Diagnostic Script")
    print("=" * 60)
    
    # Test import
    success, piper_voice_class = test_piper_import()
    if not success:
        sys.exit(1)
    
    # Get model path
    if len(sys.argv) > 1:
        model_path = Path(sys.argv[1])
    else:
        print("\nModel path not provided.")
        print("Usage: python3 scripts/test_piper.py [model_path]")
        print("Example: python3 scripts/test_piper.py /opt/piper/en_US-amy-medium.onnx")
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


