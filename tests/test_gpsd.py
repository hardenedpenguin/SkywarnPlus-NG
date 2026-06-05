"""Tests for gpsd JSON client."""

from skywarnplus_ng.location.gpsd import _fix_from_gpsd_message


def test_fix_from_tpv_message():
    fix = _fix_from_gpsd_message(
        {
            "class": "TPV",
            "mode": 3,
            "lat": 29.4214,
            "lon": -95.2560,
            "eph": 21.28,
            "time": "2026-06-05T02:27:48.000Z",
        }
    )
    assert fix is not None
    assert fix.latitude == 29.4214
    assert fix.longitude == -95.2560
    assert fix.mode == 3


def test_empty_poll_without_coordinates_returns_none():
    assert _fix_from_gpsd_message({"class": "POLL", "mode": 0}) is None
