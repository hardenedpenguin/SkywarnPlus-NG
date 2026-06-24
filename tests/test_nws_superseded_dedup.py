"""Tests for collapsing overlapping NWS CAP replacements (same event, same county)."""

from __future__ import annotations

from datetime import datetime, timezone

from skywarnplus_ng.core.models import AlertSeverity, AlertUrgency, WeatherAlert
from skywarnplus_ng.processing.deduplication import (
    collapse_superseded_nws_alerts,
    merge_same_issuance_zone_splits,
)


def _flood(
    alert_id: str,
    sent: str,
    counties: list[str],
    expires: str = "2026-05-20T12:00:00-05:00",
) -> WeatherAlert:
    return WeatherAlert(
        id=alert_id,
        event="Flood Advisory",
        description="Test",
        severity=AlertSeverity.MINOR,
        urgency=AlertUrgency.EXPECTED,
        sent=datetime.fromisoformat(sent),
        effective=datetime.fromisoformat(sent),
        expires=datetime.fromisoformat(expires),
        county_codes=counties,
        area_desc=", ".join(counties),
        sender="test",
        sender_name="NWS",
    )


def test_three_overlapping_flood_advisories_collapse_to_newest() -> None:
    """Mimics TXC039: 6:33, 7:16 update, 7:24 expanded — Brazoria should see one flood alert."""
    alerts = [
        _flood(
            "flood-633",
            "2026-05-20T06:33:00-05:00",
            ["TXC039", "TXC201"],
            "2026-05-20T08:30:00-05:00",
        ),
        _flood(
            "flood-716",
            "2026-05-20T07:16:00-05:00",
            ["TXC039"],
            "2026-05-20T08:30:00-05:00",
        ),
        _flood(
            "flood-724",
            "2026-05-20T07:24:00-05:00",
            ["TXC039", "TXC201", "TXC201"],
            "2026-05-20T09:15:00-05:00",
        ),
    ]

    out = collapse_superseded_nws_alerts(alerts)[0]
    flood_ids = {a.id for a in out if a.id.startswith("flood-")}
    assert flood_ids == {"flood-724"}


def test_different_events_both_kept() -> None:
    flood = _flood("f1", "2026-05-20T07:00:00-05:00", ["TXC039"])
    rip = WeatherAlert(
        id="rip-1",
        event="Rip Current Statement",
        description="Surf",
        severity=AlertSeverity.MODERATE,
        urgency=AlertUrgency.EXPECTED,
        sent=datetime(2026, 5, 20, 6, 36, tzinfo=timezone.utc),
        effective=datetime(2026, 5, 20, 6, 36, tzinfo=timezone.utc),
        expires=datetime(2026, 5, 20, 22, 0, tzinfo=timezone.utc),
        county_codes=["TXC039"],
        area_desc="Brazoria, TX",
        sender="test",
        sender_name="NWS",
    )
    out = collapse_superseded_nws_alerts([flood, rip])[0]
    assert len(out) == 2


def test_disjoint_counties_same_event_both_kept() -> None:
    a = _flood("fa", "2026-05-20T08:00:00-05:00", ["TXC039"])
    b = _flood("fb", "2026-05-20T08:05:00-05:00", ["TXC201"])
    out = collapse_superseded_nws_alerts([a, b])[0]
    assert {x.id for x in out} == {"fa", "fb"}


def test_four_floods_all_touching_txc039_collapse_to_one() -> None:
    """Wrinkles case: several CAP products all include TXC039 with different area lists."""
    alerts = [
        _flood("f1", "2026-05-20T06:33:00-05:00", ["TXC039", "TXC201"]),
        _flood("f2", "2026-05-20T07:16:00-05:00", ["TXC039"]),
        _flood("f3", "2026-05-20T07:24:00-05:00", ["TXC039", "TXC201", "TXC201"]),
        _flood("f4", "2026-05-20T08:00:00-05:00", ["TXC039"]),
    ]
    out = collapse_superseded_nws_alerts(alerts)[0]
    assert len([a for a in out if a.event == "Flood Advisory"]) == 1
    assert out[0].id == "f4"


def test_same_issuance_disjoint_counties_merge_for_supermon() -> None:
    """NWS zone splits at the same sent time (e.g. marine zones) become one alert."""
    sent = "2026-06-16T10:38:00-05:00"
    brazoria = WeatherAlert(
        id="tsw-brazoria",
        event="Tropical Storm Watch",
        description="Brazoria Islands",
        severity=AlertSeverity.SEVERE,
        urgency=AlertUrgency.FUTURE,
        sent=datetime.fromisoformat(sent),
        effective=datetime.fromisoformat(sent),
        expires=datetime(2026, 6, 16, 18, 45, tzinfo=timezone.utc),
        county_codes=["TXC039"],
        area_desc="Brazoria Islands",
        sender="test",
        sender_name="NWS Houston/Galveston TX",
    )
    galveston = WeatherAlert(
        id="tsw-galveston",
        event="Tropical Storm Watch",
        description="Bolivar Peninsula",
        severity=AlertSeverity.SEVERE,
        urgency=AlertUrgency.FUTURE,
        sent=datetime.fromisoformat(sent),
        effective=datetime.fromisoformat(sent),
        expires=datetime(2026, 6, 16, 18, 45, tzinfo=timezone.utc),
        county_codes=["TXC167"],
        area_desc="Bolivar Peninsula",
        sender="test",
        sender_name="NWS Houston/Galveston TX",
    )

    out = merge_same_issuance_zone_splits([brazoria, galveston])[0]
    assert len(out) == 1
    assert set(out[0].county_codes) == {"TXC039", "TXC167"}
    assert "Brazoria Islands" in out[0].area_desc
    assert "Bolivar Peninsula" in out[0].area_desc


def test_different_issuance_minutes_same_event_not_merged() -> None:
    a = _flood("fa", "2026-05-20T08:00:00-05:00", ["TXC039"])
    b = _flood("fb", "2026-05-20T08:05:00-05:00", ["TXC201"])
    out = merge_same_issuance_zone_splits([a, b])[0]
    assert {x.id for x in out} == {"fa", "fb"}
