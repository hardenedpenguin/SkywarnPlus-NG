"""Tests for WFIGS wildfire service selection logic."""

from unittest.mock import MagicMock

import pytest

from skywarnplus_ng.core.config import AppConfig, NWSApiConfig, WildfireConfig
from skywarnplus_ng.wildfire.parser import ParsedWildfire
from skywarnplus_ng.wildfire.wfigs_service import WfigsWildfireService


@pytest.fixture
def wildfire_config():
    return AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        wildfire=WildfireConfig(
            enabled=True,
            min_acres=250,
            max_distance_miles=50,
            exclude_prescribed=True,
            static_lat=34.0,
            static_lon=-118.0,
            use_gps_position=False,
        ),
    )


def _sample_incident(**overrides):
    base = dict(
        incident_id="2024-CA-TEST",
        name="Sample Fire",
        acres=1200.0,
        percent_contained=10,
        discovery_utc=None,
        incident_type_kind="WF",
        feature_category="Wildfire",
        latitude=34.1,
        longitude=-118.1,
        distance_miles=12,
        announcement_key="2024-CA-TEST",
    )
    base.update(overrides)
    return ParsedWildfire(**base)


def test_select_new_incidents_skips_announced(wildfire_config):
    service = WfigsWildfireService(wildfire_config)
    state = {"wildfire_announced_incidents": ["2024-CA-TEST"]}
    selected = service.select_new_incidents([_sample_incident()], state)
    assert selected == []


def test_select_new_incidents_excludes_prescribed(wildfire_config):
    service = WfigsWildfireService(wildfire_config)
    selected = service.select_new_incidents(
        [_sample_incident(incident_type_kind="RX", acres=5000)],
        {},
    )
    assert selected == []


def test_select_new_incidents_respects_acres(wildfire_config):
    service = WfigsWildfireService(wildfire_config)
    selected = service.select_new_incidents([_sample_incident(acres=50)], {})
    assert selected == []


def test_select_new_incidents_announces_eligible(wildfire_config):
    service = WfigsWildfireService(wildfire_config)
    selected = service.select_new_incidents([_sample_incident()], {})
    assert len(selected) == 1
    assert selected[0].incident_id == "2024-CA-TEST"


def test_get_position_uses_mobile_when_enabled(wildfire_config):
    wildfire_config.wildfire.use_gps_position = True
    mobile = MagicMock()
    mobile.get_position.return_value = (34.05, -118.25)
    service = WfigsWildfireService(wildfire_config, mobile)
    assert service.get_position() == (34.05, -118.25)
