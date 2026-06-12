"""Tests for phone number normalization."""

import pytest

from skywarnplus_ng.notifications.phone import normalize_phone_number, validate_phone_number


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+15551234567", "+15551234567"),
        ("5551234567", "+15551234567"),
        ("1-555-123-4567", "+15551234567"),
        ("+44 7911 123456", "+447911123456"),
        ("", None),
        (None, None),
        ("123", None),
    ],
)
def test_normalize_phone_number(raw, expected):
    assert normalize_phone_number(raw) == expected


def test_validate_phone_number_allows_empty():
    ok, msg = validate_phone_number("")
    assert ok is True
    assert msg == ""


def test_validate_phone_number_rejects_invalid():
    ok, msg = validate_phone_number("not-a-phone")
    assert ok is False
    assert "E.164" in msg
