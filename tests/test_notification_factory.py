"""Tests for notification factory and webhook provider detection."""

import json
from pathlib import Path

from skywarnplus_ng.core.config import AppConfig, NotificationsConfig, NotificationEmailConfig
from skywarnplus_ng.notifications.factory import build_notification_manager
from skywarnplus_ng.notifications.webhook import WebhookProvider, webhook_provider_for_url
from skywarnplus_ng.web.config_merge import redact_config_for_api


def test_webhook_provider_for_url() -> None:
    assert (
        webhook_provider_for_url("https://discord.com/api/webhooks/123/abc")
        == WebhookProvider.DISCORD
    )
    assert (
        webhook_provider_for_url("https://hooks.slack.com/services/T/B/X") == WebhookProvider.SLACK
    )
    assert (
        webhook_provider_for_url("https://outlook.office.com/webhook/guid") == WebhookProvider.TEAMS
    )
    assert webhook_provider_for_url("https://example.com/hook") == WebhookProvider.GENERIC


def test_build_notification_manager_from_email_config(tmp_path: Path) -> None:
    config = AppConfig(
        data_dir=tmp_path,
        notifications=NotificationsConfig(
            email=NotificationEmailConfig(
                provider="gmail",
                smtp_server="smtp.gmail.com",
                smtp_port=587,
                username="alerts@example.com",
                password="secret",
            )
        ),
    )
    manager = build_notification_manager(config)
    assert manager is not None
    assert len(manager.email_notifiers) == 1


def test_build_notification_manager_from_subscribers_file(tmp_path: Path) -> None:
    subscribers_file = tmp_path / "subscribers.json"
    subscribers_file.write_text(
        json.dumps(
            {
                "subscribers": [
                    {
                        "subscriber_id": "abc",
                        "name": "Test",
                        "email": "test@example.com",
                        "status": "active",
                        "preferences": {"enabled_methods": ["email"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    config = AppConfig(data_dir=tmp_path)
    manager = build_notification_manager(config)
    assert manager is not None
    assert manager.subscriber_manager.get_subscriber_count() == 1


def test_build_notification_manager_returns_none_when_unconfigured(tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path)
    assert build_notification_manager(config) is None


def test_redact_config_strips_notification_secrets() -> None:
    data = {
        "notifications": {
            "email": {"password": "smtp-secret"},
            "push": {"fcm_server_key": "fcm-key"},
        }
    }
    redacted = redact_config_for_api(data)
    assert redacted["notifications"]["email"]["password"] == ""
    assert redacted["notifications"]["push"]["fcm_server_key"] == ""
