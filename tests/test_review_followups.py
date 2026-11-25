"""Regression tests for review follow-ups on announcements, geo hazards, and session keys."""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from test_announcement_retry import NODES, _alert, _make_retry_due
from test_announcement_retry import _make_app as _make_alert_app
from test_geo_hazard_node_retry import FakeQuakeService, _quake
from test_geo_hazard_node_retry import _make_app as _make_geo_app

from skywarnplus_ng.asterisk.manager import (
    PLAYBACK_COMMAND_TIMEOUT_SECONDS,
    AsteriskManager,
)
from skywarnplus_ng.core.state import ApplicationState
from skywarnplus_ng.web.server import load_or_create_session_key


def _outcome(app, alert_id):
    return app.state_manager.get_announcement_outcome(app.state, alert_id)


# --- Geo hazards -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_geo_voice_setting_is_read_after_the_feed_poll(tmp_path):
    app = _make_geo_app(tmp_path, [list(NODES)])
    service = FakeQuakeService([_quake()])
    original_poll = service.poll

    async def poll_then_disable(state):
        items = await original_poll(state)
        # Operator turns voice off while the feed request is in flight
        app.config.earthquake.announce_enabled = False
        return items

    service.poll = poll_then_disable
    app.earthquake_service = service

    await app._handle_earthquake_events()

    app.asterisk_manager.play_audio_on_nodes.assert_not_awaited()
    assert service.marked == ["us7000abcd"]


@pytest.mark.asyncio
async def test_geo_retry_dropped_once_hazard_exceeds_max_age(tmp_path):
    app = _make_geo_app(tmp_path, [[1999], [2000]])
    quake = _quake()
    quake.time_utc = datetime.now(UTC) - timedelta(hours=1)
    app.earthquake_service = FakeQuakeService([quake])
    await app._handle_earthquake_events()
    entry = app.state["geo_hazard_retries"]["earthquake:us7000abcd"]
    assert entry["issued_at"] == quake.time_utc.isoformat()

    # The event is now older than the configured maximum age
    entry["issued_at"] = (
        datetime.now(UTC) - timedelta(hours=app.config.earthquake.max_event_age_hours + 1)
    ).isoformat()
    entry["next_retry_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    await app._retry_geo_hazard_nodes()

    assert app.asterisk_manager.play_audio_on_nodes.await_count == 1
    assert app.state["geo_hazard_retries"] == {}


@pytest.mark.asyncio
async def test_geo_retry_kept_while_hazard_is_current(tmp_path):
    app = _make_geo_app(tmp_path, [[1999], [2000]])
    quake = _quake()
    quake.time_utc = datetime.now(UTC) - timedelta(minutes=5)
    app.earthquake_service = FakeQuakeService([quake])
    await app._handle_earthquake_events()
    entry = app.state["geo_hazard_retries"]["earthquake:us7000abcd"]
    entry["next_retry_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

    await app._retry_geo_hazard_nodes()

    assert app.asterisk_manager.play_audio_on_nodes.await_args.args[1] == [2000]


def _poll_cycle_app(tmp_path):
    app = _make_alert_app(tmp_path, [])
    app.mobile_county_service = MagicMock()
    app.mobile_county_service.refresh = AsyncMock()
    app._update_geographic_filter = MagicMock()
    app.web_dashboard = None
    app._run_geo_hazard_feeds = AsyncMock()
    app._process_alerts = AsyncMock()
    return app


@pytest.mark.asyncio
async def test_geo_hazards_still_run_when_nws_fetch_fails(tmp_path):
    app = _poll_cycle_app(tmp_path)
    app.mobile_county_service.get_fetch_counties.return_value = ["TXC039"]
    app._fetch_alerts = AsyncMock(return_value=None)

    await app._poll_cycle()

    app._process_alerts.assert_not_awaited()
    app._run_geo_hazard_feeds.assert_awaited_once()


@pytest.mark.asyncio
async def test_geo_hazards_still_run_without_monitored_counties(tmp_path):
    app = _poll_cycle_app(tmp_path)
    app.mobile_county_service.get_fetch_counties.return_value = []

    await app._poll_cycle()

    app._run_geo_hazard_feeds.assert_awaited_once()


# --- Asterisk playback -------------------------------------------------------------------


def _asterisk(tmp_path, result):
    manager = AsteriskManager.__new__(AsteriskManager)
    manager.config = SimpleNamespace(playback_mode="local")
    manager.delivery_observer = None
    manager._run_asterisk_command = AsyncMock(return_value=result)
    audio = tmp_path / "alert.ulaw"
    audio.write_bytes(b"\x00\x01")
    return manager, audio


@pytest.mark.asyncio
async def test_playback_waits_for_cli_result(tmp_path):
    manager, audio = _asterisk(tmp_path, (0, "", ""))
    assert await manager.play_audio_on_node(1999, audio) is True
    kwargs = manager._run_asterisk_command.await_args.kwargs
    assert kwargs.get("wait", True) is True
    assert kwargs["timeout"] == PLAYBACK_COMMAND_TIMEOUT_SECONDS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        (1, "", "sudo: a password is required"),
        (0, "No such command 'rpt localplay 1999 /tmp/x'", ""),
        (0, "Unable to connect to remote asterisk", ""),
        (-1, "", "timed out"),
    ],
)
async def test_playback_failure_is_not_reported_as_played(tmp_path, result):
    manager, audio = _asterisk(tmp_path, result)
    assert await manager.play_audio_on_node(1999, audio) is False


@pytest.mark.asyncio
async def test_run_asterisk_command_times_out(tmp_path, monkeypatch):
    manager = AsteriskManager.__new__(AsteriskManager)
    manager.asterisk_path = tmp_path / "asterisk"

    class SlowProcess:
        returncode = None
        killed = False

        async def communicate(self):
            import asyncio

            await asyncio.sleep(5)
            return b"", b""

        def kill(self):
            self.killed = True

        async def wait(self):
            return -9

    proc = SlowProcess()
    monkeypatch.setattr(
        "skywarnplus_ng.asterisk.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    )
    result = await manager._run_asterisk_command("rpt localplay 1999 x", timeout=0.01)
    assert result == (-1, "", "timed out")
    assert proc.killed


# --- NWS announcement outcomes ------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_metadata_cleared_when_no_targets_remain(tmp_path):
    app = _make_alert_app(tmp_path, [[1999]])
    alert = _alert()
    await app._process_alerts([alert])
    assert "retry" in _outcome(app, alert.id)

    # Node 2000 no longer monitors this alert's counties
    app._target_nodes_for_alert = MagicMock(return_value=[1999])
    _make_retry_due(app, alert.id)
    await app._process_alerts([alert])

    assert alert.id not in app.state["announcement_retries"]
    assert "retry" not in _outcome(app, alert.id)


def test_clear_announcement_retry_drops_outcome_retry_block(tmp_path):
    manager = ApplicationState(tmp_path / "state.json")
    state = manager.load_state()
    manager.schedule_announcement_retry(state, "a", [2000], delivered_nodes=[1999])
    manager.set_announcement_outcome(state, "a", {"status": "partial", "retry": {"attempt": 1}})

    manager.clear_announcement_retry(state, "a")

    assert manager.get_announcement_retry(state, "a") is None
    assert "retry" not in manager.get_announcement_outcome(state, "a")


def _real_announce_app(tmp_path, play_result):
    app = _make_alert_app(tmp_path, [])
    del app._announce_alert  # use the real implementation
    audio = tmp_path / "alert.wav"
    audio.write_bytes(b"RIFF")
    app.audio_manager.generate_alert_audio.return_value = audio
    app.asterisk_manager.play_audio_on_nodes = AsyncMock(return_value=play_result)
    app.config.alerts.with_multiples = False
    return app


@pytest.mark.asyncio
async def test_alert_expiring_during_tts_is_not_played(tmp_path):
    app = _real_announce_app(tmp_path, list(NODES))
    app.nws_client = MagicMock()
    app.nws_client.filter_active_alerts.return_value = []
    alert = _alert()

    nodes = await app._announce_alert(alert)
    app._record_announcement_outcome(alert, nodes)

    assert nodes == []
    app.asterisk_manager.play_audio_on_nodes.assert_not_awaited()
    outcome = _outcome(app, alert.id)
    assert outcome["status"] == "skipped"
    assert outcome["reason"] == "expired"
    assert alert.id not in app.state.get("announcement_retries", {})


@pytest.mark.asyncio
async def test_outcome_uses_nodes_the_playback_attempted(tmp_path):
    app = _real_announce_app(tmp_path, [])
    app.nws_client = None
    app._target_nodes_for_alert = MagicMock(return_value=[1999])
    alert = _alert()

    nodes = await app._announce_alert(alert)
    # County-to-node mapping changes after playback (for example a GPS county change)
    app._target_nodes_for_alert = MagicMock(return_value=list(NODES))
    app._record_announcement_outcome(alert, nodes)

    outcome = _outcome(app, alert.id)
    assert outcome["failed_nodes"] == [1999]
    assert app.state["announcement_retries"][alert.id]["pending_nodes"] == [1999]


@pytest.mark.asyncio
async def test_failed_and_given_up_retries_are_stored_in_history(tmp_path):
    app = _make_alert_app(tmp_path, [[]] * 5)
    app.database_manager = MagicMock()
    app.database_manager.store_alert = AsyncMock()
    alert = _alert()
    await app._process_alerts([alert])
    for _ in range(4):
        _make_retry_due(app, alert.id)
        app.database_manager.store_alert.reset_mock()
        await app._process_alerts([alert])
        stored = [
            c.kwargs["announcement_outcome"]
            for c in app.database_manager.store_alert.await_args_list
            if c.kwargs.get("announcement_outcome")
        ]
        assert stored and stored[-1]["status"] == "failed"

    assert stored[-1].get("gave_up") is True


@pytest.mark.asyncio
async def test_county_change_announcement_is_stored_in_history(tmp_path):
    app = _make_alert_app(tmp_path, [[1999]])
    app.database_manager = MagicMock()
    app.database_manager.store_alert = AsyncMock()
    alert = _alert()

    await app._handle_alerts_with_changes([alert])

    kwargs = app.database_manager.store_alert.await_args.kwargs
    assert kwargs["announcement_nodes"] == [1999]
    assert kwargs["announcement_outcome"]["status"] == "partial"


def test_alias_merge_unions_delivered_nodes(tmp_path):
    manager = ApplicationState(tmp_path / "state.json")
    state = manager.load_state()
    state["announcement_retries"] = {
        "old": {"pending_nodes": [2000, 2001], "delivered_nodes": [1999]},
        "new": {"pending_nodes": [1999], "delivered_nodes": [2001]},
    }

    manager._migrate_alert_id_references(state, "old", "new")

    merged = state["announcement_retries"]["new"]
    assert merged["delivered_nodes"] == [1999, 2001]
    assert merged["pending_nodes"] == [2000]


# --- Session key -------------------------------------------------------------------------


def test_non_utf8_session_key_file_is_replaced(tmp_path):
    path = tmp_path / "session_secret.key"
    path.write_bytes(b"\xff\xfe\x00garbage")

    key = load_or_create_session_key(path)

    assert len(bytes.fromhex(key)) == 32
    assert path.read_text(encoding="utf-8").strip() == key


def test_existing_session_key_permissions_are_tightened(tmp_path):
    path = tmp_path / "session_secret.key"
    key = "ab" * 32
    path.write_text(key + "\n", encoding="utf-8")
    os.chmod(path, 0o644)

    assert load_or_create_session_key(path) == key
    assert path.stat().st_mode & 0o777 == 0o600
