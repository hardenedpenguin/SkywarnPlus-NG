"""Tests for earthquake and wildfire health monitoring."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from skywarnplus_ng.core.config import AppConfig, EarthquakeConfig, GeoHazardPositionConfig, NWSApiConfig, WildfireConfig
from skywarnplus_ng.monitoring.health import ComponentStatus, HealthMonitor
from skywarnplus_ng.usgs.earthquake_service import UsgsEarthquakeService
from skywarnplus_ng.wildfire.wfigs_service import WfigsWildfireService


@pytest.fixture
def hazard_config():
    return AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        earthquake=EarthquakeConfig(
            enabled=True,
        ),
        wildfire=WildfireConfig(
            enabled=True,
        ),
        geo_hazard_position=GeoHazardPositionConfig(
            use_gps_position=False,
            static_lat=34.0,
            static_lon=-118.0,
        ),
    )


@pytest.mark.asyncio
async def test_check_earthquake_health_ok(hazard_config):
    service = UsgsEarthquakeService(hazard_config)
    service.check_health = AsyncMock(
        return_value={
            "ok": True,
            "message": "USGS feed OK (0 event(s) in lookback window)",
            "details": {},
        }
    )
    monitor = HealthMonitor(hazard_config, MagicMock())
    monitor.earthquake_service = service

    result = await monitor.check_earthquake_health({})
    assert result.status == ComponentStatus.HEALTHY
    assert result.name == "usgs_api"


@pytest.mark.asyncio
async def test_check_wildfire_health_ok(hazard_config):
    service = WfigsWildfireService(hazard_config)
    service.check_health = AsyncMock(
        return_value={
            "ok": True,
            "message": "WFIGS feed OK (0 incident(s) in search radius)",
            "details": {},
        }
    )
    monitor = HealthMonitor(hazard_config, MagicMock())
    monitor.wildfire_service = service

    result = await monitor.check_wildfire_health({})
    assert result.status == ComponentStatus.HEALTHY
    assert result.name == "wfigs_api"


@pytest.mark.asyncio
async def test_get_health_status_includes_hazards_when_enabled(hazard_config):
    eq_service = UsgsEarthquakeService(hazard_config)
    eq_service.check_health = AsyncMock(return_value={"ok": True, "message": "ok", "details": {}})
    wf_service = WfigsWildfireService(hazard_config)
    wf_service.check_health = AsyncMock(return_value={"ok": True, "message": "ok", "details": {}})

    monitor = HealthMonitor(hazard_config, MagicMock())
    monitor.nws_client = MagicMock()
    monitor.nws_client.test_connection = AsyncMock(return_value=True)
    monitor.earthquake_service = eq_service
    monitor.wildfire_service = wf_service

    status = await monitor.get_health_status({})
    names = {c.name for c in status.components}
    assert "usgs_api" in names
    assert "wfigs_api" in names
