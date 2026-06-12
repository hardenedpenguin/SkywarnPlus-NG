"""Tests for Twilio SMS notifications."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from aiohttp import web

from skywarnplus_ng.core.models import AlertSeverity, AlertUrgency, AlertCertainty, WeatherAlert
from skywarnplus_ng.notifications.sms import (
    SmsConfig,
    SmsNotifier,
    format_short_alert_message,
    format_short_general_message,
)


def _sample_alert() -> WeatherAlert:
    return WeatherAlert(
        id="test-alert-1",
        event="Tornado Warning",
        description="Take shelter now.",
        severity=AlertSeverity.EXTREME,
        urgency=AlertUrgency.IMMEDIATE,
        certainty=AlertCertainty.OBSERVED,
        sent=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
        effective=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
        expires=datetime(2026, 5, 18, 15, 0, tzinfo=timezone.utc),
        area_desc="Harris County",
        sender="kwn@noaa.gov",
        sender_name="NWS Houston",
    )


def test_format_short_alert_message():
    body = format_short_alert_message(_sample_alert(), max_length=160)
    assert "Tornado Warning" in body
    assert "Harris County" in body
    assert len(body) <= 160


def test_format_short_general_message_truncates():
    body = format_short_general_message("Title", "x" * 200, max_length=50)
    assert len(body) <= 50
    assert body.endswith("...")


def test_sms_config_requires_twilio_fields():
    with pytest.raises(ValueError, match="Account SID"):
        SmsConfig(account_sid="", auth_token="tok", from_number="+15559876543")
    with pytest.raises(ValueError, match="Auth Token"):
        SmsConfig(account_sid="ACtest", auth_token="", from_number="+15559876543")
    with pytest.raises(ValueError, match="From number"):
        SmsConfig(account_sid="ACtest", auth_token="tok", from_number="bad")


@pytest.mark.asyncio
async def test_sms_notifier_posts_to_twilio():
    received: list[dict] = []

    async def handler(request: web.Request) -> web.Response:
        received.append(
            {
                "auth": request.headers.get("Authorization"),
                "body": await request.text(),
            }
        )
        return web.json_response({"sid": "SMtest123", "status": "queued"}, status=201)

    app = web.Application()
    app.router.add_post("/2010-04-01/Accounts/ACtest/Messages.json", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    try:
        config = SmsConfig(
            account_sid="ACtest",
            auth_token="secret",
            from_number="+15559876543",
            retry_count=1,
            retry_delay_seconds=0,
            api_base_url=f"http://127.0.0.1:{port}/2010-04-01",
        )
        async with SmsNotifier(config) as notifier:
            result = await notifier.send_alert_sms(_sample_alert(), "+15551234567")

        assert result["success"] is True
        assert result.get("message_sid") == "SMtest123"
        assert len(received) == 1
        assert "To=%2B15551234567" in received[0]["body"]
        assert "From=%2B15559876543" in received[0]["body"]
        assert received[0]["auth"].startswith("Basic ")
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_sms_notifier_rejects_invalid_phone():
    config = SmsConfig(
        account_sid="ACtest",
        auth_token="secret",
        from_number="+15559876543",
        retry_count=1,
    )
    async with SmsNotifier(config) as notifier:
        result = await notifier.send_sms("bad", "hello")
    assert result["success"] is False
    assert "Invalid" in result["error"]
