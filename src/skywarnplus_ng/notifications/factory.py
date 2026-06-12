"""
Build a NotificationManager from application configuration.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..core.config import AppConfig
from .delivery import RetryPolicy
from .email import EmailConfig, EmailProvider
from .manager import NotificationConfig, NotificationManager
from .push import PushConfig, PushProvider
from .sms import SmsConfig
from .webhook import WebhookConfig, webhook_provider_for_url

logger = logging.getLogger(__name__)


def _parse_email_provider(value: str) -> EmailProvider:
    try:
        return EmailProvider((value or "custom").lower())
    except ValueError:
        return EmailProvider.CUSTOM


def _non_empty(value: Optional[str]) -> bool:
    return bool(value and str(value).strip())


def build_notification_manager(config: AppConfig) -> Optional[NotificationManager]:
    """
    Construct a NotificationManager from AppConfig.

    Returns None when no notification channels are configured.
    """
    notifications = config.notifications
    email_cfg = notifications.email
    webhook_cfg = notifications.webhook
    push_cfg = notifications.push
    sms_cfg = notifications.sms
    delivery_cfg = notifications.delivery

    email_configs: list[EmailConfig] = []
    if _non_empty(email_cfg.smtp_server) and _non_empty(email_cfg.username):
        email_configs.append(
            EmailConfig(
                provider=_parse_email_provider(email_cfg.provider),
                smtp_server=email_cfg.smtp_server.strip(),
                smtp_port=email_cfg.smtp_port,
                use_tls=email_cfg.use_tls,
                use_ssl=email_cfg.use_ssl,
                username=email_cfg.username.strip(),
                password=email_cfg.password or "",
                from_name=email_cfg.from_name or "SkywarnPlus-NG",
            )
        )

    webhook_configs: list[WebhookConfig] = []
    for url in (webhook_cfg.slack_url, webhook_cfg.teams_url, webhook_cfg.generic_url):
        if not _non_empty(url):
            continue
        clean_url = str(url).strip()
        webhook_configs.append(
            WebhookConfig(
                provider=webhook_provider_for_url(clean_url),
                webhook_url=clean_url,
                timeout_seconds=delivery_cfg.timeout_seconds,
                retry_count=delivery_cfg.max_retries,
                retry_delay_seconds=delivery_cfg.retry_delay,
            )
        )

    push_configs: list[PushConfig] = []
    if _non_empty(push_cfg.fcm_server_key):
        push_configs.append(
            PushConfig(
                provider=PushProvider.FCM,
                fcm_server_key=push_cfg.fcm_server_key,
                fcm_project_id=push_cfg.fcm_project_id,
                timeout_seconds=delivery_cfg.timeout_seconds,
                retry_count=delivery_cfg.max_retries,
                retry_delay_seconds=delivery_cfg.retry_delay,
            )
        )

    sms_configs: list[SmsConfig] = []
    if (
        sms_cfg.enabled
        and _non_empty(sms_cfg.account_sid)
        and _non_empty(sms_cfg.auth_token)
        and _non_empty(sms_cfg.from_number)
    ):
        try:
            sms_configs.append(
                SmsConfig(
                    account_sid=str(sms_cfg.account_sid).strip(),
                    auth_token=str(sms_cfg.auth_token).strip(),
                    from_number=str(sms_cfg.from_number).strip(),
                    enabled=True,
                    timeout_seconds=delivery_cfg.timeout_seconds,
                    retry_count=delivery_cfg.max_retries,
                    retry_delay_seconds=delivery_cfg.retry_delay,
                    max_length=sms_cfg.max_length,
                    all_clear_enabled=sms_cfg.all_clear_enabled,
                )
            )
        except ValueError as exc:
            logger.error("Twilio SMS config rejected: %s", exc)

    subscriber_file = config.data_dir / "subscribers.json"
    has_subscribers = False
    if subscriber_file.exists():
        try:
            import json

            with open(subscriber_file, encoding="utf-8") as handle:
                data = json.load(handle)
            subs = data.get("subscribers", []) if isinstance(data, dict) else []
            has_subscribers = bool(subs)
        except Exception:
            has_subscribers = True

    if (
        not email_configs
        and not webhook_configs
        and not push_configs
        and not sms_configs
        and not has_subscribers
    ):
        logger.debug("No notification channels configured; notification manager disabled")
        return None

    notification_config = NotificationConfig(
        email_enabled=bool(email_configs),
        email_configs=email_configs,
        webhook_enabled=bool(webhook_configs),
        webhook_configs=webhook_configs,
        push_enabled=bool(push_configs),
        push_configs=push_configs,
        sms_enabled=bool(sms_configs),
        sms_configs=sms_configs,
        delivery_queue_enabled=True,
        max_concurrent_deliveries=delivery_cfg.max_concurrent,
        delivery_timeout_seconds=delivery_cfg.timeout_seconds,
        max_retries=delivery_cfg.max_retries,
        retry_delay_seconds=delivery_cfg.retry_delay,
        subscriber_file=subscriber_file,
        template_storage_path=config.data_dir / "templates.json",
        delivery_queue_path=config.data_dir / "delivery_queue.json",
    )

    manager = NotificationManager(notification_config)
    if manager.delivery_queue:
        manager.delivery_queue.retry_policy = RetryPolicy(
            max_retries=delivery_cfg.max_retries,
            initial_delay_seconds=delivery_cfg.retry_delay,
        )
    return manager
