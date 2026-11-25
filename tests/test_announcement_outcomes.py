"""Tests for announcement outcome tracking and per-node delivery health."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from test_announcement_retry import NODES, _alert, _make_app, _make_retry_due

from skywarnplus_ng.core.config import AppConfig, NWSApiConfig
from skywarnplus_ng.core.state import ApplicationState
from skywarnplus_ng.monitoring.health import ComponentStatus, HealthMonitor
from skywarnplus_ng.web.alert_payload import _enrich_alert_payload


def _outcome(app, alert_id):
    return app.state_manager.get_announcement_outcome(app.state, alert_id)


@pytest.mark.asyncio
async def test_outcome_played_on_all_nodes(tmp_path):
    app = _make_app(tmp_path, [NODES])
    alert = _alert()
    await app._process_alerts([alert])

    outcome = _outcome(app, alert.id)
    assert outcome["status"] == "played"
    assert outcome["reason"] is None
    assert outcome["played_nodes"] == NODES
    assert outcome["nodes"] == {"1999": "played", "2000": "played"}
    assert "retry" not in outcome


@pytest.mark.asyncio
async def test_outcome_partial_then_played_after_retry(tmp_path):
    app = _make_app(tmp_path, [[1999], [2000]])
    alert = _alert()
    await app._process_alerts([alert])

    outcome = _outcome(app, alert.id)
    assert outcome["status"] == "partial"
    assert outcome["reason"] == "playback_failed"
    assert outcome["failed_nodes"] == [2000]
    assert outcome["retry"]["attempt"] == 1
    assert outcome["retry"]["max_attempts"] == 5

    _make_retry_due(app, alert.id)
    await app._process_alerts([alert])
    outcome = _outcome(app, alert.id)
    assert outcome["status"] == "played"
    assert outcome["played_nodes"] == NODES
    assert "retry" not in outcome


@pytest.mark.asyncio
async def test_outcome_failure_reason_comes_from_announce(tmp_path):
    app = _make_app(tmp_path, [[]])

    async def fail_audio(alert, only_nodes=None):
        app._last_announce_failure = "audio_failed"
        return []

    app._announce_alert = AsyncMock(side_effect=fail_audio)
    alert = _alert()
    await app._process_alerts([alert])

    outcome = _outcome(app, alert.id)
    assert outcome["status"] == "failed"
    assert outcome["reason"] == "audio_failed"
    assert outcome["failed_nodes"] == NODES


@pytest.mark.asyncio
async def test_outcome_gave_up_after_max_attempts(tmp_path):
    app = _make_app(tmp_path, [[]] * 5)
    alert = _alert()
    await app._process_alerts([alert])
    for _ in range(4):
        _make_retry_due(app, alert.id)
        await app._process_alerts([alert])

    outcome = _outcome(app, alert.id)
    assert outcome["status"] == "failed"
    assert outcome["gave_up"] is True
    assert alert.id not in app.state["announcement_retries"]


@pytest.mark.asyncio
async def test_outcome_skipped_when_event_blocked(tmp_path):
    app = _make_app(tmp_path, [])
    app.config.filtering.say_alert_blocked = ["Tornado*"]
    alert = _alert()
    await app._process_alerts([alert])

    app._announce_alert.assert_not_awaited()
    outcome = _outcome(app, alert.id)
    assert outcome["status"] == "skipped"
    assert outcome["reason"] == "blocked_event"


@pytest.mark.asyncio
async def test_outcome_skipped_for_quiet_hours(tmp_path):
    app = _make_app(tmp_path, [])
    policy = MagicMock()
    policy.should_announce_voice.return_value = (False, "quiet_hours")
    app.playback_policy = policy
    alert = _alert()
    await app._process_alerts([alert])

    outcome = _outcome(app, alert.id)
    assert outcome["status"] == "skipped"
    assert outcome["reason"] == "quiet_hours"


@pytest.mark.asyncio
async def test_outcome_delivery_not_configured(tmp_path):
    app = _make_app(tmp_path, [[]])
    app.config.asterisk.enabled = False
    alert = _alert()
    await app._process_alerts([alert])

    outcome = _outcome(app, alert.id)
    assert outcome["status"] == "skipped"
    assert outcome["reason"] == "delivery_not_configured"


@pytest.mark.asyncio
async def test_outcome_pruned_on_expiry_and_exposed_in_payload(tmp_path):
    app = _make_app(tmp_path, [NODES])
    alert = _alert()
    await app._process_alerts([alert])

    payload = _enrich_alert_payload({"id": alert.id}, app.state)
    assert payload["announcement_outcome"]["status"] == "played"

    await app._process_alerts([])
    assert _outcome(app, alert.id) is None
    assert _enrich_alert_payload({"id": alert.id}, app.state)["announcement_outcome"] is None


def test_record_node_delivery_tracks_success_and_failures(tmp_path):
    mgr = ApplicationState(tmp_path / "state.json")
    state = mgr.load_state()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    mgr.record_node_delivery(state, [1, 2], [1], now=t0)
    mgr.record_node_delivery(state, [1, 2], [1], now=t0 + timedelta(minutes=1))
    assert state["node_delivery"]["2"]["consecutive_failures"] == 2
    assert state["node_delivery"]["2"]["total_failures"] == 2
    assert state["node_delivery"]["1"]["total_success"] == 2

    mgr.record_node_delivery(state, [2], [2], now=t0 + timedelta(minutes=2))
    assert state["node_delivery"]["2"]["consecutive_failures"] == 0
    assert state["node_delivery"]["2"]["last_success_at"] == (t0 + timedelta(minutes=2)).isoformat()


@pytest.mark.asyncio
async def test_asterisk_manager_reports_to_delivery_observer(tmp_path, monkeypatch):
    from skywarnplus_ng.asterisk.manager import AsteriskManager
    from skywarnplus_ng.core.config import AsteriskConfig

    monkeypatch.setattr(AsteriskManager, "_validate_asterisk", lambda self: None)
    manager = AsteriskManager(AsteriskConfig(enabled=True, nodes=[1, 2]))
    manager.play_audio_on_node = AsyncMock(side_effect=[True, False])
    seen = []
    manager.delivery_observer = lambda attempted, ok: seen.append((attempted, ok))

    result = await manager.play_audio_on_nodes(tmp_path / "a.ulaw", [1, 2])
    assert result == [1]
    assert seen == [([1, 2], [1])]


def _monitor(nodes):
    config = AppConfig(nws=NWSApiConfig(user_agent="test"))
    config.asterisk.enabled = True
    config.asterisk.nodes = nodes
    monitor = HealthMonitor(config, datetime.now(UTC))
    monitor.asterisk_manager = MagicMock()
    return monitor


@pytest.mark.asyncio
async def test_delivery_health_statuses():
    monitor = _monitor([1, 2])

    comp = await monitor.check_announcement_delivery_health({})
    assert comp.status == ComponentStatus.HEALTHY
    assert comp.message == "No playback attempted yet"

    ok = {"last_success_at": "2026-01-01T00:00:00+00:00", "consecutive_failures": 0}
    bad = {"last_failure_at": "2026-01-01T00:00:00+00:00", "consecutive_failures": 3}

    comp = await monitor.check_announcement_delivery_health({"node_delivery": {"1": ok, "2": ok}})
    assert comp.status == ComponentStatus.HEALTHY

    comp = await monitor.check_announcement_delivery_health({"node_delivery": {"1": ok, "2": bad}})
    assert comp.status == ComponentStatus.DEGRADED
    assert "node 2: 3 consecutive failures" in comp.message
    assert comp.details["node_delivery"]["2"]["consecutive_failures"] == 3

    comp = await monitor.check_announcement_delivery_health({"node_delivery": {"1": bad}})
    assert comp.status == ComponentStatus.UNHEALTHY


@pytest.mark.asyncio
async def test_delivery_health_unknown_without_asterisk_manager():
    monitor = _monitor([1])
    monitor.asterisk_manager = None
    comp = await monitor.check_announcement_delivery_health({})
    assert comp.status == ComponentStatus.UNKNOWN


@pytest.mark.asyncio
async def test_store_alert_keeps_outcome_on_refresh(tmp_path):
    from skywarnplus_ng.database.manager import DatabaseManager

    db = DatabaseManager(AppConfig(nws=NWSApiConfig(user_agent="test"), data_dir=tmp_path))
    await db.initialize()
    try:
        alert = _alert()
        outcome = {"status": "played", "played_nodes": [1999]}
        await db.store_alert(alert, announced=True, announcement_outcome=outcome)
        await db.store_alert(alert, announced=True)
        record = await db.get_alert(alert.id)
        assert record.additional_data["announcement_outcome"] == outcome
        assert "original_alert" in record.additional_data

        newer = {"status": "partial", "played_nodes": [1999], "failed_nodes": [2000]}
        await db.store_alert(alert, announced=True, announcement_outcome=newer)
        record = await db.get_alert(alert.id)
        assert record.additional_data["announcement_outcome"] == newer
    finally:
        await db.close()
