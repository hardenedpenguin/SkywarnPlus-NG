"""Tests for NHC health monitoring."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from skywarnplus_ng import __version__ as APP_VERSION
from skywarnplus_ng.core.config import (
    AppConfig,
    GeoHazardPositionConfig,
    GpsdConfig,
    NWSApiConfig,
    NhcConfig,
)
from skywarnplus_ng.monitoring.health import ComponentStatus, HealthMonitor, rollup_overall_status
from skywarnplus_ng.nhc.cyclone_service import NhcCycloneService


@pytest.fixture
def nhc_config():
    return AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        gpsd=GpsdConfig(enabled=True),
        nhc=NhcConfig(
            enabled=True,
        ),
        geo_hazard_position=GeoHazardPositionConfig(
            use_gps_position=True,
            static_lat=29.95,
            static_lon=-90.07,
        ),
    )


@pytest.mark.asyncio
async def test_check_nhc_health_ok(nhc_config):
    service = NhcCycloneService(nhc_config)
    service.fetch_feed_xml = AsyncMock(
        return_value='<?xml version="1.0"?><rss><channel><item><description>no tropical cyclones</description></item></channel></rss>'
    )

    monitor = HealthMonitor(nhc_config, MagicMock())
    monitor.nhc_service = service

    result = await monitor.check_nhc_health({})
    assert result.status == ComponentStatus.HEALTHY
    assert result.name == "nhc_api"
    assert "no active tropical cyclones" in result.message.lower()


@pytest.mark.asyncio
async def test_check_nhc_health_missing_gps_position(nhc_config):
    nhc_config.geo_hazard_position.static_lat = None
    nhc_config.geo_hazard_position.static_lon = None
    mobile = MagicMock()
    mobile.get_position.return_value = None
    mobile.get_status.return_value = {
        "active": False,
        "reason": "no_fix",
    }

    service = NhcCycloneService(nhc_config, mobile)
    monitor = HealthMonitor(nhc_config, MagicMock())
    monitor.nhc_service = service

    result = await monitor.check_nhc_health({})
    assert result.status == ComponentStatus.DEGRADED
    assert "GPS position" in result.message


@pytest.mark.asyncio
async def test_check_nhc_health_feed_failure(nhc_config):
    service = NhcCycloneService(nhc_config)
    service.get_position = MagicMock(return_value=(29.95, -90.07))
    service.fetch_feed_xml = AsyncMock(return_value=None)
    service._last_error_message = "NHC feed fetch failed: timeout"

    monitor = HealthMonitor(nhc_config, MagicMock())
    monitor.nhc_service = service

    result = await monitor.check_nhc_health({})
    assert result.status == ComponentStatus.UNHEALTHY
    assert "fetch failed" in result.message.lower()


@pytest.mark.asyncio
async def test_get_health_status_includes_nhc_when_enabled(nhc_config):
    service = NhcCycloneService(nhc_config)
    service.check_health = AsyncMock(
        return_value={"ok": True, "message": "NHC feed OK", "details": {}}
    )

    monitor = HealthMonitor(nhc_config, MagicMock())
    monitor.nhc_service = service

    status = await monitor.get_health_status({})
    names = [c.name for c in status.components]
    assert "nhc_api" in names
    assert status.version == APP_VERSION


@pytest.mark.asyncio
async def test_get_health_status_version_matches_package():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        nhc=NhcConfig(enabled=False),
    )
    monitor = HealthMonitor(config, MagicMock())
    monitor.nws_client = MagicMock()
    monitor.nws_client.check_health = AsyncMock(
        return_value={"ok": True, "message": "ok", "details": {}}
    )

    status = await monitor.get_health_status({})
    assert status.version == APP_VERSION


@pytest.mark.asyncio
async def test_get_health_status_skips_nhc_when_disabled():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        nhc=NhcConfig(enabled=False),
    )
    monitor = HealthMonitor(config, MagicMock())
    monitor.nws_client = MagicMock()
    monitor.nws_client.test_connection = AsyncMock(return_value=True)
    monitor.audio_manager = None
    monitor.asterisk_manager = None
    monitor.script_manager = None
    monitor.database_manager = None

    status = await monitor.get_health_status({})
    names = [c.name for c in status.components]
    assert "nhc_api" not in names


def test_rollup_overall_status_ignores_unknown_components():
    statuses = [
        ComponentStatus.HEALTHY,
        ComponentStatus.UNKNOWN,
        ComponentStatus.UNKNOWN,
    ]
    assert rollup_overall_status(statuses) == ComponentStatus.HEALTHY


@pytest.mark.asyncio
async def test_get_health_status_healthy_when_optional_components_unknown():
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        nhc=NhcConfig(enabled=False),
    )
    monitor = HealthMonitor(config, MagicMock())
    monitor.nws_client = MagicMock()
    monitor.nws_client.test_connection = AsyncMock(return_value=True)
    monitor.audio_manager = MagicMock()
    monitor.audio_manager.tts_engine = MagicMock()
    monitor.audio_manager.tts_engine.is_available.return_value = True
    monitor.asterisk_manager = None
    monitor.script_manager = None
    monitor.database_manager = None

    status = await monitor.get_health_status({})
    assert status.overall_status == ComponentStatus.HEALTHY
