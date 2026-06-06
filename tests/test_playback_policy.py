"""Tests for playback policy (quiet hours and announcement hold)."""

from datetime import datetime, timedelta, timezone

import pytest

from skywarnplus_ng.core.config import AlertConfig, QuietHoursConfig
from skywarnplus_ng.core.models import (
    AlertCategory,
    AlertCertainty,
    AlertSeverity,
    AlertStatus,
    AlertUrgency,
    WeatherAlert,
)
from skywarnplus_ng.playback.policy import PlaybackPolicy


def _alert(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id="urn:test:1",
        event="Tornado Warning",
        description="d",
        headline=None,
        instruction=None,
        severity=AlertSeverity.SEVERE,
        urgency=AlertUrgency.IMMEDIATE,
        certainty=AlertCertainty.OBSERVED,
        status=AlertStatus.ACTUAL,
        category=AlertCategory.MET,
        sent=now,
        effective=now,
        onset=now,
        expires=now + timedelta(hours=1),
        ends=now + timedelta(hours=2),
        area_desc="Test County",
        geocode=[],
        county_codes=["TXC039"],
        sender="s",
        sender_name="n",
    )
    base.update(overrides)
    return WeatherAlert(**base)


@pytest.fixture
def policy():
    return PlaybackPolicy(
        AlertConfig(
            quiet_hours=QuietHoursConfig(
                enabled=True,
                start="01:00",
                end="06:00",
                timezone="UTC",
                allow_severe=True,
            ),
            announcement_hold_minutes=30,
        )
    )


def test_quiet_hours_blocks_minor_alerts(policy):
    alert = _alert(severity=AlertSeverity.MINOR)
    now = datetime(2026, 5, 18, 3, 0, tzinfo=timezone.utc)
    allowed, reason = policy.should_announce_voice(alert, {}, now=now)
    assert allowed is False
    assert reason == "quiet_hours"


def test_quiet_hours_allows_severe_when_configured(policy):
    alert = _alert(severity=AlertSeverity.SEVERE)
    now = datetime(2026, 5, 18, 3, 0, tzinfo=timezone.utc)
    allowed, reason = policy.should_announce_voice(alert, {}, now=now)
    assert allowed is True
    assert reason is None


def test_announcement_hold_blocks_repeat(policy):
    alert = _alert()
    now = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    state = {"announcement_cooldown": {}}
    policy.record_announcement(alert, state, now=now)
    allowed, reason = policy.should_announce_voice(alert, state, now=now + timedelta(minutes=10))
    assert allowed is False
    assert reason == "announcement_hold"


def test_announcement_hold_expires(policy):
    alert = _alert()
    now = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    state = {"announcement_cooldown": {}}
    policy.record_announcement(alert, state, now=now)
    allowed, reason = policy.should_announce_voice(alert, state, now=now + timedelta(minutes=31))
    assert allowed is True
    assert reason is None


def test_cyclone_respects_quiet_hours(policy):
    now = datetime(2026, 5, 18, 3, 0, tzinfo=timezone.utc)
    allowed, reason = policy.should_announce_cyclone(now=now)
    assert allowed is False
    assert reason == "quiet_hours"
