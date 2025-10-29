"""
Main notification manager for SkywarnPlus-NG.
Coordinates all notification delivery methods and subscriber management.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from pathlib import Path

from .email import EmailNotifier, EmailConfig, EmailProvider
from .webhook import WebhookNotifier, WebhookConfig, WebhookProvider
from .push import PushNotifier, PushConfig, PushProvider
from .subscriber import SubscriberManager, Subscriber, NotificationMethod
from .templates import TemplateEngine, TemplateType
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
    
    # Delivery settings
    delivery_queue_enabled: bool = True
    max_concurrent_deliveries: int = 10
    delivery_timeout_seconds: int = 30
    
    # Subscriber settings
    subscriber_file: Optional[Path] = None
    
    def __post_init__(self):
        if self.email_configs is None:
            self.email_configs = []
        if self.webhook_configs is None:
            self.webhook_configs = []
        if self.push_configs is None:
            self.push_configs = []


class NotificationManager:
    """Main notification manager coordinating all delivery methods."""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.subscriber_manager = SubscriberManager(config.subscriber_file)
        self.template_engine = TemplateEngine()
        self.delivery_queue = DeliveryQueue() if config.delivery_queue_enabled else None
        
        # Initialize notifiers
        self.email_notifiers: List[EmailNotifier] = []
        self.webhook_notifiers: List[WebhookNotifier] = []
        self.push_notifiers: List[PushNotifier] = []
        
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
                    self.logger.info(f"Initialized email notifier for {email_config.provider.value}")
                except Exception as e:
                    self.logger.error(f"Failed to initialize email notifier: {e}")
        
        # Initialize webhook notifiers
        if self.config.webhook_enabled:
            for webhook_config in self.config.webhook_configs:
                try:
                    notifier = WebhookNotifier(webhook_config)
                    self.webhook_notifiers.append(notifier)
                    self.logger.info(f"Initialized webhook notifier for {webhook_config.provider.value}")
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
    
    async def send_alert_notifications(self, alert: WeatherAlert) -> Dict[str, Any]:
        """
        Send notifications for a weather alert.
        
        Args:
            alert: Weather alert to send notifications for
            
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
                "delivery_results": {}
            }
        
        # Generate notifications for each subscriber
        delivery_results = {}
        total_notifications = 0
        
        for subscriber in subscribers:
            try:
                # Generate notification content
                notification_content = await self._generate_notification_content(alert, subscriber)
                
                # Send notifications via enabled methods
                subscriber_results = await self._send_subscriber_notifications(
                    alert, subscriber, notification_content
                )
                
                delivery_results[subscriber.subscriber_id] = subscriber_results
                total_notifications += sum(
                    result.get("sent_count", 0) for result in subscriber_results.values()
                )
                
                # Record notification for subscriber
                subscriber.record_notification()
                self.subscriber_manager.update_subscriber(subscriber)
                
            except Exception as e:
                self.logger.error(f"Failed to send notifications to subscriber {subscriber.subscriber_id}: {e}")
                delivery_results[subscriber.subscriber_id] = {"error": str(e)}
        
        self.logger.info(f"Sent {total_notifications} notifications for alert {alert.id}")
        
        return {
            "success": True,
            "alert_id": alert.id,
            "subscribers_notified": len(subscribers),
            "total_notifications": total_notifications,
            "delivery_results": delivery_results
        }
    
    async def send_general_notification(
        self,
        title: str,
        message: str,
        recipients: Optional[List[str]] = None,
        methods: Optional[List[NotificationMethod]] = None
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
                self.subscriber_manager.get_subscriber_by_email(email)
                for email in recipients
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
                "delivery_results": {}
            }
        
        # Generate notification content
        notification_content = {
            "subject": title,
            "body": message,
            "html_body": message  # Simple HTML for now
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
                self.logger.error(f"Failed to send notification to subscriber {subscriber.subscriber_id}: {e}")
                delivery_results[subscriber.subscriber_id] = {"error": str(e)}
        
        self.logger.info(f"Sent {total_notifications} general notifications")
        
        return {
            "success": True,
            "title": title,
            "subscribers_notified": len(target_subscribers),
            "total_notifications": total_notifications,
            "delivery_results": delivery_results
        }
    
    async def _generate_notification_content(
        self, 
        alert: WeatherAlert, 
        subscriber: Subscriber
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
        
        return None
    
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
{alert.description or 'No description available'}

Effective: {alert.effective.strftime('%Y-%m-%d %H:%M:%S UTC') if alert.effective else 'N/A'}
Expires: {alert.expires.strftime('%Y-%m-%d %H:%M:%S UTC') if alert.expires else 'N/A'}

Instructions:
{alert.instruction or 'Please monitor local weather conditions and follow safety guidelines.'}

This alert was sent by SkywarnPlus-NG.
        """.strip()
        
        return {
            "subject": subject,
            "body": body,
            "html_body": body  # Simple HTML for now
        }
    
    async def _send_subscriber_notifications(
        self,
        alert: Optional[WeatherAlert],
        subscriber: Subscriber,
        content: Dict[str, str],
        methods: Optional[List[NotificationMethod]] = None
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
                self.logger.error(f"Email notification failed for subscriber {subscriber.subscriber_id}: {e}")
                results["email"] = {"success": False, "error": str(e)}
        
        # Send webhook notification
        if NotificationMethod.WEBHOOK in methods and self.webhook_notifiers and subscriber.webhook_url:
            try:
                webhook_result = await self._send_webhook_notification(
                    subscriber, content["subject"], content["body"]
                )
                results["webhook"] = webhook_result
            except Exception as e:
                self.logger.error(f"Webhook notification failed for subscriber {subscriber.subscriber_id}: {e}")
                results["webhook"] = {"success": False, "error": str(e)}
        
        # Send push notification
        if NotificationMethod.PUSH in methods and self.push_notifiers and subscriber.push_tokens:
            try:
                push_result = await self._send_push_notification(
                    subscriber, content["subject"], content["body"]
                )
                results["push"] = push_result
            except Exception as e:
                self.logger.error(f"Push notification failed for subscriber {subscriber.subscriber_id}: {e}")
                results["push"] = {"success": False, "error": str(e)}
        
        return results
    
    async def _send_email_notification(
        self, 
        subscriber: Subscriber, 
        subject: str, 
        body: str, 
        html_body: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send email notification to subscriber."""
        # Use the first available email notifier
        if not self.email_notifiers:
            raise NotificationError("No email notifiers configured")
        
        notifier = self.email_notifiers[0]
        
        return await notifier.send_notification_email(
            subject=subject,
            body=body,
            recipients=[subscriber.email],
            html_body=html_body
        )
    
    async def _send_webhook_notification(
        self, 
        subscriber: Subscriber, 
        title: str, 
        message: str
    ) -> Dict[str, Any]:
        """Send webhook notification to subscriber."""
        if not subscriber.webhook_url:
            raise NotificationError("No webhook URL configured for subscriber")
        
        # Create webhook config for subscriber
        webhook_config = WebhookConfig(
            provider=WebhookProvider.GENERIC,
            webhook_url=subscriber.webhook_url
        )
        
        async with WebhookNotifier(webhook_config) as notifier:
            return await notifier.send_notification_webhook(
                title=title,
                message=message
            )
    
    async def _send_push_notification(
        self, 
        subscriber: Subscriber, 
        title: str, 
        message: str
    ) -> Dict[str, Any]:
        """Send push notification to subscriber."""
        if not subscriber.push_tokens:
            raise NotificationError("No push tokens configured for subscriber")
        
        # Use the first available push notifier
        if not self.push_notifiers:
            raise NotificationError("No push notifiers configured")
        
        notifier = self.push_notifiers[0]
        
        return await notifier.send_notification_push(
            title=title,
            body=message,
            device_tokens=subscriber.push_tokens
        )
    
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
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id, DeliveryStatus.SENDING
            )
            
            # Send notification based on method
            if delivery.method == DeliveryMethod.EMAIL:
                await self._process_email_delivery(delivery)
            elif delivery.method == DeliveryMethod.WEBHOOK:
                await self._process_webhook_delivery(delivery)
            elif delivery.method == DeliveryMethod.PUSH:
                await self._process_push_delivery(delivery)
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
            subject=delivery.subject,
            body=delivery.body,
            recipients=[delivery.recipient]
        )
        
        if result.get("success", False):
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id, DeliveryStatus.SENT, response_data=result
            )
        else:
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id, DeliveryStatus.FAILED, 
                error_message=result.get("error", "Unknown error")
            )
    
    async def _process_webhook_delivery(self, delivery: DeliveryItem) -> None:
        """Process webhook delivery."""
        webhook_config = WebhookConfig(
            provider=WebhookProvider.GENERIC,
            webhook_url=delivery.recipient
        )
        
        async with WebhookNotifier(webhook_config) as notifier:
            result = await notifier.send_notification_webhook(
                title=delivery.subject,
                message=delivery.body
            )
            
            if result.get("success", False):
                self.delivery_queue.update_delivery_status(
                    delivery.delivery_id, DeliveryStatus.SENT, response_data=result
                )
            else:
                self.delivery_queue.update_delivery_status(
                    delivery.delivery_id, DeliveryStatus.FAILED,
                    error_message=result.get("error", "Unknown error")
                )
    
    async def _process_push_delivery(self, delivery: DeliveryItem) -> None:
        """Process push delivery."""
        if not self.push_notifiers:
            raise NotificationError("No push notifiers available")
        
        notifier = self.push_notifiers[0]
        
        result = await notifier.send_notification_push(
            title=delivery.subject,
            body=delivery.body,
            device_tokens=[delivery.recipient]
        )
        
        if result.get("success", False):
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id, DeliveryStatus.SENT, response_data=result
            )
        else:
            self.delivery_queue.update_delivery_status(
                delivery.delivery_id, DeliveryStatus.FAILED,
                error_message=result.get("error", "Unknown error")
            )
    
    def get_notification_stats(self) -> Dict[str, Any]:
        """Get notification system statistics."""
        stats = {
            "subscribers": self.subscriber_manager.get_subscriber_stats(),
            "notifiers": {
                "email": len(self.email_notifiers),
                "webhook": len(self.webhook_notifiers),
                "push": len(self.push_notifiers)
            },
            "templates": self.template_engine.get_available_templates()
        }
        
        if self.delivery_queue:
            stats["delivery_queue"] = self.delivery_queue.get_queue_stats()
        
        return stats
