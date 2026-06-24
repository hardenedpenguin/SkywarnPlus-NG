"""Tests for alert ID alias handling in application state."""

from datetime import datetime, timezone

from skywarnplus_ng.core.models import AlertSeverity, AlertUrgency, WeatherAlert
from skywarnplus_ng.core.state import ApplicationState


def _alert(alert_id: str) -> WeatherAlert:
    now = datetime.now(timezone.utc)
    return WeatherAlert(
        id=alert_id,
        event="Flood Advisory",
        description="Test",
        severity=AlertSeverity.MINOR,
        urgency=AlertUrgency.EXPECTED,
        sent=now,
        effective=now,
        expires=now,
        county_codes=["TXC039"],
        area_desc="Brazoria, TX",
        sender="test",
        sender_name="NWS",
    )


def test_expired_skips_when_alias_target_still_active(tmp_path):
    state_mgr = ApplicationState(tmp_path / "state.json")
    state = state_mgr.load_state()
    state["last_alerts"] = {"old-id": {"added_at": datetime.now(timezone.utc).isoformat()}}
    state_mgr.update_alert_id_aliases(state, {"old-id": "new-id"})

    expired = state_mgr.get_expired_alerts(state, [_alert("new-id")])
    assert expired == []


def test_migrate_tracking_lists_on_alias(tmp_path):
    state_mgr = ApplicationState(tmp_path / "state.json")
    state = state_mgr.load_state()
    state["last_sayalert"] = ["old-id"]
    state_mgr.update_alert_id_aliases(state, {"old-id": "new-id"})
    assert "new-id" in state["last_sayalert"]
    assert "old-id" not in state["last_sayalert"]
