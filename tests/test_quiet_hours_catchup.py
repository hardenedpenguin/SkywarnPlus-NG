"""Alerts held during quiet hours are voiced once quiet hours end (if still active)."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from test_announcement_retry import NODES, _alert, _make_app

from skywarnplus_ng.core.config import AppConfig, NWSApiConfig
from skywarnplus_ng.core.models import AlertSeverity
from skywarnplus_ng.core.state import ApplicationState
from skywarnplus_ng.playback.policy import PlaybackPolicy, _in_quiet_window, _parse_hhmm


def _moderate_alert(alert_id: str = "urn:test:wsw", event: str = "Winter Storm Warning"):
    alert = _alert(alert_id, event)
    alert.severity = AlertSeverity.MODERATE
    return alert


def _with_quiet_policy(app, active: bool = True):
    """Attach a real PlaybackPolicy whose quiet-hours window is toggled by the test."""
    app.config.alerts.quiet_hours.enabled = True
    policy = PlaybackPolicy(app.config.alerts)
    flag = {"on": active}
    policy.is_quiet_hours_active = lambda now=None: flag["on"]
    app.playback_policy = policy
    return flag


def _outcome(app, alert_id):
    return app.state_manager.get_announcement_outcome(app.state, alert_id)


@pytest.mark.asyncio
async def test_held_alert_is_voiced_when_quiet_hours_end(tmp_path):
    app = _make_app(tmp_path, [NODES])
    quiet = _with_quiet_policy(app)
    alert = _moderate_alert()

    await app._process_alerts([alert])
    await app._process_alerts([alert])
    assert app._announce_alert.await_count == 0
    assert alert.id in app.state["quiet_hours_held"]
    outcome = _outcome(app, alert.id)
    assert outcome["status"] == "skipped"
    assert outcome["reason"] == "quiet_hours"
    assert outcome["held"] is True

    quiet["on"] = False
    await app._process_alerts([alert])

    assert app._announce_alert.await_count == 1
    assert alert.id in app.state["last_sayalert"]
    assert alert.id not in app.state["quiet_hours_held"]
    assert _outcome(app, alert.id)["status"] == "played"

    # Not voiced again on later polls
    await app._process_alerts([alert])
    assert app._announce_alert.await_count == 1


@pytest.mark.asyncio
async def test_catchup_disabled_drops_quiet_hours_skip(tmp_path):
    app = _make_app(tmp_path, [NODES])
    quiet = _with_quiet_policy(app)
    app.config.alerts.quiet_hours.announce_held_on_end = False
    alert = _moderate_alert()

    await app._process_alerts([alert])
    assert alert.id not in app.state["quiet_hours_held"]
    assert "held" not in _outcome(app, alert.id)

    quiet["on"] = False
    await app._process_alerts([alert])
    assert app._announce_alert.await_count == 0


@pytest.mark.asyncio
async def test_disabling_catchup_releases_existing_holds(tmp_path):
    app = _make_app(tmp_path, [NODES])
    quiet = _with_quiet_policy(app)
    alert = _moderate_alert()
    await app._process_alerts([alert])
    assert alert.id in app.state["quiet_hours_held"]

    app.config.alerts.quiet_hours.announce_held_on_end = False
    quiet["on"] = False
    await app._process_alerts([alert])

    assert app._announce_alert.await_count == 0
    assert alert.id not in app.state["quiet_hours_held"]
    assert "held" not in _outcome(app, alert.id)


@pytest.mark.asyncio
async def test_alert_expired_overnight_is_not_voiced(tmp_path):
    app = _make_app(tmp_path, [NODES])
    quiet = _with_quiet_policy(app)
    alert = _moderate_alert()
    await app._process_alerts([alert])
    assert alert.id in app.state["quiet_hours_held"]

    # Alert gone from the feed before quiet hours end
    await app._process_alerts([])
    assert alert.id not in app.state["quiet_hours_held"]

    quiet["on"] = False
    await app._process_alerts([])
    assert app._announce_alert.await_count == 0


@pytest.mark.asyncio
async def test_alert_that_expired_since_fetch_is_not_voiced(tmp_path):
    app = _make_app(tmp_path, [NODES])
    quiet = _with_quiet_policy(app)
    alert = _moderate_alert()
    await app._process_alerts([alert])

    app.nws_client = MagicMock()
    app.nws_client.filter_active_alerts.return_value = []
    quiet["on"] = False
    await app._process_alerts([alert])

    assert app._announce_alert.await_count == 0
    assert alert.id not in app.state["quiet_hours_held"]


@pytest.mark.asyncio
async def test_severe_alert_allowed_through_is_not_held(tmp_path):
    app = _make_app(tmp_path, [NODES])
    _with_quiet_policy(app)
    alert = _alert()  # Extreme severity; allow_severe defaults to True

    await app._process_alerts([alert])

    assert app._announce_alert.await_count == 1
    assert alert.id not in app.state["quiet_hours_held"]


@pytest.mark.asyncio
async def test_held_alert_dropped_when_event_becomes_blocked(tmp_path):
    app = _make_app(tmp_path, [NODES])
    quiet = _with_quiet_policy(app)
    alert = _moderate_alert()
    await app._process_alerts([alert])

    app.config.filtering.say_alert_blocked = ["Winter*"]
    quiet["on"] = False
    await app._process_alerts([alert])

    assert app._announce_alert.await_count == 0
    assert alert.id not in app.state["quiet_hours_held"]
    outcome = _outcome(app, alert.id)
    assert outcome["reason"] == "blocked_event"
    assert "held" not in outcome


@pytest.mark.asyncio
async def test_failed_catchup_falls_back_to_retry(tmp_path):
    app = _make_app(tmp_path, [[]])
    quiet = _with_quiet_policy(app)
    alert = _moderate_alert()
    await app._process_alerts([alert])

    quiet["on"] = False
    await app._process_alerts([alert])

    assert app._announce_alert.await_count == 1
    assert alert.id not in app.state["quiet_hours_held"]
    assert app.state["announcement_retries"][alert.id]["pending_nodes"] == NODES
    assert _outcome(app, alert.id)["status"] == "failed"


@pytest.mark.asyncio
async def test_catchup_updates_stored_alert(tmp_path):
    app = _make_app(tmp_path, [NODES])
    quiet = _with_quiet_policy(app)
    app.database_manager = MagicMock()
    stored = []

    async def store_alert(**kwargs):
        stored.append(kwargs)

    app.database_manager.store_alert = store_alert
    alert = _moderate_alert()
    await app._process_alerts([alert])
    assert stored[-1]["announcement_outcome"]["held"] is True

    quiet["on"] = False
    await app._process_alerts([alert])
    assert stored[-1]["announced"] is True
    assert stored[-1]["announcement_nodes"] == NODES
    assert stored[-1]["announcement_outcome"]["status"] == "played"


def test_hold_follows_alias_merge_and_is_pruned(tmp_path):
    sm = ApplicationState(tmp_path / "state.json")
    state = sm.load_state()
    sm.hold_for_quiet_hours(state, "urn:old")
    sm.update_alert_id_aliases(state, {"urn:old": "urn:new"})
    assert list(sm.get_quiet_hours_held(state)) == ["urn:new"]

    sm.prune_alert_tracking(state, "urn:new")
    assert sm.get_quiet_hours_held(state) == {}


def test_existing_state_file_gains_hold_key(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"last_alerts": {}, "active_alerts": []}', encoding="utf-8")
    state = ApplicationState(path).load_state()
    assert state["quiet_hours_held"] == {}


def test_policy_status_reports_held_count(tmp_path):
    config = AppConfig(nws=NWSApiConfig(user_agent="test"), data_dir=tmp_path)
    assert config.alerts.quiet_hours.announce_held_on_end is True
    policy = PlaybackPolicy(config.alerts)
    status = policy.get_status({"quiet_hours_held": {"a": {}, "b": {}}})
    assert status["held_for_quiet_hours"] == 2
    assert status["quiet_hours"]["announce_held_on_end"] is True


@pytest.mark.parametrize(
    ("clock", "expected"),
    [("23:30", True), ("02:00", True), ("06:00", False), ("12:00", False)],
)
def test_quiet_window_crossing_midnight(clock, expected):
    start, end = _parse_hhmm("22:00"), _parse_hhmm("06:00")
    now = datetime.fromisoformat(f"2026-11-24T{clock}:00")
    assert _in_quiet_window(now, start, end) is expected
