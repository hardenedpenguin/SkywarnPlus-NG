"""Tests for collapsing overlapping NWS CAP replacements (same event, same county)."""

from __future__ import annotations

from datetime import datetime, timezone

from skywarnplus_ng.core.models import AlertSeverity, AlertUrgency, WeatherAlert
from skywarnplus_ng.processing.deduplication import collapse_superseded_nws_alerts


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

    out = collapse_superseded_nws_alerts(alerts)
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
    out = collapse_superseded_nws_alerts([flood, rip])
    assert len(out) == 2


def test_disjoint_counties_same_event_both_kept() -> None:
    a = _flood("fa", "2026-05-20T08:00:00-05:00", ["TXC039"])
    b = _flood("fb", "2026-05-20T08:05:00-05:00", ["TXC201"])
    out = collapse_superseded_nws_alerts([a, b])
    assert {x.id for x in out} == {"fa", "fb"}
