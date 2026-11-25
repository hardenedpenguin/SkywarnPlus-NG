"""All-clear notifications are sent even when a county has no display name."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from skywarnplus_ng.core.application import SkywarnPlusApplication
from skywarnplus_ng.core.config import AppConfig, CountyConfig, NWSApiConfig
from skywarnplus_ng.core.state import ApplicationState


@pytest.mark.asyncio
async def test_all_clear_notification_falls_back_to_county_code(tmp_path):
    config = AppConfig(
        nws=NWSApiConfig(user_agent="test"),
        data_dir=tmp_path / "data",
        counties=[
            CountyConfig(code="TXC039", name="Brazoria"),
            CountyConfig(code="TXC167"),
            CountyConfig(code="TXC201", name="Harris", enabled=False),
        ],
    )
    app = SkywarnPlusApplication(config)
    app.state_manager = ApplicationState(tmp_path / "state.json")
    app.state = app.state_manager.load_state()
    app.config.alerts.say_all_clear = False
    app.alert_logger = None
    app.notification_manager = MagicMock()
    app.notification_manager.send_all_clear_notifications = AsyncMock(
        return_value={"success": True}
    )

    await app._handle_all_clear()

    app.notification_manager.send_all_clear_notifications.assert_awaited_once_with(
        "Brazoria, TXC167"
    )
