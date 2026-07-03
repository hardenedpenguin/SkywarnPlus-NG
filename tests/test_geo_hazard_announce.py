"""Tests for monitor-only vs voice geo hazard settings."""

import pytest

from skywarnplus_ng.core.config import (
    AppConfig,
    EarthquakeConfig,
    GeoHazardPositionConfig,
    NWSApiConfig,
    WildfireConfig,
)
from skywarnplus_ng.usgs.earthquake_service import UsgsEarthquakeService
from skywarnplus_ng.usgs.parser import ParsedEarthquake
from skywarnplus_ng.wildfire.parser import ParsedWildfire
from skywarnplus_ng.wildfire.wfigs_service import WfigsWildfireService
from datetime import datetime, timezone


def test_earthquake_config_defaults_announce_enabled_true():
    eq = EarthquakeConfig(enabled=True)
    assert eq.announce_enabled is True


def test_wildfire_config_defaults_announce_enabled_true():
    wf = WildfireConfig(enabled=True)
    assert wf.announce_enabled is True


@pytest.mark.asyncio
async def test_earthquake_poll_skips_voice_cap_when_monitor_only(monkeypatch):
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        earthquake=EarthquakeConfig(
            enabled=True,
            announce_enabled=False,
            max_announcements_per_cycle=1,
            announce_history_on_enable=True,
        ),
        geo_hazard_position=GeoHazardPositionConfig(
            static_lat=34.0,
            static_lon=-118.0,
            use_gps_position=False,
        ),
    )
    service = UsgsEarthquakeService(config)
    events = [
        ParsedEarthquake(
            event_id=f"eq{i}",
            magnitude=4.0,
            place="near test",
            latitude=34.1,
            longitude=-118.1,
            depth_km=10.0,
            time_utc=datetime.now(timezone.utc),
            status="reviewed",
            tsunami=False,
            distance_miles=10,
            announcement_key=f"eq{i}",
        )
        for i in range(3)
    ]

    async def fake_fetch(_position):
        return {"features": []}

    monkeypatch.setattr(service, "fetch_events_geojson", fake_fetch)
    monkeypatch.setattr(
        "skywarnplus_ng.usgs.earthquake_service.parse_earthquake_collection",
        lambda _data, *, origin_lat, origin_lon: events,
    )
    monkeypatch.setattr(service, "get_position", lambda: (34.0, -118.0))

    selected = await service.poll({"usgs_history_seeded": True})
    assert len(selected) == 3


@pytest.mark.asyncio
async def test_wildfire_poll_skips_voice_cap_when_monitor_only(monkeypatch):
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        wildfire=WildfireConfig(
            enabled=True,
            announce_enabled=False,
            max_announcements_per_cycle=1,
            announce_history_on_enable=True,
        ),
        geo_hazard_position=GeoHazardPositionConfig(
            static_lat=34.0,
            static_lon=-118.0,
            use_gps_position=False,
        ),
    )
    service = WfigsWildfireService(config)
    incidents = [
        ParsedWildfire(
            incident_id=f"wf{i}",
            name=f"Fire {i}",
            acres=500.0,
            percent_contained=10,
            discovery_utc=datetime.now(timezone.utc),
            incident_type_kind="WF",
            feature_category="Wildfire",
            latitude=34.1,
            longitude=-118.1,
            distance_miles=10,
            announcement_key=f"wf{i}",
        )
        for i in range(3)
    ]

    async def fake_fetch(_position):
        return {"features": []}

    monkeypatch.setattr(service, "fetch_incidents_geojson", fake_fetch)
    monkeypatch.setattr(
        "skywarnplus_ng.wildfire.wfigs_service.parse_wildfire_collection",
        lambda _data, *, origin_lat, origin_lon: incidents,
    )
    monkeypatch.setattr(service, "get_position", lambda: (34.0, -118.0))

    selected = await service.poll({"wildfire_history_seeded": True})
    assert len(selected) == 3
