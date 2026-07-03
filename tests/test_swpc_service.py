"""Tests for NOAA SWPC space weather service."""

from __future__ import annotations

from datetime import datetime, timezone

from skywarnplus_ng.core.config import AppConfig
from skywarnplus_ng.spaceweather.parser import ParsedSpaceWeather
from skywarnplus_ng.spaceweather.swpc_service import DISPLAY_TRACKED_LIMIT, SwpcSpaceWeatherService


def _parsed_alert(index: int) -> ParsedSpaceWeather:
    issued = datetime(2026, 7, 1, index, 0, 0, tzinfo=timezone.utc)
    return ParsedSpaceWeather(
        product_id=f"P{index}",
        title=f"Alert {index}",
        message=f"ALERT: Test {index}",
        message_type="alert",
        geomagnetic_scale=0,
        radio_blackout_scale=0,
        solar_radiation_scale=0,
        announcement_key=f"P{index}:2026-07-01:0{index}:00:00",
        issued_utc=issued,
        tts_text=f"Alert {index}",
    )


def test_select_new_alerts_limits_tracked_to_five_most_recent() -> None:
    config = AppConfig()
    config.space_weather.enabled = True
    service = SwpcSpaceWeatherService(config)

    alerts = [_parsed_alert(i) for i in range(10)]
    alerts.sort(key=lambda alert: alert.issued_utc, reverse=True)

    selected = service.select_new_alerts(alerts, {})

    assert len(service._tracked_alerts) == DISPLAY_TRACKED_LIMIT
    assert len(selected) == 10
    assert service._tracked_alerts[0]["title"] == "Alert 9"
    assert service._tracked_alerts[-1]["title"] == "Alert 5"


def test_passes_filters_ignores_unset_scales() -> None:
    config = AppConfig()
    config.space_weather.enabled = True
    config.space_weather.min_geomagnetic_scale = 2
    config.space_weather.min_radio_blackout_scale = 1
    service = SwpcSpaceWeatherService(config)

    radio_only = ParsedSpaceWeather(
        product_id="ALTTP2",
        title="ALERT: Radio Blackout R3",
        message="ALERT: Radio Blackout R3",
        message_type="alert",
        geomagnetic_scale=0,
        radio_blackout_scale=3,
        solar_radiation_scale=0,
        announcement_key="ALTTP2:2026-07-01:12:00:00",
        issued_utc=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        tts_text="Radio Blackout R3",
    )

    assert service._passes_filters(radio_only) is True
