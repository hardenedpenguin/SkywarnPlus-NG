#!/usr/bin/env python3
"""
Test script for PushOver notification functionality.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.skywarnplus_ng.notifications.pushover import PushOverNotifier, PushOverConfig
from src.skywarnplus_ng.core.models import WeatherAlert, AlertSeverity, AlertUrgency, AlertCertainty, AlertStatus, AlertCategory
from datetime import datetime, timezone


async def test_pushover(api_token: str, user_key: str):
    """Test PushOver notification sending."""
    
    print("🔄 Testing PushOver notification system...")
    print(f"   API Token: {api_token[:10]}...")
    print(f"   User Key: {user_key[:10]}...")
    print()
    
    # Create configuration
    config = PushOverConfig(
        api_token=api_token,
        user_key=user_key,
        enabled=True,
        priority=0,  # Normal priority for testing
        sound="magic"
    )
    
    # Test simple notification
    print("📤 Sending test notification...")
    async with PushOverNotifier(config) as pushover:
        result = await pushover.test_pushover()
        
        if result:
            print("✅ PushOver test notification sent successfully!")
        else:
            print("❌ PushOver test notification failed")
            return False
    
    print()
    
    # Test alert notification
    print("📤 Sending test weather alert notification...")
    
    # Create a mock alert
    mock_alert = WeatherAlert(
        id="TEST-ALERT-001",
        event="Tornado Warning",
        headline="Tornado Warning for Test County",
        description="This is a test tornado warning. Take shelter immediately. This is only a test message.",
        instruction="Go to the lowest level of your home and take cover. Stay away from windows.",
        severity=AlertSeverity.EXTREME,
        urgency=AlertUrgency.IMMEDIATE,
        certainty=AlertCertainty.OBSERVED,
        status=AlertStatus.TEST,
        category=AlertCategory.MET,
        sent=datetime.now(timezone.utc),
        effective=datetime.now(timezone.utc),
        expires=datetime.now(timezone.utc).replace(hour=23, minute=59, second=59),
        area_desc="Test County, TX",
        sender="TEST",
        sender_name="Test Weather Service"
    )
    
    async with PushOverNotifier(config) as pushover:
        result = await pushover.send_alert_push(mock_alert)
        
        if result.get("success", False):
            print("✅ PushOver alert notification sent successfully!")
            print(f"   Sent to: {result.get('sent_count', 0)} recipient(s)")
            print(f"   Priority: {result.get('priority', 'N/A')}")
            print(f"   Sound: {result.get('sound', 'N/A')}")
        else:
            print("❌ PushOver alert notification failed")
            print(f"   Error: {result.get('error', 'Unknown error')}")
            return False
    
    print()
    print("✨ All PushOver tests completed successfully!")
    return True


async def main():
    """Main entry point."""
    print("=" * 70)
    print("PushOver Notification Test Script")
    print("=" * 70)
    print()
    
    # Check if credentials are provided
    if len(sys.argv) < 3:
        print("Usage: python test_pushover.py <API_TOKEN> <USER_KEY>")
        print()
        print("To get your credentials:")
        print("  1. Go to https://pushover.net/apps/build to create an app")
        print("  2. Go to https://pushover.net/ to get your user key")
        print()
        sys.exit(1)
    
    api_token = sys.argv[1]
    user_key = sys.argv[2]
    
    # Run tests
    success = await test_pushover(api_token, user_key)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

