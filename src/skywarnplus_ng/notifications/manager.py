"""
Main notification manager for SkywarnPlus-NG.
Coordinates all notification delivery methods and subscriber management.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from pathlib import Path

from .email import EmailNotifier, EmailConfig
from .webhook import WebhookNotifier, WebhookConfig, webhook_provider_for_url
from .push import PushNotifier, PushConfig
from .sms import (
    SmsNotifier,
    SmsConfig,
    format_short_alert_message,
    format_short_general_message,
)
from .subscriber import SubscriberManager, Subscriber, NotificationMethod
from .templates import TemplateEngine
from .delivery import DeliveryQueue, DeliveryItem, DeliveryMethod, DeliveryStatus
from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)


class NotificationError(Exception):
    """Notification system error."""

    pass


@dataclass
class NotificationConfig:
    """Notification system configuration."""

    # Email settings
    email_enabled: bool = True
    email_configs: List[EmailConfig] = None

    # Webhook settings
    webhook_enabled: bool = True
    webhook_configs: List[WebhookConfig] = None

    # Push settings
    push_enabled: bool = True
    push_configs: List[PushConfig] = None

    # SMS settings
    sms_enabled: bool = True
    sms_configs: List[SmsConfig] = None

    # Delivery settings
    delivery_queue_enabled: bool = True
    max_concurrent_deliveries: int = 10
    delivery_timeout_seconds: int = 30
    max_retries: int = 3
    retry_delay_seconds: int = 5

    # Subscriber settings
    subscriber_file: Optional[Path] = None
    template_storage_path: Optional[Path] = None
    delivery_queue_path: Optional[Path] = None

    def __post_init__(self):
        if self.email_configs is None:
            self.email_configs = []
        if self.webhook_configs is None:
            self.webhook_configs = []
        if self.push_configs is None:
            self.push_configs = []
        if self.sms_configs is None:
            self.sms_configs = []


class NotificationManager:
    """Main notification manager coordinating all delivery methods."""

    def __init__(self, config: NotificationConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.subscriber_manager = SubscriberManager(config.subscriber_file)
        self.template_engine = TemplateEngine(storage_path=config.template_storage_path)
        self.delivery_queue = (
            DeliveryQueue(data_file=config.delivery_queue_path)
            if config.delivery_queue_enabled
            else None
        )

        # Initialize notifiers
        self.email_notifiers: List[EmailNotifier] = []
        self.webhook_notifiers: List[WebhookNotifier] = []
        self.push_notifiers: List[PushNotifier] = []
        self.sms_notifiers: List[SmsNotifier] = []

        self._initialize_notifiers()

        # Delivery tracking
        self._delivery_tasks: Set[asyncio.Task] = set()
        self._running = False

    def _initialize_notifiers(self) -> None:
        """Initialize notification notifiers."""
        # Initialize email notifiers
        if self.config.email_enabled:
            for email_config in self.config.email_configs:
                try:
                    notifier = EmailNotifier(email_config)
                    self.email_notifiers.append(notifier)
                    self.logger.info(
                        f"Initialized email notifier for {email_config.provider.value}"
                    )
                except Exception as e:
                    self.logger.error(f"Failed to initialize email notifier: {e}")

        # Initialize webhook notifiers
        if self.config.webhook_enabled:
            for webhook_config in self.config.webhook_configs:
                try:
                    notifier = WebhookNotifier(webhook_config)
                    self.webhook_notifiers.append(notifier)
                    self.logger.info(
                        f"Initialized webhook notifier for {webhook_config.provider.value}"
                    )
                except Exception as e:
                    self.logger.error(f"Failed to initialize webhook notifier: {e}")

        # Initialize push notifiers
        if self.config.push_enabled:
            for push_config in self.config.push_configs:
                try:
                    notifier = PushNotifier(push_config)
                    self.push_notifiers.append(notifier)
                    self.logger.info(f"Initialized push notifier for {push_config.provider.value}")
                except Exception as e:
                    self.logger.error(f"Failed to initialize push notifier: {e}")

        if self.config.sms_enabled:
            for sms_config in self.config.sms_configs:
                try:
                    notifier = SmsNotifier(sms_config)
                    self.sms_notifiers.append(notifier)
                    self.logger.info("Initialized Twilio SMS notifier")
                except Exception as e:
                    self.logger.error(f"Failed to initialize SMS notifier: {e}")

    async def send_alert_notifications(
        self, alert: WeatherAlert, *, skip_webhooks: bool = False
    ) -> Dict[str, Any]:
        """
        Send notifications for a weather alert.

        Args:
            alert: Weather alert to send notifications for
            skip_webhooks: Skip subscriber webhook delivery (e.g. already sent)

        Returns:
            Delivery results summary
        """
        self.logger.info(f"Sending notifications for alert {alert.id}: {alert.event}")

        # Get subscribers who should receive this alert
        subscribers = self.subscriber_manager.get_subscribers_for_alert(alert)

        if not subscribers:
            self.logger.info(f"No subscribers found for alert {alert.id}")
            return {
                "success": True,
                "alert_id": alert.id,
                "subscribers_notified": 0,
                "total_notifications": 0,
                "delivery_results": {},
                "webhook_success": False,
            }

        # Generate notifications for each subscriber
        delivery_results = {}
        total_notifications = 0
        webhook_success = False

        for subscriber in subscribers:
            try:
                if subscriber.preferences.batch_delivery and self.delivery_queue:
                    queued = self._queue_subscriber_delivery(alert, subscriber, skip_webhooks)
                    delivery_results[subscriber.subscriber_id] = queued
                    total_notifications += queued.get("queued_count", 0)
                    continue

                # Generate notification content
                notification_content = await self._generate_notification_content(alert, subscriber)

                # Send notifications via enabled methods
                subscriber_results = await self._send_subscriber_notifications(
                    alert, subscriber, notification_content, skip_webhooks=skip_webhooks
                )

                delivery_results[subscriber.subscriber_id] = subscriber_results
                total_notifications += sum(
                    result.get("sent_count", 0) for result in subscriber_results.values()
                )
                if subscriber_results.get("webhook", {}).get("success"):
                    webhook_success = True

                # Record notification for subscriber
                subscriber.record_notification()
                self.subscriber_manager.update_subscriber(subscriber)

            except Exception as e:
                self.logger.error(
                    f"Failed to send notifications to subscriber {subscriber.subscriber_id}: {e}"
                )
                delivery_results[subscriber.subscriber_id] = {"error": str(e)}

        self.logger.info(f"Sent {total_notifications} notifications for alert {alert.id}")

        return {
            "success": True,
            "alert_id": alert.id,
            "subscribers_notified": len(subscribers),
            "total_notifications": total_notifications,
            "delivery_results": delivery_results,
            "webhook_success": webhook_success,
        }

    async def send_global_webhook_notifications(self, alert: WeatherAlert) -> Dict[str, Any]:
        """Send alert to globally configured webhook URLs (Slack, Teams, generic)."""
        if not self.webhook_notifiers:
            return {"success": False, "results": [], "sent_count": 0}

        results = []
        sent_count = 0
        for notifier in self.webhook_notifiers:
            try:
                async with notifier as webhook:
                    result = await webhook.send_alert_webhook(alert)
                    results.append(result)
                    if result.get("success"):
                        sent_count += 1
            except Exception as e:
                self.logger.error("Global webhook delivery failed: %s", e)
                results.append({"success": False, "error": str(e)})

        return {
            "success": sent_count > 0,
            "results": results,
            "sent_count": sent_count,
        }

    async def send_all_clear_notifications(self, area_message: str) -> Dict[str, Any]:
        """Notify subscribers and global webhooks that there are no active alerts."""
        title = "All Clear"
        message = f"No active weather alerts. {area_message}".strip()
        subscriber_result = await self.send_general_notification(title, message)
        global_result = await self._send_global_general_webhooks(title, message)
        return {
            "success": subscriber_result.get("success", False)
            or global_result.get("success", False),
            "subscribers": subscriber_result,
            "global_webhooks": global_result,
        }

    async def _send_global_general_webhooks(self, title: str, message: str) -> Dict[str, Any]:
        """Send a general notification to globally configured webhooks."""
        if not self.webhook_notifiers:
            return {"success": False, "results": [], "sent_count": 0}

        results = []
        sent_count = 0
        for notifier in self.webhook_notifiers:
            try:
                async with notifier as webhook:
                    result = await webhook.send_notification_webhook(title=title, message=message)
                    results.append(result)
                    if result.get("success"):
                        sent_count += 1
            except Exception as e:
                self.logger.error("Global webhook all-clear delivery failed: %s", e)
                results.append({"success": False, "error": str(e)})

        return {"success": sent_count > 0, "results": results, "sent_count": sent_count}

    async def send_general_notification(
        self,
        title: str,
        message: str,
        recipients: Optional[List[str]] = None,
        methods: Optional[List[NotificationMethod]] = None,
    ) -> Dict[str, Any]:
        """
        Send general notification to specified recipients.

        Args:
            title: Notification title
            message: Notification message
            recipients: List of recipient identifiers (optional, sends to all if not specified)
            methods: List of delivery methods (optional, uses all enabled if not specified)

        Returns:
            Delivery results summary
        """
        self.logger.info(f"Sending general notification: {title}")

        # Get recipients
        if recipients:
            target_subscribers = [
                self.subscriber_manager.get_subscriber_by_email(email) for email in recipients
            ]
            target_subscribers = [s for s in target_subscribers if s is not None]
        else:
            target_subscribers = self.subscriber_manager.get_all_subscribers()

        if not target_subscribers:
            self.logger.warning("No target subscribers found for general notification")
            return {
                "success": True,
                "title": title,
                "subscribers_notified": 0,
                "delivery_results": {},
            }

        # Generate notification content
        notification_content = {
            "subject": title,
            "body": message,
            "html_body": message,  # Simple HTML for now
        }

        # Send notifications
        delivery_results = {}
        total_notifications = 0

        for subscriber in target_subscribers:
            try:
                subscriber_results = await self._send_subscriber_notifications(
                    None, subscriber, notification_content, methods
                )

                delivery_results[subscriber.subscriber_id] = subscriber_results
                total_notifications += sum(
                    result.get("sent_count", 0) for result in subscriber_results.values()
                )

            except Exception as e:
                self.logger.error(
                    f"Failed to send notification to subscriber {subscriber.subscriber_id}: {e}"
                )
                delivery_results[subscriber.subscriber_id] = {"error": str(e)}

        self.logger.info(f"Sent {total_notifications} general notifications")

        return {
            "success": True,
            "title": title,
            "subscribers_notified": len(target_subscribers),
            "total_notifications": total_notifications,
            "delivery_results": delivery_results,
        }

    async def _generate_notification_content(
        self, alert: WeatherAlert, subscriber: Subscriber
    ) -> Dict[str, str]:
        """Generate notification content for a subscriber."""
        # Use template engine to generate content
        try:
            # Try to find a template that matches subscriber preferences
            template_id = self._select_template_for_subscriber(subscriber)

            if template_id:
                content = self.template_engine.render_alert_template(template_id, alert)
                return content
            else:
                # Fallback to default content generation
                return self._generate_default_content(alert)

        except Exception as e:
            self.logger.error(f"Failed to generate notification content: {e}")
            return self._generate_default_content(alert)

    def _select_template_for_subscriber(self, subscriber: Subscriber) -> Optional[str]:
        """Select appropriate template for subscriber."""
        # Simple template selection logic
        # In a real implementation, this would be more sophisticated

        if NotificationMethod.EMAIL in subscriber.preferences.enabled_methods:
            return "email_alert_default"
        elif NotificationMethod.WEBHOOK in subscriber.preferences.enabled_methods:
            return "webhook_alert_default"
        elif NotificationMethod.PUSH in subscriber.preferences.enabled_methods:
            return "push_alert_default"
        elif NotificationMethod.SMS in subscriber.preferences.enabled_methods:
            return "sms_alert_default"

        return None

    def _generate_sms_body(
        self,
        alert: Optional[WeatherAlert],
        title: str,
        message: str,
    ) -> str:
        """Build a short SMS body for an alert or general notification."""
        max_len = self.sms_notifiers[0].config.max_length if self.sms_notifiers else 160

        if alert is not None:
            if self.template_engine.get_template("sms_alert_default"):
                try:
                    rendered = self.template_engine.render_alert_template(
                        "sms_alert_default", alert
                    )
                    body = (rendered.get("body") or "").strip()
                    if body:
                        return body[:max_len]
                except Exception as e:
                    self.logger.debug("SMS template render failed, using default: %s", e)
            return format_short_alert_message(alert, max_len)

        return format_short_general_message(title, message, max_len)

    def _generate_default_content(self, alert: WeatherAlert) -> Dict[str, str]:
        """Generate default notification content."""
        subject = f"Weather Alert: {alert.event} - {alert.area_desc}"

        body = f"""
Weather Alert: {alert.event}

Area: {alert.area_desc}
Severity: {alert.severity.value}
Urgency: {alert.urgency.value}
Certainty: {alert.certainty.value}

Description:
{alert.description or "No description available"}

Effective: {alert.effective.strftime("%Y-%m-%d %H:%M:%S UTC") if alert.effective else "N/A"}
Expires: {alert.expires.strftime("%Y-%m-%d %H:%M:%S UTC") if alert.expires else "N/A"}

Instructions:
{alert.instruction or "Please monitor local weather conditions and follow safety guidelines."}

This alert was sent by SkywarnPlus-NG.
        """.strip()

        return {
            "subject": subject,
            "body": body,
            "html_body": body,  # Simple HTML for now
        }

    async def _send_subscriber_notifications(
        self,
        alert: Optional[WeatherAlert],
        subscriber: Subscriber,
        content: Dict[str, str],
        methods: Optional[List[NotificationMethod]] = None,
        *,
        skip_webhooks: bool = False,
    ) -> Dict[str, Any]:
        """Send notifications to a subscriber via their preferred methods."""
        if methods is None:
            methods = list(subscriber.preferences.enabled_methods)

        results = {}

        # Send email notification
        if NotificationMethod.EMAIL in methods and self.email_notifiers:
            try:
                email_result = await self._send_email_notification(
                    subscriber, content["subject"], content["body"], content.get("html_body")
                )
                results["email"] = email_result
            except Exception as e:
                self.logger.error(
                    f"Email notification failed for subscriber {subscriber.subscriber_id}: {e}"
                )
                results["email"] = {"success": False, "error": str(e)}

        # Send webhook notification
        if not skip_webhooks and NotificationMethod.WEBHOOK in methods and subscriber.webhook_url:
            try:
                webhook_result = await self._send_webhook_notification(
                    subscriber,
                    alert,
                    content["subject"],
                    content["body"],
                )
                results["webhook"] = webhook_result
            except Exception as e:
                self.logger.error(
                    f"Webhook notification failed for subscriber {subscriber.subscriber_id}: {e}"
                )
                results["webhook"] = {"success": False, "error": str(e)}

        # Send push notification
        if NotificationMethod.PUSH in methods and self.push_notifiers and subscriber.push_tokens:
            try:
                push_result = await self._send_push_notification(
                    subscriber,
                    alert,
                    content["subject"],
                    content["body"],
                )
                results["push"] = push_result
            except Exception as e:
                self.logger.error(
                    f"Push notification failed for subscriber {subscriber.subscriber_id}: {e}"
                )
                results["push"] = {"success": False, "error": str(e)}

        if NotificationMethod.SMS in methods:
            if not self.sms_notifiers or not subscriber.phone:
                results["sms"] = {
                    "success": False,
                    "error": "SMS not configured or no phone number",
                }
            elif alert is None and not self.sms_notifiers[0].config.all_clear_enabled:
                results["sms"] = {
                    "success": False,
                    "skipped": True,
                    "error": "All-clear SMS disabled",
                }
            else:
                try:
                    sms_result = await self._send_sms_notification(
                        subscriber,
                        alert,
                        content["subject"],
                        content["body"],
                    )
                    results["sms"] = sms_result
                except Exception as e:
                    self.logger.error(
                        f"SMS notification failed for subscriber {subscriber.subscriber_id}: {e}"
                    )
                    results["sms"] = {"success": False, "error": str(e)}

        return results

    def _queue_subscriber_delivery(
        self,
        alert: WeatherAlert,
        subscriber: Subscriber,
        skip_webhooks: bool,
    ) -> Dict[str, Any]:
        """Queue subscriber notifications for batch delivery."""
        if not self.delivery_queue:
            return {"success": False, "error": "Delivery queue not enabled"}

        content = self._generate_default_content(alert)
        scheduled_at = datetime.now(timezone.utc) + timedelta(
            minutes=subscriber.preferences.batch_interval_minutes
        )
        queued_count = 0
        methods = list(subscriber.preferences.enabled_methods)

        if NotificationMethod.EMAIL in methods and self.email_notifiers:
            self.delivery_queue.add_delivery(
                alert_id=alert.id,
                method=DeliveryMethod.EMAIL,
                recipient=subscriber.email,
                subject=content["subject"],
                body=content["body"],
                scheduled_at=scheduled_at,
            )
            queued_count += 1

        if not skip_webhooks and NotificationMethod.WEBHOOK in methods and subscriber.webhook_url:
            self.delivery_queue.add_delivery(
                alert_id=alert.id,
                method=DeliveryMethod.WEBHOOK,
                recipient=subscriber.webhook_url,
                subject=content["subject"],
                body=content["body"],
                scheduled_at=scheduled_at,
            )
            queued_count += 1

        if NotificationMethod.PUSH in methods and self.push_notifiers and subscriber.push_tokens:
            for token in subscriber.push_tokens:
                self.delivery_queue.add_delivery(
                    alert_id=alert.id,
                    method=DeliveryMethod.PUSH,
                    recipient=token,
                    subject=content["subject"],
                    body=content["body"],
                    scheduled_at=scheduled_at,
                )
                queued_count += 1

        if NotificationMethod.SMS in methods and self.sms_notifiers and subscriber.phone:
            sms_body = self._generate_sms_body(alert, content["subject"], content["body"])
            self.delivery_queue.add_delivery(
                alert_id=alert.id,
                method=DeliveryMethod.SMS,
                recipient=subscriber.phone,
                subject=content["subject"],
                body=sms_body,
                scheduled_at=scheduled_at,
            )
            queued_count += 1

        return {"success": True, "queued": True, "queued_count": queued_count}

    async def _send_email_notification(
        self, subscriber: Subscriber, subject: str, body: str, html_body: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send email notification to subscriber."""
        # Use the first available email notifier
        if not self.email_notifiers:
            raise NotificationError("No email notifiers configured")

        notifier = self.email_notifiers[0]

        return await notifier.send_notification_email(
            subject=subject, body=body, recipients=[subscriber.email], html_body=html_body
        )

    async def _send_webhook_notification(
        self,
        subscriber: Subscriber,
        alert: Optional[WeatherAlert],
        title: str,
        message: str,
    ) -> Dict[str, Any]:
        """Send webhook notification to subscriber."""
        if not subscriber.webhook_url:
            raise NotificationError("No webhook URL configured for subscriber")

        provider = webhook_provider_for_url(subscriber.webhook_url)
        webhook_config = WebhookConfig(
            provider=provider,
            webhook_url=subscriber.webhook_url,
            timeout_seconds=self.config.delivery_timeout_seconds,
            retry_count=self.config.max_retries,
            retry_delay_seconds=self.config.retry_delay_seconds,
        )

        try:
            notifier_cm = WebhookNotifier(webhook_config)
        except ValueError as e:
            self.logger.warning(
                "Subscriber %s webhook URL rejected: %s",
                subscriber.subscriber_id,
                e,
            )
            return {"success": False, "error": str(e)}

        async with notifier_cm as notifier:
            if alert is not None:
                return await notifier.send_alert_webhook(alert)
            return await notifier.send_notification_webhook(title=title, message=message)

    async def _send_push_notification(
        self,
        subscriber: Subscriber,
        alert: Optional[WeatherAlert],
        title: str,
        message: str,
    ) -> Dict[str, Any]:
        """Send push notification to subscriber."""
        if not subscriber.push_tokens:
            raise NotificationError("No push tokens configured for subscriber")

        if not self.push_notifiers:
            raise NotificationError("No push notifiers configured")

        notifier = self.push_notifiers[0]

        if alert is not None:
            return await notifier.send_alert_push(alert, subscriber.push_tokens)
        return await notifier.send_notification_push(
            title=title, body=message, device_tokens=subscriber.push_tokens
        )

    async def _send_sms_notification(
        self,
        subscriber: Subscriber,
        alert: Optional[WeatherAlert],
        title: str,
        message: str,
    ) -> Dict[str, Any]:
        """Send SMS notification to subscriber via the configured gateway."""
        if not subscriber.phone:
            raise NotificationError("No phone number configured for subscriber")
        if not self.sms_notifiers:
            raise NotificationError("No SMS notifiers configured")

        body = self._generate_sms_body(alert, title, message)
        notifier = self.sms_notifiers[0]

        async with notifier as sms:
            if alert is not None:
                return await sms.send_sms(
                    subscriber.phone,
                    body,
                    alert_id=alert.id,
                    event=alert.event,
                )
            return await sms.send_sms(subscriber.phone, body)

    async def start_delivery_processor(self) -> None:
        """Start the delivery queue processor."""
        if not self.delivery_queue:
            self.logger.warning("Delivery queue not enabled")
            return

        self._running = True
        self.logger.info("Starting delivery queue processor")

        while self._running:
            try:
                # Process pending deliveries
                await self._process_pending_deliveries()

                # Wait before next cycle
                await asyncio.sleep(5)

            except Exception as e:
                self.logger.error(f"Error in delivery processor: {e}")
                await asyncio.sleep(10)

    async def stop_delivery_processor(self) -> None:
        """Stop the delivery queue processor."""
        self._running = False
        self.logger.info("Stopping delivery queue processor")

        # Wait for running tasks to complete
        if self._delivery_tasks:
            await asyncio.gather(*self._delivery_tasks, return_exceptions=True)

    async def _process_pending_deliveries(self) -> None:
        """Process pending deliveries in the queue."""
        if not self.delivery_queue:
            return

        pending_deliveries = self.delivery_queue.get_pending_deliveries()

        if not pending_deliveries:
            return

        # Limit concurrent deliveries
        max_concurrent = self.config.max_concurrent_deliveries
        current_tasks = len([t for t in self._delivery_tasks if not t.done()])

        if current_tasks >= max_concurrent:
            return

        # Process deliveries
        available_slots = max_concurrent - current_tasks
        deliveries_to_process = pending_deliveries[:available_slots]

        for delivery in deliveries_to_process:
            task = asyncio.create_task(self._process_delivery(delivery))
            self._delivery_tasks.add(task)
            task.add_done_callback(self._delivery_tasks.discard)

    async def _process_delivery(self, delivery: DeliveryItem) -> None:
        """Process a single delivery item."""
        try:
            # Update status to sending
            self.delivery_queue.update_delivery_status(delivery.delivery_id, DeliveryStatus.SENDING)

            # Send notification based on method
            if delivery.method == DeliveryMethod.EMAIL:
                await self._process_email_delivery(delivery)
            elif delivery.method == DeliveryMethod.WEBHOOK:
                await self._process_webhook_delivery(delivery)
            elif delivery.method == DeliveryMethod.PUSH:
                await self._process_push_delivery(delivery)
            elif delivery.method == DeliveryMethod.SMS:
                await self._process_sms_delivery(delivery)
            else:
                raise NotificationError(f"Unsupported delivery method: {delivery.method}")

        except Exception as e:
            self.logger.error(f"Failed to process delivery {delivery.delivery_id}: {e}")
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id, DeliveryStatus.FAILED, str(e)
            )

    async def _process_email_delivery(self, delivery: DeliveryItem) -> None:
        """Process email delivery."""
        if not self.email_notifiers:
            raise NotificationError("No email notifiers available")

        notifier = self.email_notifiers[0]

        result = await notifier.send_notification_email(
            subject=delivery.subject, body=delivery.body, recipients=[delivery.recipient]
        )

        if result.get("success", False):
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id, DeliveryStatus.SENT, response_data=result
            )
        else:
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id,
                DeliveryStatus.FAILED,
                error_message=result.get("error", "Unknown error"),
            )

    async def _process_webhook_delivery(self, delivery: DeliveryItem) -> None:
        """Process webhook delivery."""
        webhook_config = WebhookConfig(
            provider=webhook_provider_for_url(delivery.recipient),
            webhook_url=delivery.recipient,
            timeout_seconds=self.config.delivery_timeout_seconds,
            retry_count=self.config.max_retries,
            retry_delay_seconds=self.config.retry_delay_seconds,
        )

        try:
            notifier_cm = WebhookNotifier(webhook_config)
        except ValueError as e:
            self.logger.warning(
                "Webhook delivery %s rejected invalid URL: %s",
                delivery.delivery_id,
                e,
            )
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id,
                DeliveryStatus.FAILED,
                error_message=str(e),
            )
            return

        async with notifier_cm as notifier:
            result = await notifier.send_notification_webhook(
                title=delivery.subject, message=delivery.body
            )

            if result.get("success", False):
                self.delivery_queue.update_delivery_status(
                    delivery.delivery_id, DeliveryStatus.SENT, response_data=result
                )
            else:
                self.delivery_queue.update_delivery_status(
                    delivery.delivery_id,
                    DeliveryStatus.FAILED,
                    error_message=result.get("error", "Unknown error"),
                )

    async def _process_push_delivery(self, delivery: DeliveryItem) -> None:
        """Process push delivery."""
        if not self.push_notifiers:
            raise NotificationError("No push notifiers available")

        notifier = self.push_notifiers[0]

        result = await notifier.send_notification_push(
            title=delivery.subject, body=delivery.body, device_tokens=[delivery.recipient]
        )

        if result.get("success", False):
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id, DeliveryStatus.SENT, response_data=result
            )
        else:
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id,
                DeliveryStatus.FAILED,
                error_message=result.get("error", "Unknown error"),
            )

    async def _process_sms_delivery(self, delivery: DeliveryItem) -> None:
        """Process SMS delivery."""
        if not self.sms_notifiers:
            raise NotificationError("No SMS notifiers available")

        notifier = self.sms_notifiers[0]

        async with notifier as sms:
            result = await sms.send_sms(delivery.recipient, delivery.body)

        if result.get("success", False):
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id, DeliveryStatus.SENT, response_data=result
            )
        else:
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id,
                DeliveryStatus.FAILED,
                error_message=result.get("error", "Unknown error"),
            )

    def get_notification_stats(self) -> Dict[str, Any]:
        """Get notification system statistics."""
        stats = {
            "subscribers": self.subscriber_manager.get_subscriber_stats(),
            "notifiers": {
                "email": len(self.email_notifiers),
                "webhook": len(self.webhook_notifiers),
                "push": len(self.push_notifiers),
                "sms": len(self.sms_notifiers),
            },
            "templates": self.template_engine.get_available_templates(),
        }

        if self.delivery_queue:
            stats["delivery_queue"] = self.delivery_queue.get_queue_stats()

        return stats
