"""Tests for config API county list sanitization."""

from skywarnplus_ng.web.handlers.api_config import _sanitize_counties_list


def test_sanitize_drops_null_holes() -> None:
    raw = [None, {"code": "TXC039", "name": "Brazoria", "enabled": True}]
    out = _sanitize_counties_list(raw)
    assert len(out) == 1
    assert out[0]["code"] == "TXC039"


def test_sanitize_dict_numeric_keys() -> None:
    raw = {
        "1": {"code": "TXC201", "enabled": True},
        "0": None,
    }
    out = _sanitize_counties_list(raw)
    assert len(out) == 1
    assert out[0]["code"] == "TXC201"
