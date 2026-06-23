"""Tests for geo hazard broadcast notifications."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from skywarnplus_ng.core.application import SkywarnPlusApplication
from skywarnplus_ng.core.config import AppConfig, NWSApiConfig


@pytest.fixture
def app_config(tmp_path: Path):
    return AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        data_dir=tmp_path / "data",
    )


@pytest.mark.asyncio
async def test_notify_geo_hazard_broadcast_calls_manager(app_config):
    app = SkywarnPlusApplication(app_config)
    app.notification_manager = MagicMock()
    app.notification_manager.send_broadcast_notification = AsyncMock(return_value={"success": True})

    await app._notify_geo_hazard_broadcast(title="Earthquake M4.2", message="Test message")

    app.notification_manager.send_broadcast_notification.assert_awaited_once_with(
        "Earthquake M4.2",
        "Test message",
    )


@pytest.mark.asyncio
async def test_notify_geo_hazard_broadcast_no_manager(app_config):
    app = SkywarnPlusApplication(app_config)
    app.notification_manager = None
    await app._notify_geo_hazard_broadcast(title="Test", message="Test")
