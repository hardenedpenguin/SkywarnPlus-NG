"""Geo-hazard announcements are retried on nodes that missed playback."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from skywarnplus_ng.core.application import SkywarnPlusApplication
from skywarnplus_ng.core.config import AppConfig, NWSApiConfig
from skywarnplus_ng.core.state import ANNOUNCEMENT_RETRY_MAX_ATTEMPTS, ApplicationState

NODES = [1999, 2000]


class FakeQuakeService:
    def __init__(self, events):
        self.events = events
        self.marked: list[str] = []

    def should_poll(self):
        return True

    async def poll(self, state):
        return [e for e in self.events if e.announcement_key not in self.marked]

    def mark_announced(self, key, state):
        self.marked.append(key)


def _quake(key="us7000abcd"):
    return SimpleNamespace(
        announcement_key=key,
        event_id=key,
        magnitude=5.1,
        distance_miles=42,
        tts_text="Magnitude 5.1 earthquake 42 miles away.",
    )


def _make_app(tmp_path, play_results):
    app = SkywarnPlusApplication(
        AppConfig(nws=NWSApiConfig(user_agent="test"), data_dir=tmp_path / "data")
    )
    app.state_manager = ApplicationState(tmp_path / "state.json")
    app.state = app.state_manager.load_state()
    app.playback_policy = None
    app.config.asterisk.enabled = True
    app.config.asterisk.nodes = list(NODES)
    app.config.earthquake.enabled = True
    app.config.earthquake.announce_enabled = True
    audio = tmp_path / "quake.wav"
    audio.write_bytes(b"RIFF")
    app.audio_manager = MagicMock()
    app.audio_manager.generate_spoken_audio.return_value = audio
    app.asterisk_manager = MagicMock()
    app.asterisk_manager.play_audio_on_nodes = AsyncMock(side_effect=play_results)
    app._notify_geo_hazard_broadcast = AsyncMock()
    return app


def _retries(app):
    return app.state["geo_hazard_retries"]


def _make_due(app):
    for entry in _retries(app).values():
        entry["next_retry_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()


@pytest.mark.asyncio
async def test_partial_playback_retries_only_missed_nodes(tmp_path):
    app = _make_app(tmp_path, [[1999], [2000]])
    service = FakeQuakeService([_quake()])
    app.earthquake_service = service

    await app._handle_earthquake_events()
    assert service.marked == ["us7000abcd"]
    entry = _retries(app)["earthquake:us7000abcd"]
    assert entry["pending_nodes"] == [2000]
    assert entry["delivered_nodes"] == [1999]
    app._notify_geo_hazard_broadcast.assert_awaited_once()

    # Backoff not elapsed yet
    await app._retry_geo_hazard_nodes()
    assert app.asterisk_manager.play_audio_on_nodes.await_count == 1

    _make_due(app)
    await app._retry_geo_hazard_nodes()
    assert app.asterisk_manager.play_audio_on_nodes.await_args.args[1] == [2000]
    assert _retries(app) == {}
    # Broadcast notification is not repeated for node retries
    app._notify_geo_hazard_broadcast.assert_awaited_once()


@pytest.mark.asyncio
async def test_full_playback_schedules_no_retry(tmp_path):
    app = _make_app(tmp_path, [NODES])
    app.earthquake_service = FakeQuakeService([_quake()])
    await app._handle_earthquake_events()
    assert _retries(app) == {}


@pytest.mark.asyncio
async def test_complete_failure_is_left_for_next_poll(tmp_path):
    app = _make_app(tmp_path, [[], NODES])
    service = FakeQuakeService([_quake()])
    app.earthquake_service = service

    await app._handle_earthquake_events()
    assert service.marked == []
    assert _retries(app) == {}

    await app._handle_earthquake_events()
    assert service.marked == ["us7000abcd"]


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts(tmp_path):
    app = _make_app(tmp_path, [[1999]] + [[]] * ANNOUNCEMENT_RETRY_MAX_ATTEMPTS)
    app.earthquake_service = FakeQuakeService([_quake()])
    await app._handle_earthquake_events()

    for _ in range(ANNOUNCEMENT_RETRY_MAX_ATTEMPTS - 1):
        assert _retries(app)
        _make_due(app)
        await app._retry_geo_hazard_nodes()
    assert _retries(app) == {}
    assert app.asterisk_manager.play_audio_on_nodes.await_count == ANNOUNCEMENT_RETRY_MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_backoff_grows_between_attempts(tmp_path):
    app = _make_app(tmp_path, [[1999], [], []])
    app.earthquake_service = FakeQuakeService([_quake()])
    await app._handle_earthquake_events()
    _make_due(app)
    await app._retry_geo_hazard_nodes()
    entry = _retries(app)["earthquake:us7000abcd"]
    assert entry["attempts"] == 2
    wait = datetime.fromisoformat(entry["next_retry_at"]) - datetime.now(UTC)
    assert timedelta(seconds=50) < wait <= timedelta(seconds=60)


@pytest.mark.asyncio
async def test_retry_dropped_when_announcements_disabled(tmp_path):
    app = _make_app(tmp_path, [[1999]])
    app.earthquake_service = FakeQuakeService([_quake()])
    await app._handle_earthquake_events()

    app.config.earthquake.announce_enabled = False
    _make_due(app)
    await app._retry_geo_hazard_nodes()
    assert _retries(app) == {}
    assert app.asterisk_manager.play_audio_on_nodes.await_count == 1


@pytest.mark.asyncio
async def test_retry_dropped_during_quiet_hours(tmp_path):
    app = _make_app(tmp_path, [[1999]])
    app.earthquake_service = FakeQuakeService([_quake()])
    await app._handle_earthquake_events()

    app.playback_policy = MagicMock()
    app.playback_policy.should_announce_geo_hazard.return_value = (False, "quiet_hours")
    _make_due(app)
    await app._retry_geo_hazard_nodes()
    assert _retries(app) == {}
    assert app.asterisk_manager.play_audio_on_nodes.await_count == 1


@pytest.mark.asyncio
async def test_retry_skips_nodes_removed_from_config(tmp_path):
    app = _make_app(tmp_path, [[1999]])
    app.earthquake_service = FakeQuakeService([_quake()])
    await app._handle_earthquake_events()

    app.config.asterisk.nodes = [1999]
    _make_due(app)
    await app._retry_geo_hazard_nodes()
    assert _retries(app) == {}
    assert app.asterisk_manager.play_audio_on_nodes.await_count == 1


@pytest.mark.asyncio
async def test_announce_disabled_marks_without_playing(tmp_path):
    app = _make_app(tmp_path, [])
    app.config.earthquake.announce_enabled = False
    service = FakeQuakeService([_quake()])
    app.earthquake_service = service
    await app._handle_earthquake_events()
    assert service.marked == ["us7000abcd"]
    app.asterisk_manager.play_audio_on_nodes.assert_not_awaited()


@pytest.mark.asyncio
async def test_quiet_hours_skip_leaves_item_unmarked(tmp_path):
    app = _make_app(tmp_path, [])
    app.playback_policy = MagicMock()
    app.playback_policy.should_announce_geo_hazard.return_value = (False, "quiet_hours")
    service = FakeQuakeService([_quake()])
    app.earthquake_service = service
    await app._handle_earthquake_events()
    assert service.marked == []
    app.asterisk_manager.play_audio_on_nodes.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_state_survives_restart(tmp_path):
    app = _make_app(tmp_path, [[1999]])
    app.earthquake_service = FakeQuakeService([_quake()])
    await app._handle_earthquake_events()

    reloaded = ApplicationState(tmp_path / "state.json").load_state()
    assert reloaded["geo_hazard_retries"]["earthquake:us7000abcd"]["pending_nodes"] == [2000]


_ITEM = dict(
    announcement_key="k1",
    advisory_key="k1",
    event_id="k1",
    incident_id="k1",
    alert_id="k1",
    product_id="K1",
    vnum="k1",
    atcf="al012026",
    storm_type="Hurricane",
    name="Test",
    event="Tsunami Warning",
    title="G3 Watch",
    magnitude=5.0,
    distance_miles=10,
    tts_text="Test hazard.",
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "attr", "handler", "title"),
    [
        ("nhc", "nhc_service", "_handle_nhc_advisories", "Tropical Cyclone: Test"),
        ("earthquake", "earthquake_service", "_handle_earthquake_events", "Earthquake M5.0"),
        ("wildfire", "wildfire_service", "_handle_wildfire_incidents", "Wildfire: Test"),
        ("tsunami", "tsunami_service", "_handle_tsunami_alerts", "Tsunami: Tsunami Warning"),
        (
            "space_weather",
            "space_weather_service",
            "_handle_space_weather_alerts",
            "Space Weather: G3 Watch",
        ),
        ("volcano", "volcano_service", "_handle_volcano_notices", "Volcano: Test"),
    ],
)
async def test_every_hazard_feed_announces_and_queues_missed_nodes(
    tmp_path, kind, attr, handler, title
):
    app = _make_app(tmp_path, [[1999], [2000]])
    getattr(app.config, kind).enabled = True
    service = FakeQuakeService([SimpleNamespace(**_ITEM)])
    service.audio_prefix_for = lambda incident_id: f"wildfire_{incident_id}"
    setattr(app, attr, service)

    await getattr(app, handler)()

    assert service.marked == ["k1"]
    assert _retries(app)[f"{kind}:k1"]["pending_nodes"] == [2000]
    assert app._notify_geo_hazard_broadcast.await_args.kwargs["title"] == title

    _make_due(app)
    await app._retry_geo_hazard_nodes()
    assert _retries(app) == {}
    assert app.asterisk_manager.play_audio_on_nodes.await_args.args[1] == [2000]
