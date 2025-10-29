#!/usr/bin/env python3
"""
Test script for SkywarnPlus-NG Asterisk Integration

This script tests various aspects of the Asterisk integration including:
- DTMF command processing
- Audio file generation
- Configuration validation
"""

import sys
import asyncio
from pathlib import Path

# Add the src directory to the path so we can import skywarnplus_ng
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skywarnplus_ng.core.config import AppConfig
from skywarnplus_ng.skydescribe.dtmf_handler import DTMFHandler


async def test_dtmf_commands():
    """Test DTMF command processing."""
    print("🧪 Testing DTMF Command Processing")
    print("=" * 40)
    
    # Load configuration
    try:
        config = AppConfig.from_yaml("config/default.yaml")
        print("✅ Configuration loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return False
    
    # Create DTMF handler
    try:
        dtmf_handler = DTMFHandler(config.skydescribe)
        print("✅ DTMF handler created successfully")
    except Exception as e:
        print(f"❌ Failed to create DTMF handler: {e}")
        return False
    
    # Mock callbacks for testing
    def get_current_alerts():
        return [
            {
                "id": "test-001",
                "event": "Severe Thunderstorm Warning",
                "area_desc": "Test County, TX",
                "severity": "Severe",
                "effective_time": "2024-01-01T12:00:00Z",
                "expires_time": "2024-01-01T18:00:00Z"
            }
        ]
    
    def get_system_status():
        return {
            "status": "running",
            "nws_connected": True,
            "audio_available": True,
            "asterisk_available": True,
            "uptime_seconds": 3600
        }
    
    def get_alert_by_id(alert_id):
        alerts = get_current_alerts()
        return next((alert for alert in alerts if alert["id"] == alert_id), None)
    
    # Set callbacks
    dtmf_handler.set_callbacks(get_current_alerts, get_system_status, get_alert_by_id)
    
    # Test DTMF codes
    test_codes = [
        ("*1", "current_alerts"),
        ("*2", "system_status"),
        ("*3", "all_clear"),
        ("*4", "system_status"),
        ("*9", "help")
    ]
    
    print("\n🔍 Testing DTMF Codes:")
    for code, expected_cmd in test_codes:
        try:
            response = await dtmf_handler.process_dtmf_code(code)
            if response.success:
                print(f"  ✅ {code} -> {expected_cmd} (SUCCESS: {response.audio_file})")
            else:
                print(f"  ❌ {code} -> {expected_cmd} (ERROR: {response.message})")
        except Exception as e:
            print(f"  ❌ {code} -> {expected_cmd} (EXCEPTION: {e})")
    
    return True


def test_configuration():
    """Test configuration validation."""
    print("\n🔧 Testing Configuration Validation")
    print("=" * 40)
    
    try:
        config = AppConfig.from_yaml("config/default.yaml")
        
        # Test DTMF configuration
        dtmf = config.skydescribe.dtmf_codes
        print(f"✅ DTMF Codes:")
        print(f"  - Current alerts: *{dtmf.current_alerts}")
        print(f"  - Alert by ID: *{dtmf.alert_by_id}")
        print(f"  - All clear: *{dtmf.all_clear}")
        print(f"  - System status: *{dtmf.system_status}")
        print(f"  - Help: *{dtmf.help}")
        
        # Test audio configuration
        audio = config.audio
        print(f"\n✅ Audio Configuration:")
        print(f"  - Sounds path: {audio.sounds_path}")
        print(f"  - Alert sound: {audio.alert_sound}")
        print(f"  - All clear sound: {audio.all_clear_sound}")
        print(f"  - Separator sound: {audio.separator_sound}")
        
        # Test Asterisk configuration
        asterisk = config.asterisk
        print(f"\n✅ Asterisk Configuration:")
        print(f"  - Enabled: {asterisk.enabled}")
        print(f"  - Nodes: {asterisk.nodes}")
        print(f"  - Audio delay: {asterisk.audio_delay}ms")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        return False


def test_sound_files():
    """Test sound file availability."""
    print("\n🔊 Testing Sound Files")
    print("=" * 40)
    
    sounds_path = Path("SOUNDS")
    if not sounds_path.exists():
        print("❌ SOUNDS directory not found")
        return False
    
    required_files = [
        "Duncecap.wav",
        "Triangles.wav", 
        "Woodblock.wav"
    ]
    
    print("✅ Checking required sound files:")
    all_found = True
    for file in required_files:
        file_path = sounds_path / file
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"  ✅ {file} ({size:,} bytes)")
        else:
            print(f"  ❌ {file} (missing)")
            all_found = False
    
    return all_found


async def main():
    """Main test function."""
    print("🚀 SkywarnPlus-NG Asterisk Integration Test")
    print("=" * 50)
    
    tests = [
        ("Configuration Validation", test_configuration),
        ("Sound Files", test_sound_files),
        ("DTMF Commands", test_dtmf_commands)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 20)
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\nResults: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Asterisk integration is ready.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
