"""Tests for earthquake and wildfire config coercion."""

from pathlib import Path

from skywarnplus_ng.core.config import AppConfig, EarthquakeConfig, NWSApiConfig, WildfireConfig


def test_earthquake_config_accepts_empty_optional_fields():
    eq = EarthquakeConfig(
        enabled=True,
        static_lat="",
        static_lon="",
        ignore_automatic_below="",
    )
    assert eq.static_lat is None
    assert eq.static_lon is None
    assert eq.ignore_automatic_below is None


def test_wildfire_config_accepts_empty_static_coords():
    wf = WildfireConfig(enabled=True, static_lat="", static_lon="")
    assert wf.static_lat is None
    assert wf.static_lon is None


def test_app_config_accepts_empty_geo_hazard_coords():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        earthquake={"enabled": True, "static_lat": "", "static_lon": ""},
        wildfire={"enabled": True, "static_lat": "", "static_lon": ""},
    )
    assert config.earthquake.static_lat is None
    assert config.wildfire.static_lon is None


def test_default_yaml_includes_geo_hazard_sections():
    config = AppConfig.from_yaml(Path("config/default.yaml"))
    assert config.earthquake.enabled is False
    assert config.earthquake.min_magnitude == 3.5
    assert config.wildfire.enabled is False
    assert config.wildfire.min_acres == 250
