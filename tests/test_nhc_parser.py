"""Tests for NHC cyclone XML parser and selection."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from skywarnplus_ng.core.config import AppConfig, NhcConfig, NWSApiConfig
from skywarnplus_ng.nhc.cyclone_service import NhcCycloneService
from skywarnplus_ng.nhc.parser import (
    build_cyclone_tts_text,
    filter_active_cyclones,
    haversine_miles,
    is_cyclone_current,
    parse_nhc_cyclone_xml,
)

FIXTURE = Path(__file__).parent / "fixtures" / "nhc_cyclone_sample.xml"
FROZEN_NOW = datetime(2026, 6, 5, 6, 0, tzinfo=timezone.utc)


@contextmanager
def frozen_nhc_time():
    with patch("skywarnplus_ng.nhc.parser.datetime") as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.fromisoformat = datetime.fromisoformat
        mock_dt.strptime = datetime.strptime
        yield


def test_parse_nhc_cyclone_xml():
    xml_text = FIXTURE.read_text()
    cyclones = parse_nhc_cyclone_xml(xml_text)
    assert len(cyclones) == 1
    cyclone = cyclones[0]
    assert cyclone.name == "ALPHA"
    assert cyclone.atcf == "AL012026"
    assert cyclone.center == "28.5,-90.0"
    assert cyclone.wind == "50 mph"


def test_filter_active_cyclones():
    xml_text = FIXTURE.read_text()
    cyclones = filter_active_cyclones(parse_nhc_cyclone_xml(xml_text))
    assert len(cyclones) == 1


def test_build_cyclone_tts_text_includes_name_and_wind():
    xml_text = FIXTURE.read_text()
    cyclone = parse_nhc_cyclone_xml(xml_text)[0]
    text = build_cyclone_tts_text(cyclone)
    assert "ALPHA" in text
    assert "50 mph" in text


def test_haversine_miles_known_distance():
    # New Orleans area to storm center in fixture (~70 miles)
    miles = haversine_miles(29.95, -90.07, 28.5, -90.0)
    assert 90 < miles < 110


def test_is_cyclone_current_recent_advisory():
    xml_text = FIXTURE.read_text()
    cyclone = parse_nhc_cyclone_xml(xml_text)[0]
    with frozen_nhc_time():
        assert is_cyclone_current(cyclone, max_age_hours=48) is True


def test_select_new_advisories_within_range():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        nhc=NhcConfig(
            enabled=True,
            max_distance_miles=500,
            max_advisory_age_hours=48,
            hurricanes_only=False,
            use_gps_position=False,
            static_lat=29.95,
            static_lon=-90.07,
        ),
    )
    service = NhcCycloneService(config)
    cyclones = parse_nhc_cyclone_xml(FIXTURE.read_text())
    with frozen_nhc_time():
        advisories = service.select_new_advisories(cyclones, {}, (29.95, -90.07))
    assert len(advisories) == 1
    assert advisories[0].name == "ALPHA"
    assert advisories[0].distance_miles < 500
    tracked = service._tracked_storms
    assert len(tracked) == 1
    assert tracked[0]["wind"] == "50 mph"
    assert tracked[0]["within_range"] is True
    assert tracked[0]["announced"] is False


def test_select_skips_already_announced():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        nhc=NhcConfig(enabled=True, max_distance_miles=500, max_advisory_age_hours=48),
    )
    service = NhcCycloneService(config)
    cyclones = parse_nhc_cyclone_xml(FIXTURE.read_text())
    state = {"nhc_announced_advisories": [cyclones[0].advisory_key]}
    advisories = service.select_new_advisories(cyclones, state, (29.95, -90.07))
    assert advisories == []
