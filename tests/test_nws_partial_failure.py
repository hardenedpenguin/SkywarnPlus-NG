"""Partial NWS zone-fetch failures must not discard alerts from successful zones."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from skywarnplus_ng.api.nws_client import NWSClient, NWSClientError
from skywarnplus_ng.core.config import NWSApiConfig
from skywarnplus_ng.core.models import WeatherAlert


def _alert(alert_id: str, county: str) -> WeatherAlert:
    now = datetime.now(timezone.utc)
    return WeatherAlert(
        id=alert_id,
        event="Flood Advisory",
        description="Test",
        sent=now,
        effective=now,
        expires=now,
        area_desc=county,
        county_codes=[county],
        sender="test",
        sender_name="NWS",
    )


@pytest.fixture
def client() -> NWSClient:
    return NWSClient(NWSApiConfig())


@pytest.mark.asyncio
async def test_partial_zone_failure_returns_successful_zones(client: NWSClient) -> None:
    async def fake_fetch(zone: str):
        if zone == "TXC201":
            raise NWSClientError("HTTP error: 500")
        return [_alert(f"alert-{zone}", zone)]

    client.fetch_alerts_for_zone = AsyncMock(side_effect=fake_fetch)

    alerts, failed = await client.fetch_alerts_for_zones(["TXC039", "TXC201", "TXC167"])
    assert failed == ["TXC201"]
    assert {a.id for a in alerts} == {"alert-TXC039", "alert-TXC167"}


@pytest.mark.asyncio
async def test_all_zones_failing_raises(client: NWSClient) -> None:
    client.fetch_alerts_for_zone = AsyncMock(side_effect=NWSClientError("HTTP error: 500"))

    with pytest.raises(NWSClientError):
        await client.fetch_alerts_for_zones(["TXC039", "TXC201"])


@pytest.mark.asyncio
async def test_no_failures_returns_empty_failed_list(client: NWSClient) -> None:
    client.fetch_alerts_for_zone = AsyncMock(return_value=[_alert("a1", "TXC039")])

    alerts, failed = await client.fetch_alerts_for_zones(["TXC039"])
    assert failed == []
    assert [a.id for a in alerts] == ["a1"]
