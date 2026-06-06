"""Tests for NHC config coercion from dashboard form values."""

from skywarnplus_ng.core.config import AppConfig, NWSApiConfig, NhcConfig


def test_nhc_config_accepts_empty_static_coords():
    nhc = NhcConfig(enabled=True, static_lat="", static_lon="")
    assert nhc.static_lat is None
    assert nhc.static_lon is None


def test_app_config_accepts_empty_nhc_coords():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        nhc={"enabled": True, "static_lat": "", "static_lon": ""},
    )
    assert config.nhc.enabled is True
    assert config.nhc.static_lat is None
    assert config.nhc.static_lon is None
