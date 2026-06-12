"""Tests for alert snapshot refresh in application state."""

from datetime import datetime, timezone, timedelta

from skywarnplus_ng.core.models import WeatherAlert, AlertSeverity, AlertUrgency, AlertCertainty
from skywarnplus_ng.core.state import ApplicationState
from skywarnplus_ng.web.alert_payload import build_active_alerts_payload


def _make_alert(alert_id: str, expires_hours: int = 1) -> WeatherAlert:
    now = datetime.now(timezone.utc)
    return WeatherAlert(
        id=alert_id,
        event="Severe Thunderstorm Warning",
        description="Take shelter now.",
        severity=AlertSeverity.SEVERE,
        urgency=AlertUrgency.IMMEDIATE,
        certainty=AlertCertainty.OBSERVED,
        sent=now,
        effective=now,
        expires=now + timedelta(hours=expires_hours),
        area_desc="Sample County",
        county_codes=["TXC039"],
        sender="w-nws.webmaster@noaa.gov",
        sender_name="NWS Houston/Galveston TX",
    )


def test_upsert_alert_updates_expires_and_sets_updated_at(tmp_path) -> None:
    sm = ApplicationState(tmp_path / "state.json")
    state = sm._get_default_state()
    alert = _make_alert("urn:oid:1.2.3", expires_hours=1)

    assert sm.upsert_alert(state, alert) is True
    assert "updated_at" not in state["last_alerts"]["urn:oid:1.2.3"]

    extended = _make_alert("urn:oid:1.2.3", expires_hours=3)
    assert sm.upsert_alert(state, extended) is True
    stored = state["last_alerts"]["urn:oid:1.2.3"]
    assert stored["expires"] == extended.model_dump(mode="json")["expires"]
    assert stored.get("updated_at")


def test_build_active_alerts_payload_includes_enrichment(tmp_path) -> None:
    sm = ApplicationState(tmp_path / "state.json")
    state = sm._get_default_state()
    alert = _make_alert("urn:oid:9.9")
    sm.upsert_alert(state, alert)
    state["active_alerts"] = [alert.id]
    state["last_sayalert"] = [alert.id]

    payload = build_active_alerts_payload(state, config=None)
    assert len(payload) == 1
    assert payload[0]["announced"] is True
    assert payload[0]["expires"] == alert.model_dump(mode="json")["expires"]
