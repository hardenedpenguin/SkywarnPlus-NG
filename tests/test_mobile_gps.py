"""Tests for gpsd mobile county monitoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from skywarnplus_ng.core.config import AppConfig, CountyConfig, GpsdConfig, NodeConfig
from skywarnplus_ng.location.gpsd import GpsFix
from skywarnplus_ng.location.mobile_counties import MobileCountyService


def _mobile_config() -> AppConfig:
    return AppConfig(
        counties=[
            CountyConfig(code="TXC039", name="Brazoria County", enabled=True),
            CountyConfig(code="TXC201", name="Galveston County", enabled=True),
        ],
        asterisk={
            "enabled": True,
            "nodes": [
                NodeConfig(number=546050, counties=["TXC039", "TXC201"], gps_controlled=True),
                NodeConfig(number=546051, counties=["TXC039"], gps_controlled=False),
            ],
        },
        gpsd=GpsdConfig(enabled=True, stale_seconds=900, hysteresis_polls=1),
    )


def _fix(**overrides) -> GpsFix:
    defaults = {
        "latitude": 29.7604,
        "longitude": -95.3698,
        "mode": 3,
        "accuracy_m": 10.0,
        "fix_time": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return GpsFix(**defaults)


@pytest.mark.asyncio
async def test_gps_active_overrides_mobile_node_counties():
    config = _mobile_config()
    nws = AsyncMock()
    nws.resolve_county_from_coordinates = AsyncMock(return_value=("TXC167", "Harris County"))
    service = MobileCountyService(config, nws)
    config.gpsd.hysteresis_polls = 1

    with patch(
        "skywarnplus_ng.location.mobile_counties.poll_gpsd_fix", AsyncMock(return_value=_fix())
    ):
        await service.refresh()

    assert service.is_gps_active()
    assert service.get_effective_counties_for_node(546050) == {"TXC167"}
    assert service.get_fetch_counties() == ["TXC039", "TXC167"]
    assert service.get_nodes_for_counties(["TXC167"]) == [546050]
    assert service.get_nodes_for_counties(["TXC039"]) == [546051]


@pytest.mark.asyncio
async def test_stale_gps_reverts_to_static_counties():
    config = _mobile_config()
    nws = AsyncMock()
    service = MobileCountyService(config, nws)
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=1200)

    with patch(
        "skywarnplus_ng.location.mobile_counties.poll_gpsd_fix",
        AsyncMock(return_value=_fix(fix_time=stale_time)),
    ):
        await service.refresh()

    assert not service.is_gps_active()
    assert service.get_effective_counties_for_node(546050) == {"TXC039", "TXC201"}
    assert service.get_fetch_counties() == ["TXC039", "TXC201"]


@pytest.mark.asyncio
async def test_hysteresis_requires_multiple_polls():
    config = _mobile_config()
    config.gpsd.hysteresis_polls = 2
    nws = AsyncMock()
    nws.resolve_county_from_coordinates = AsyncMock(
        side_effect=[
            ("TXC167", "Harris County"),
            ("TXC167", "Harris County"),
            ("TXC201", "Galveston County"),
            ("TXC201", "Galveston County"),
        ]
    )
    service = MobileCountyService(config, nws)

    with patch(
        "skywarnplus_ng.location.mobile_counties.poll_gpsd_fix", AsyncMock(return_value=_fix())
    ):
        await service.refresh()
        assert service.is_gps_active()
        assert service.active_gps_county_code == "TXC167"

        await service.refresh()
        assert service.active_gps_county_code == "TXC167"

        await service.refresh()
        assert service.active_gps_county_code == "TXC167"

        await service.refresh()
        assert service.active_gps_county_code == "TXC201"


@pytest.mark.asyncio
async def test_initial_county_lock_is_immediate_with_higher_hysteresis():
    config = _mobile_config()
    config.gpsd.hysteresis_polls = 3
    nws = AsyncMock()
    nws.resolve_county_from_coordinates = AsyncMock(return_value=("TXC167", "Harris County"))
    service = MobileCountyService(config, nws)

    with patch(
        "skywarnplus_ng.location.mobile_counties.poll_gpsd_fix", AsyncMock(return_value=_fix())
    ):
        await service.refresh()

    assert service.is_gps_active()
    assert service.active_gps_county_code == "TXC167"
    assert service.get_fetch_counties() == ["TXC039", "TXC167"]


@pytest.mark.asyncio
async def test_get_position_uses_fresh_fix_without_county_lock():
    service = MobileCountyService(_mobile_config(), AsyncMock())
    service._last_fix = _fix()
    assert service.get_position() == (29.7604, -95.3698)
    assert not service.is_gps_active()


@pytest.mark.asyncio
async def test_gps_only_node_silent_when_inactive():
    config = AppConfig(
        counties=[],
        asterisk={
            "enabled": True,
            "nodes": [NodeConfig(number=546050, counties=None, gps_controlled=True, gps_only=True)],
        },
        gpsd=GpsdConfig(enabled=True, hysteresis_polls=1),
    )
    nws = AsyncMock()
    service = MobileCountyService(config, nws)

    with patch(
        "skywarnplus_ng.location.mobile_counties.poll_gpsd_fix", AsyncMock(return_value=None)
    ):
        await service.refresh()

    assert not service.is_gps_active()
    assert service.get_effective_counties_for_node(546050) == set()
    assert service.get_fetch_counties() == []
    assert service.get_nodes_for_counties(["TXC039"]) == []


@pytest.mark.asyncio
async def test_gps_only_inferred_from_empty_counties():
    config = AppConfig(
        counties=[CountyConfig(code="TXC039", name="Brazoria County", enabled=True)],
        asterisk={
            "enabled": True,
            "nodes": [NodeConfig(number=546050, counties=None, gps_controlled=True)],
        },
        gpsd=GpsdConfig(enabled=True, hysteresis_polls=1),
    )
    nws = AsyncMock()
    service = MobileCountyService(config, nws)

    assert service.is_gps_only_node(546050)

    with patch(
        "skywarnplus_ng.location.mobile_counties.poll_gpsd_fix", AsyncMock(return_value=None)
    ):
        await service.refresh()

    assert service.get_effective_counties_for_node(546050) == set()
    assert service.get_nodes_for_counties(["TXC039"]) == []


@pytest.mark.asyncio
async def test_gps_only_active_without_global_counties_config():
    config = AppConfig(
        counties=[],
        asterisk={
            "enabled": True,
            "nodes": [NodeConfig(number=546050, gps_controlled=True, gps_only=True)],
        },
        gpsd=GpsdConfig(enabled=True, hysteresis_polls=1),
    )
    nws = AsyncMock()
    nws.resolve_county_from_coordinates = AsyncMock(return_value=("TXC167", "Harris County"))
    service = MobileCountyService(config, nws)

    with patch(
        "skywarnplus_ng.location.mobile_counties.poll_gpsd_fix", AsyncMock(return_value=_fix())
    ):
        await service.refresh()

    assert service.is_gps_active()
    assert service.get_fetch_counties() == ["TXC167"]
    assert service.get_nodes_for_counties(["TXC167"]) == [546050]
    assert "TXC167" in service.get_monitored_county_codes()


def test_gpsd_config_in_default_yaml():
    from pathlib import Path

    cfg = AppConfig.from_yaml(Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    assert cfg.gpsd.enabled is False
    assert cfg.gpsd.stale_seconds == 900
