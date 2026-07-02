"""Tests for USGS earthquake service selection logic."""

from unittest.mock import MagicMock

import pytest

from skywarnplus_ng.core.config import AppConfig, EarthquakeConfig, GeoHazardPositionConfig, NWSApiConfig
from skywarnplus_ng.usgs.earthquake_service import UsgsEarthquakeService
from skywarnplus_ng.usgs.parser import ParsedEarthquake
from datetime import datetime, timezone


@pytest.fixture
def earthquake_config():
    return AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        earthquake=EarthquakeConfig(
            enabled=True,
            min_magnitude=3.5,
            max_distance_miles=100,
        ),
        geo_hazard_position=GeoHazardPositionConfig(
            static_lat=34.0,
            static_lon=-118.0,
            use_gps_position=False,
        ),
    )


def _sample_event(**overrides):
    base = dict(
        event_id="us7000test",
        magnitude=4.0,
        place="near test",
        latitude=34.1,
        longitude=-118.1,
        depth_km=10.0,
        time_utc=datetime.now(timezone.utc),
        status="reviewed",
        tsunami=False,
        distance_miles=10,
        announcement_key="us7000test",
    )
    base.update(overrides)
    return ParsedEarthquake(**base)


def test_select_new_events_skips_announced(earthquake_config):
    service = UsgsEarthquakeService(earthquake_config)
    state = {"usgs_announced_events": ["us7000test"]}
    selected = service.select_new_events([_sample_event()], state)
    assert selected == []


def test_select_new_events_respects_magnitude(earthquake_config):
    service = UsgsEarthquakeService(earthquake_config)
    selected = service.select_new_events([_sample_event(magnitude=2.0)], {})
    assert selected == []


def test_select_new_events_respects_automatic_threshold(earthquake_config):
    earthquake_config.earthquake.ignore_automatic_below = 4.5
    service = UsgsEarthquakeService(earthquake_config)
    selected = service.select_new_events(
        [_sample_event(magnitude=4.0, status="automatic")],
        {},
    )
    assert selected == []


def test_select_new_events_announces_eligible(earthquake_config):
    service = UsgsEarthquakeService(earthquake_config)
    selected = service.select_new_events([_sample_event()], {})
    assert len(selected) == 1
    assert selected[0].event_id == "us7000test"


def test_get_position_uses_mobile_when_enabled(earthquake_config):
    earthquake_config.geo_hazard_position.use_gps_position = True
    mobile = MagicMock()
    mobile.get_position.return_value = (29.9, -90.1)
    service = UsgsEarthquakeService(earthquake_config, mobile)
    assert service.get_position() == (29.9, -90.1)
