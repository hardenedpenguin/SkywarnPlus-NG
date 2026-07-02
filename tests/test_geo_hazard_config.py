"""Tests for earthquake and wildfire config coercion."""

from pathlib import Path

from skywarnplus_ng.core.config import (
    AppConfig,
    EarthquakeConfig,
    GeoHazardPositionConfig,
    NWSApiConfig,
)


def test_earthquake_config_accepts_empty_ignore_automatic_below():
    eq = EarthquakeConfig(
        enabled=True,
        ignore_automatic_below="",
    )
    assert eq.ignore_automatic_below is None


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


def test_legacy_earthquake_coords_migrate_to_geo_hazard_position():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        earthquake={"enabled": True, "static_lat": 34.0, "static_lon": -118.0},
    )
    assert config.geo_hazard_position.static_lat == 34.0
    assert config.geo_hazard_position.static_lon == -118.0


def test_legacy_wildfire_coords_migrate_when_geo_position_empty():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        nhc={"static_lat": 29.95, "static_lon": -90.07},
        wildfire={"static_lat": 34.0, "static_lon": -118.0},
    )
    assert config.geo_hazard_position.static_lat == 29.95
    assert config.geo_hazard_position.static_lon == -90.07


def test_earthquake_config_allows_large_distance_radius():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        earthquake={"enabled": True, "max_distance_miles": 3000},
    )
    assert config.earthquake.max_distance_miles == 3000


def test_wildfire_config_allows_large_distance_radius():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        wildfire={"enabled": True, "max_distance_miles": 750},
    )
    assert config.wildfire.max_distance_miles == 750


def test_default_yaml_includes_geo_hazard_sections():
    config = AppConfig.from_yaml(Path("config/default.yaml"))
    assert config.geo_hazard_position.use_gps_position is True
    assert config.earthquake.enabled is False
    assert config.earthquake.min_magnitude == 3.5
    assert config.wildfire.enabled is False
    assert config.wildfire.min_acres == 250
