"""Tests for shared geo-hazard helpers."""

from datetime import datetime, timedelta, timezone

import pytest

from skywarnplus_ng.core.config import AppConfig, EarthquakeConfig, NWSApiConfig, WildfireConfig
from skywarnplus_ng.geo_hazard.fetch_cache import GeoFetchCache
from skywarnplus_ng.geo_hazard.tts import sanitize_for_tts
from skywarnplus_ng.usgs.earthquake_service import UsgsEarthquakeService
from skywarnplus_ng.usgs.parser import ParsedEarthquake
from skywarnplus_ng.wildfire.parser import ParsedWildfire
from skywarnplus_ng.wildfire.wfigs_service import WfigsWildfireService


def test_sanitize_for_tts_strips_control_chars_and_title_cases():
    assert sanitize_for_tts("  NEAR LOS ANGELES, CA  ") == "Near Los Angeles, Ca"
    assert sanitize_for_tts("HELLO WORLD") == "Hello World"
    assert sanitize_for_tts("a\u0007b") == "a b"


@pytest.mark.asyncio
async def test_geo_fetch_cache_deduplicates_in_flight():
    cache = GeoFetchCache(ttl_seconds=60)
    calls = 0

    async def fetch() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    first, second = await cache.get_or_fetch("key", fetch), await cache.get_or_fetch("key", fetch)
    assert first == second == "ok"
    assert calls == 1


def _eq_config(**kwargs) -> AppConfig:
    eq_kwargs = dict(
        enabled=True,
        min_magnitude=3.5,
        max_distance_miles=100,
        max_event_age_hours=6,
        max_announcements_per_cycle=2,
        static_lat=34.0,
        static_lon=-118.0,
        use_gps_position=False,
    )
    eq_kwargs.update(kwargs)
    return AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        earthquake=EarthquakeConfig(**eq_kwargs),
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


def test_select_new_events_respects_max_event_age():
    service = UsgsEarthquakeService(_eq_config())
    old = _sample_event(time_utc=datetime.now(timezone.utc) - timedelta(hours=12))
    assert service.select_new_events([old], {}) == []


def test_seed_history_marks_existing_without_selecting():
    service = UsgsEarthquakeService(_eq_config(announce_history_on_enable=False))
    state: dict = {}
    service._maybe_seed_announced_history([_sample_event()], state)
    assert state["usgs_history_seeded"] is True
    assert "us7000test" in state["usgs_announced_events"]
    assert service.select_new_events([_sample_event()], state) == []


@pytest.mark.asyncio
async def test_poll_caps_announcements_per_cycle(monkeypatch):
    service = UsgsEarthquakeService(
        _eq_config(max_announcements_per_cycle=1, announce_history_on_enable=True)
    )
    events = [
        _sample_event(event_id=f"eq{i}", announcement_key=f"eq{i}") for i in range(3)
    ]

    async def fake_fetch(_position):
        return {"features": []}

    def fake_parse(_data, *, origin_lat, origin_lon):
        return events

    monkeypatch.setattr(service, "fetch_events_geojson", fake_fetch)
    monkeypatch.setattr(
        "skywarnplus_ng.usgs.earthquake_service.parse_earthquake_collection",
        fake_parse,
    )
    monkeypatch.setattr(service, "get_position", lambda: (34.0, -118.0))

    selected = await service.poll({"usgs_history_seeded": True})
    assert len(selected) == 1


def test_wildfire_discovery_age_filter():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        wildfire=WildfireConfig(
            enabled=True,
            min_acres=250,
            max_distance_miles=50,
            max_discovery_age_hours=48,
            static_lat=34.0,
            static_lon=-118.0,
            use_gps_position=False,
        ),
    )
    service = WfigsWildfireService(config)
    old = ParsedWildfire(
        incident_id="old",
        name="Old Fire",
        acres=1000,
        percent_contained=None,
        discovery_utc=datetime.now(timezone.utc) - timedelta(hours=72),
        incident_type_kind="WF",
        feature_category="Wildfire",
        latitude=34.1,
        longitude=-118.1,
        distance_miles=10,
        announcement_key="old",
    )
    assert service.select_new_incidents([old], {}) == []
