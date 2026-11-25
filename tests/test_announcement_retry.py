"""Regression tests: failed voice announcements are retried on later polls."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from skywarnplus_ng.core.application import SkywarnPlusApplication
from skywarnplus_ng.core.config import AppConfig, NWSApiConfig
from skywarnplus_ng.core.models import AlertSeverity, AlertUrgency, WeatherAlert
from skywarnplus_ng.core.state import ANNOUNCEMENT_RETRY_MAX_ATTEMPTS, ApplicationState

NODES = [1999, 2000]


def _alert(alert_id: str = "urn:test:1", event: str = "Tornado Warning") -> WeatherAlert:
    now = datetime.now(UTC)
    return WeatherAlert(
        id=alert_id,
        event=event,
        description="Test",
        severity=AlertSeverity.EXTREME,
        urgency=AlertUrgency.IMMEDIATE,
        sent=now,
        effective=now,
        expires=now + timedelta(hours=1),
        county_codes=["TXC039"],
        area_desc="Brazoria, TX",
        sender="test",
        sender_name="NWS",
    )


def _make_app(tmp_path: Path, announce_results: list[list[int]]) -> SkywarnPlusApplication:
    app = SkywarnPlusApplication(
        AppConfig(nws=NWSApiConfig(user_agent="test"), data_dir=tmp_path / "data")
    )
    app.state_manager = ApplicationState(tmp_path / "state.json")
    app.state = app.state_manager.load_state()
    app.alert_pipeline = None
    app.script_manager = None
    app.database_manager = None
    app.mobile_county_service = None
    app.playback_policy = None
    app.notification_manager = None
    app.audio_manager = MagicMock()
    app.asterisk_manager = MagicMock()
    app.config.asterisk.enabled = True
    app.config.asterisk.nodes = NODES
    app._target_nodes_for_alert = MagicMock(return_value=list(NODES))
    app._send_alert_notifications = AsyncMock()
    app._announce_alert = AsyncMock(side_effect=announce_results)
    return app


def _make_retry_due(app: SkywarnPlusApplication, alert_id: str) -> None:
    entry = app.state["announcement_retries"][alert_id]
    entry["next_retry_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()


@pytest.mark.asyncio
async def test_failed_announcement_is_retried_after_backoff(tmp_path):
    app = _make_app(tmp_path, [[], NODES])
    alert = _alert()

    await app._process_alerts([alert])
    assert alert.id not in app.state["last_sayalert"]
    assert app.state["announcement_retries"][alert.id]["pending_nodes"] == NODES

    # Backoff not elapsed: no retry yet
    await app._process_alerts([alert])
    assert app._announce_alert.await_count == 1

    _make_retry_due(app, alert.id)
    await app._process_alerts([alert])

    assert app._announce_alert.await_count == 2
    assert app._announce_alert.await_args.kwargs["only_nodes"] == NODES
    assert alert.id in app.state["last_sayalert"]
    assert alert.id not in app.state["announcement_retries"]


@pytest.mark.asyncio
async def test_partial_node_failure_retries_only_failed_nodes(tmp_path):
    app = _make_app(tmp_path, [[1999], [2000]])
    alert = _alert()

    await app._process_alerts([alert])
    assert alert.id in app.state["last_sayalert"]
    entry = app.state["announcement_retries"][alert.id]
    assert entry["pending_nodes"] == [2000]
    assert entry["delivered_nodes"] == [1999]

    _make_retry_due(app, alert.id)
    await app._process_alerts([alert])

    assert app._announce_alert.await_args.kwargs["only_nodes"] == [2000]
    assert alert.id not in app.state["announcement_retries"]


@pytest.mark.asyncio
async def test_retry_entry_pruned_when_alert_expires(tmp_path):
    app = _make_app(tmp_path, [[]])
    alert = _alert()

    await app._process_alerts([alert])
    assert alert.id in app.state["announcement_retries"]

    await app._process_alerts([])
    assert alert.id not in app.state["announcement_retries"]


@pytest.mark.asyncio
async def test_retry_dropped_when_event_becomes_blocked(tmp_path):
    app = _make_app(tmp_path, [[]])
    alert = _alert()

    await app._process_alerts([alert])
    app.config.filtering.say_alert_blocked = ["Tornado*"]
    _make_retry_due(app, alert.id)
    await app._process_alerts([alert])

    assert app._announce_alert.await_count == 1
    assert alert.id not in app.state["announcement_retries"]


@pytest.mark.asyncio
async def test_no_retry_when_asterisk_disabled(tmp_path):
    app = _make_app(tmp_path, [[]])
    app.config.asterisk.enabled = False
    alert = _alert()

    await app._process_alerts([alert])
    assert alert.id not in app.state.get("announcement_retries", {})


@pytest.mark.asyncio
async def test_retry_waits_during_quiet_hours(tmp_path):
    app = _make_app(tmp_path, [[], NODES])
    alert = _alert()
    alert.severity = AlertSeverity.MINOR

    await app._process_alerts([alert])
    policy = MagicMock()
    policy.is_quiet_hours_active.return_value = True
    app.playback_policy = policy
    app.config.alerts.quiet_hours.allow_severe = False
    _make_retry_due(app, alert.id)
    await app._process_alerts([alert])

    assert app._announce_alert.await_count == 1
    assert alert.id in app.state["announcement_retries"]

    policy.is_quiet_hours_active.return_value = False
    await app._process_alerts([alert])
    assert app._announce_alert.await_count == 2
    assert alert.id not in app.state["announcement_retries"]


def test_retry_gives_up_after_max_attempts(tmp_path):
    mgr = ApplicationState(tmp_path / "state.json")
    state = mgr.load_state()
    for _ in range(ANNOUNCEMENT_RETRY_MAX_ATTEMPTS - 1):
        assert mgr.schedule_announcement_retry(state, "a", [1])
    assert not mgr.schedule_announcement_retry(state, "a", [1])
    assert "a" not in state["announcement_retries"]


def test_retry_backoff_grows_and_caps(tmp_path):
    mgr = ApplicationState(tmp_path / "state.json")
    state = mgr.load_state()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    delays = []
    for _ in range(4):
        mgr.schedule_announcement_retry(state, "a", [1], now=now)
        nxt = datetime.fromisoformat(state["announcement_retries"]["a"]["next_retry_at"])
        delays.append((nxt - now).total_seconds())
    assert delays == [30, 60, 120, 240]
    assert mgr.get_due_announcement_retries(state, now=now) == {}
    assert "a" in mgr.get_due_announcement_retries(state, now=now + timedelta(seconds=240))


@pytest.mark.asyncio
async def test_retry_skipped_and_cleared_when_alert_expired_since_fetch(tmp_path):
    from skywarnplus_ng.api.nws_client import NWSClient

    app = _make_app(tmp_path, [[]])
    app.nws_client = NWSClient(app.config.nws)
    alert = _alert()

    await app._process_alerts([alert])
    alert.expires = datetime.now(UTC) - timedelta(seconds=1)
    alert.ends = None
    _make_retry_due(app, alert.id)
    await app._retry_failed_announcements([alert])

    assert app._announce_alert.await_count == 1
    assert alert.id not in app.state["announcement_retries"]


def test_alias_migration_merges_pending_nodes(tmp_path):
    mgr = ApplicationState(tmp_path / "state.json")
    state = mgr.load_state()
    state["announcement_retries"] = {
        "canon": {
            "attempts": 2,
            "next_retry_at": "2026-01-01T00:10:00+00:00",
            "pending_nodes": [1],
            "delivered_nodes": [2],
        },
        "alias": {
            "attempts": 1,
            "next_retry_at": "2026-01-01T00:01:00+00:00",
            "pending_nodes": [2, 3],
            "delivered_nodes": [],
        },
    }
    mgr.update_alert_id_aliases(state, {"alias": "canon"})

    entry = state["announcement_retries"]["canon"]
    assert "alias" not in state["announcement_retries"]
    assert entry["pending_nodes"] == [1, 3]
    assert entry["attempts"] == 2
    assert entry["next_retry_at"] == "2026-01-01T00:10:00+00:00"


def test_alias_migration_moves_entry_when_canonical_has_none(tmp_path):
    mgr = ApplicationState(tmp_path / "state.json")
    state = mgr.load_state()
    entry = {"attempts": 1, "next_retry_at": None, "pending_nodes": [5], "delivered_nodes": []}
    state["announcement_retries"] = {"alias": dict(entry)}
    mgr.update_alert_id_aliases(state, {"alias": "canon"})
    assert state["announcement_retries"] == {"canon": entry}


@pytest.mark.asyncio
async def test_store_alert_refresh_preserves_announcement_nodes(tmp_path):
    from skywarnplus_ng.database.manager import DatabaseManager

    config = AppConfig(nws=NWSApiConfig(user_agent="test"), data_dir=tmp_path)
    db = DatabaseManager(config)
    await db.initialize()
    try:
        alert = _alert()
        await db.store_alert(alert, announced=True, announcement_nodes=[1999, 2000])
        # Snapshot refresh path omits announcement_nodes
        await db.store_alert(alert, announced=True)
        record = await db.get_alert(alert.id)
        assert record.announcement_nodes == [1999, 2000]

        await db.store_alert(alert, announced=False, announcement_nodes=[])
        record = await db.get_alert(alert.id)
        assert record.announcement_nodes == []
    finally:
        await db.close()
