"""Tests for geo hazard position config coercion from dashboard form values."""

from skywarnplus_ng.core.config import AppConfig, GeoHazardPositionConfig, NWSApiConfig


def test_geo_hazard_position_accepts_empty_static_coords():
    pos = GeoHazardPositionConfig(static_lat="", static_lon="")
    assert pos.static_lat is None
    assert pos.static_lon is None


def test_app_config_accepts_empty_geo_hazard_coords():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        geo_hazard_position={"static_lat": "", "static_lon": ""},
    )
    assert config.geo_hazard_position.static_lat is None
    assert config.geo_hazard_position.static_lon is None


def test_legacy_nhc_coords_migrate_to_geo_hazard_position():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        nhc={"enabled": True, "static_lat": 29.95, "static_lon": -90.07},
    )
    assert config.geo_hazard_position.static_lat == 29.95
    assert config.geo_hazard_position.static_lon == -90.07
