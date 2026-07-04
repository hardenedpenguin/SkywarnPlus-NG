"""Tests for dashboard config merge helpers."""

from skywarnplus_ng.core.config import AppConfig
from skywarnplus_ng.web.config_merge import (
    deep_merge_dict,
    is_blank_secret,
    preserve_blank_notification_secrets,
    redact_config_for_api,
)


def test_deep_merge_preserves_skydescribe_when_absent_from_overlay() -> None:
    base = {
        "enabled": True,
        "skydescribe": {"enabled": True, "dtmf_codes": {"help": "*9"}},
        "alerts": {"say_alert": True, "say_all_clear": True},
    }
    overlay = {"alerts": {"say_alert": False}}
    merged = deep_merge_dict(base, overlay)
    assert merged["skydescribe"]["dtmf_codes"]["help"] == "*9"
    assert merged["alerts"]["say_alert"] is False
    assert merged["alerts"]["say_all_clear"] is True


def test_deep_merge_geo_hazard_enabled_false_overrides_base() -> None:
    base = {
        "earthquake": {"enabled": True, "max_distance_miles": 3000},
        "wildfire": {"enabled": True, "min_acres": 250},
    }
    overlay = {
        "earthquake": {"enabled": False},
        "wildfire": {"enabled": False},
    }
    merged = deep_merge_dict(base, overlay)
    assert merged["earthquake"]["enabled"] is False
    assert merged["earthquake"]["max_distance_miles"] == 3000
    assert merged["wildfire"]["enabled"] is False
    assert merged["wildfire"]["min_acres"] == 250


def test_redact_config_strips_secrets() -> None:
    data = {
        "monitoring": {
            "http_server": {
                "auth": {"password": "hash", "secret_key": "abc"},
            }
        },
        "pushover": {"api_token": "tok", "user_key": "key"},
        "notifications": {
            "email": {"password": "smtp-secret"},
            "push": {"fcm_server_key": "fcm-secret"},
            "sms": {"auth_token": "twilio-secret"},
        },
    }
    redacted = redact_config_for_api(data)
    assert redacted["monitoring"]["http_server"]["auth"]["password"] == ""
    assert redacted["pushover"]["api_token"] == ""
    assert redacted["notifications"]["email"]["password"] == ""
    assert redacted["notifications"]["push"]["fcm_server_key"] == ""
    assert redacted["notifications"]["sms"]["auth_token"] == ""


def test_is_blank_secret() -> None:
    assert is_blank_secret(None) is True
    assert is_blank_secret("") is True
    assert is_blank_secret("   ") is True
    assert is_blank_secret("app-password") is False


def test_preserve_blank_notification_secrets_keeps_stored_values() -> None:
    config = AppConfig()
    config.notifications.email.password = "yahoo-app-password"
    config.notifications.push.fcm_server_key = "fcm-key"
    config.notifications.sms.auth_token = "twilio-token"

    data = {
        "notifications": {
            "email": {"username": "user@yahoo.com", "password": ""},
            "push": {"fcm_server_key": ""},
            "sms": {"auth_token": ""},
        }
    }
    preserve_blank_notification_secrets(data, config)
    assert data["notifications"]["email"]["password"] == "yahoo-app-password"
    assert data["notifications"]["push"]["fcm_server_key"] == "fcm-key"
    assert data["notifications"]["sms"]["auth_token"] == "twilio-token"


def test_preserve_blank_notification_secrets_keeps_new_values() -> None:
    config = AppConfig()
    config.notifications.email.password = "old-password"

    data = {"notifications": {"email": {"password": "new-app-password"}}}
    preserve_blank_notification_secrets(data, config)
    assert data["notifications"]["email"]["password"] == "new-app-password"
