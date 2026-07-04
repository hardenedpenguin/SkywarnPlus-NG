"""Tests for NWSClient.filter_active_alerts."""

from datetime import datetime, timedelta, timezone

import pytest

from skywarnplus_ng.api.nws_client import NWSClient
from skywarnplus_ng.core.config import NWSApiConfig
from skywarnplus_ng.core.models import (
    AlertCategory,
    AlertCertainty,
    AlertSeverity,
    AlertStatus,
    AlertUrgency,
    WeatherAlert,
)


def _alert(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id="urn:test:1",
        event="Test Event",
        description="d",
        headline=None,
        instruction=None,
        severity=AlertSeverity.MINOR,
        urgency=AlertUrgency.EXPECTED,
        certainty=AlertCertainty.LIKELY,
        status=AlertStatus.ACTUAL,
        category=AlertCategory.MET,
        sent=now,
        effective=now - timedelta(hours=1),
        onset=now - timedelta(hours=1),
        expires=now + timedelta(hours=1),
        ends=now + timedelta(days=1),
        area_desc="A",
        geocode=[],
        county_codes=["TXC039"],
        sender="s",
        sender_name="n",
    )
    base.update(overrides)
    return WeatherAlert(**base)


@pytest.fixture
def nws_client():
    return NWSClient(NWSApiConfig(base_url="https://api.weather.gov", user_agent="test", timeout=5))


def test_filter_keeps_onset_window(nws_client):
    a = _alert()
    out = nws_client.filter_active_alerts([a], time_type="onset")
    assert len(out) == 1


def test_filter_drops_past_urgency_even_if_ends_future(nws_client):
    now = datetime.now(timezone.utc)
    a = _alert(
        urgency=AlertUrgency.PAST,
        onset=now - timedelta(hours=2),
        ends=now + timedelta(days=1),
        expires=now - timedelta(hours=1),
    )
    out = nws_client.filter_active_alerts([a], time_type="onset")
    assert out == []


def test_filter_drops_cancelled_headline(nws_client):
    now = datetime.now(timezone.utc)
    a = _alert(
        headline="The Rip Current Statement has been cancelled.",
        onset=now - timedelta(hours=1),
        ends=now + timedelta(days=1),
        expires=now + timedelta(hours=1),
    )
    out = nws_client.filter_active_alerts([a], time_type="onset")
    assert out == []


def test_filter_effective_mode_uses_expires(nws_client):
    now = datetime.now(timezone.utc)
    a = _alert(
        onset=now - timedelta(hours=1),
        effective=now - timedelta(hours=1),
        expires=now + timedelta(hours=2),
        ends=now + timedelta(days=1),
    )
    out = nws_client.filter_active_alerts([a], time_type="effective")
    assert len(out) == 1


def test_county_codes_from_geocode_marine_zones_and_same():
    geo = {
        "UGC": ["TXZ436", "TXC039"],
        "SAME": ["048167", "048039"],
    }
    codes = NWSClient._county_codes_from_nws_geocode(geo)
    assert codes == ["TXZ436", "TXC039", "TXC167"]


def test_parse_alert_derives_county_codes_from_same_when_ugc_is_marine_zones_only(nws_client):
    ts = "2026-04-12T15:09:00+00:00"
    feature = {
        "properties": {
            "id": "urn:test:galveston",
            "event": "Rip Current Statement",
            "sent": ts,
            "effective": ts,
            "expires": ts,
            "geocode": {"UGC": ["TXZ436", "TXZ437"], "SAME": ["048321", "048039", "048167"]},
            "areaDesc": "Matagorda Islands; Brazoria Islands; Galveston Island",
        }
    }
    alert = nws_client._parse_alert(feature)
    assert alert.county_codes == ["TXZ436", "TXZ437", "TXC321", "TXC039", "TXC167"]
