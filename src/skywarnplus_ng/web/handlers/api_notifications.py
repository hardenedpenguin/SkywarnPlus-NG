"""
Notifications, subscribers, and templates API handlers mixin.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp.web import Request, Response

from ...notifications.subscriber import Subscriber, SubscriptionStatus
from ...notifications.templates import (
    NotificationTemplate,
    TemplateFormat,
    TemplateType,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class NotificationsApiMixin:
    async def api_notifications_test_email_handler(self, request: Request) -> Response:
        """Handle email connection test."""
        try:
            data = await request.json()
            if not isinstance(data, dict):
                return web.json_response({"error": "JSON body must be an object"}, status=400)

            # Import notification modules
            from ...notifications.email import EmailNotifier, EmailConfig, EmailProvider

            # Password is redacted in the config UI; blank means use the saved value.
            password = data.get("password") or ""
            if isinstance(password, str):
                password = password.strip()
            if not password:
                password = self.config.notifications.email.password or ""

            provider = EmailProvider(data.get("provider", "gmail"))
            email_config = EmailConfig(
                provider=provider,
                smtp_server=data.get("smtp_server", ""),
                smtp_port=data.get("smtp_port", 587),
                use_tls=data.get("use_tls", True),
                use_ssl=data.get("use_ssl", False),
                username=data.get("username", ""),
                password=password,
                from_name=data.get("from_name", "SkywarnPlus-NG"),
            )

            # Test connection (worker thread; smtplib blocks the event loop)
            notifier = EmailNotifier(email_config)
            success = await asyncio.to_thread(notifier.test_connection)

            if success:
                return web.json_response(
                    {"success": True, "message": "Email connection test successful"}
                )
            else:
                return web.json_response(
                    {
                        "success": False,
                        "message": "Email connection test failed - check credentials and settings",
                        "error": "Connection test failed",
                    }
                )

        except Exception as e:
            logger.error(f"Error testing email connection: {e}")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def api_notifications_test_sms_handler(self, request: Request) -> Response:
        """Send a test SMS through Twilio."""
        try:
            data = await request.json()
            if not isinstance(data, dict):
                return web.json_response({"error": "JSON body must be an object"}, status=400)

            from ...notifications.phone import validate_phone_number
            from ...notifications.sms import SmsConfig, SmsNotifier

            to = (data.get("to") or "").strip()
            account_sid = (data.get("account_sid") or "").strip()
            from_number = (data.get("from_number") or "").strip()
            if not account_sid:
                return web.json_response(
                    {"success": False, "error": "Twilio Account SID is required"},
                    status=400,
                )
            if not from_number:
                return web.json_response(
                    {"success": False, "error": "Twilio From number is required"},
                    status=400,
                )

            ok, msg = validate_phone_number(to)
            if not to or not ok:
                return web.json_response(
                    {
                        "success": False,
                        "error": msg or "Valid test phone number required (E.164)",
                    },
                    status=400,
                )

            auth_token = data.get("auth_token")
            auth_clean = (
                str(auth_token).strip()
                if auth_token is not None and str(auth_token).strip()
                else None
            )
            # Auth token is redacted in the config UI; blank means use the saved value.
            if not auth_clean:
                saved = self.config.notifications.sms.auth_token
                auth_clean = str(saved).strip() if saved else None
            if not auth_clean:
                return web.json_response(
                    {"success": False, "error": "Twilio Auth Token is required"},
                    status=400,
                )

            try:
                sms_config = SmsConfig(
                    account_sid=account_sid,
                    auth_token=auth_clean,
                    from_number=from_number,
                    timeout_seconds=int(data.get("timeout_seconds") or 30),
                    max_length=int(data.get("max_length") or 160),
                )
                notifier = SmsNotifier(sms_config)
            except ValueError as exc:
                return web.json_response({"success": False, "error": str(exc)}, status=400)

            async with notifier as sms:
                result = await sms.send_sms(to, "SkywarnPlus-NG SMS test OK")

            if result.get("success"):
                return web.json_response(
                    {"success": True, "message": "SMS test sent successfully", "result": result}
                )
            return web.json_response(
                {
                    "success": False,
                    "message": "SMS test failed",
                    "error": result.get("error", "Unknown error"),
                    "result": result,
                }
            )

        except Exception as e:
            logger.error(f"Error testing Twilio SMS: {e}")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def api_notifications_subscribers_handler(self, request: Request) -> Response:
        """Handle subscribers list endpoint."""
        try:
            subscriber_manager = self._get_subscriber_manager()
            subscribers = subscriber_manager.get_all_subscribers()

            # Convert to dict format for JSON response
            subscribers_data = [subscriber.to_dict() for subscriber in subscribers]

            return web.json_response(subscribers_data)

        except Exception as e:
            logger.error(f"Error getting subscribers: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_add_subscriber_handler(self, request: Request) -> Response:
        """Handle add subscriber endpoint."""
        try:
            data = await request.json()
            if not isinstance(data, dict):
                return web.json_response({"error": "JSON body must be an object"}, status=400)
            subscriber_id = data.get("subscriber_id") or str(uuid.uuid4())
            name = (data.get("name") or "").strip()
            email = (data.get("email") or "").strip()

            if not name or not email:
                return web.json_response(
                    {"success": False, "error": "Name and email are required"},
                    status=400,
                )

            try:
                status = SubscriptionStatus(data.get("status", "active"))
            except ValueError:
                status = SubscriptionStatus.ACTIVE

            preferences = self._parse_subscription_preferences(data)

            sms_err = self._subscriber_phone_validation_error(
                data.get("phone"), preferences.enabled_methods
            )
            if sms_err:
                return web.json_response({"success": False, "error": sms_err}, status=400)

            wh_err = self._subscriber_webhook_validation_error(data.get("webhook_url"))
            if wh_err:
                return web.json_response(
                    {"success": False, "error": wh_err},
                    status=400,
                )
            wh_raw = data.get("webhook_url")
            webhook_clean = (
                str(wh_raw).strip() if wh_raw is not None and str(wh_raw).strip() else None
            )

            phone_raw = data.get("phone")
            phone_clean = None
            if phone_raw is not None and str(phone_raw).strip():
                from ...notifications.phone import normalize_phone_number

                phone_clean = normalize_phone_number(phone_raw)

            subscriber = Subscriber(
                subscriber_id=subscriber_id,
                name=name,
                email=email,
                status=status,
                preferences=preferences,
                phone=phone_clean,
                webhook_url=webhook_clean,
                push_tokens=self._normalize_list(data.get("push_tokens")),
            )

            # Add subscriber
            subscriber_manager = self._get_subscriber_manager()
            success = subscriber_manager.add_subscriber(subscriber)

            if success:
                return web.json_response(
                    {
                        "success": True,
                        "message": "Subscriber added successfully",
                        "subscriber_id": subscriber.subscriber_id,
                    }
                )
            else:
                return web.json_response(
                    {"success": False, "error": "Failed to add subscriber"}, status=400
                )

        except Exception as e:
            logger.error(f"Error adding subscriber: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_update_subscriber_handler(self, request: Request) -> Response:
        """Handle update subscriber endpoint."""
        try:
            subscriber_id = request.match_info["subscriber_id"]
            data = await request.json()
            if not isinstance(data, dict):
                return web.json_response({"error": "JSON body must be an object"}, status=400)

            # Get existing subscriber
            subscriber_manager = self._get_subscriber_manager()
            subscriber = subscriber_manager.get_subscriber(subscriber_id)

            if not subscriber:
                return web.json_response({"error": "Subscriber not found"}, status=404)

            # Update subscriber data
            if "name" in data:
                subscriber.name = data["name"].strip()
            if "email" in data:
                subscriber.email = data["email"].strip()
            if "status" in data:
                try:
                    subscriber.status = SubscriptionStatus(data["status"])
                except ValueError:
                    pass
            if "phone" in data:
                from ...notifications.phone import normalize_phone_number

                phone_raw = data["phone"]
                subscriber.phone = (
                    normalize_phone_number(phone_raw)
                    if phone_raw is not None and str(phone_raw).strip()
                    else None
                )
            if "webhook_url" in data:
                wh_err = self._subscriber_webhook_validation_error(data["webhook_url"])
                if wh_err:
                    return web.json_response({"error": wh_err}, status=400)
                wu = data["webhook_url"]
                subscriber.webhook_url = (
                    str(wu).strip() if wu is not None and str(wu).strip() else None
                )
            if "push_tokens" in data:
                subscriber.push_tokens = self._normalize_list(data.get("push_tokens"))

            # Update preferences if provided
            preference_keys = set(data.keys()).intersection(self.PREFERENCE_FIELDS)
            if "preferences" in data or preference_keys:
                subscriber.preferences = self._parse_subscription_preferences(
                    data, existing=subscriber.preferences
                )

            sms_err = self._subscriber_phone_validation_error(
                subscriber.phone, subscriber.preferences.enabled_methods
            )
            if sms_err:
                return web.json_response({"error": sms_err}, status=400)

            # Save updated subscriber
            success = subscriber_manager.update_subscriber(subscriber)

            if success:
                return web.json_response(
                    {"success": True, "message": "Subscriber updated successfully"}
                )
            else:
                return web.json_response(
                    {"success": False, "error": "Failed to update subscriber"}, status=400
                )

        except Exception as e:
            logger.error(f"Error updating subscriber: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_delete_subscriber_handler(self, request: Request) -> Response:
        """Handle delete subscriber endpoint."""
        try:
            subscriber_id = request.match_info["subscriber_id"]

            # Delete subscriber
            subscriber_manager = self._get_subscriber_manager()
            success = subscriber_manager.remove_subscriber(subscriber_id)

            if success:
                return web.json_response(
                    {"success": True, "message": "Subscriber deleted successfully"}
                )
            else:
                return web.json_response(
                    {"success": False, "error": "Subscriber not found"}, status=404
                )

        except Exception as e:
            logger.error(f"Error deleting subscriber: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_templates_handler(self, request: Request) -> Response:
        """Handle templates list endpoint."""
        try:
            template_engine = self._get_template_engine()
            templates = template_engine.get_available_templates()
            return web.json_response(templates)

        except Exception as e:
            logger.error(f"Error getting templates: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_template_detail_handler(self, request: Request) -> Response:
        """Handle template detail endpoint."""
        try:
            template_id = request.match_info["template_id"]
            template_engine = self._get_template_engine()
            template = template_engine.get_template_data(template_id)
            if not template:
                return web.json_response({"error": "Template not found"}, status=404)
            return web.json_response(template)
        except Exception as e:
            logger.error(f"Error getting template {template_id}: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_add_template_handler(self, request: Request) -> Response:
        """Handle add template endpoint."""
        try:
            data = await request.json()
            if not isinstance(data, dict):
                return web.json_response({"error": "JSON body must be an object"}, status=400)

            template_engine = self._get_template_engine()
            template_type_value = (data.get("template_type") or "email").lower()
            format_value = (data.get("format") or "text").lower()
            try:
                template_type = TemplateType(template_type_value)
                template_format = TemplateFormat(format_value)
            except ValueError:
                return web.json_response({"error": "Invalid template type or format"}, status=400)

            template = NotificationTemplate(
                template_id=data.get("template_id", str(uuid.uuid4())),
                name=data.get("name", ""),
                description=data.get("description", ""),
                template_type=template_type,
                format=template_format,
                subject_template=data.get("subject_template", ""),
                body_template=data.get("body_template", ""),
                enabled=data.get("enabled", True),
            )

            template_engine.add_template(template)

            return web.json_response(
                {
                    "success": True,
                    "message": "Template added successfully",
                    "template_id": template.template_id,
                }
            )

        except Exception as e:
            logger.error(f"Error adding template: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_update_template_handler(self, request: Request) -> Response:
        """Handle update template endpoint."""
        try:
            template_id = request.match_info["template_id"]
            data = await request.json()
            if not isinstance(data, dict):
                return web.json_response({"error": "JSON body must be an object"}, status=400)

            template_engine = self._get_template_engine()
            template = template_engine.get_template(template_id)

            if not template:
                return web.json_response({"error": "Template not found"}, status=404)

            # Update template data
            if "name" in data:
                template.name = data["name"]
            if "description" in data:
                template.description = data["description"]
            if "template_type" in data:
                try:
                    template.template_type = TemplateType((data["template_type"] or "").lower())
                except ValueError:
                    return web.json_response({"error": "Invalid template type"}, status=400)
            if "format" in data:
                try:
                    template.format = TemplateFormat((data["format"] or "").lower())
                except ValueError:
                    return web.json_response({"error": "Invalid template format"}, status=400)
            if "subject_template" in data:
                template.subject_template = data["subject_template"]
            if "body_template" in data:
                template.body_template = data["body_template"]
            if "enabled" in data:
                template.enabled = data["enabled"]

            # Update template
            template_engine.add_template(template)

            return web.json_response({"success": True, "message": "Template updated successfully"})

        except Exception as e:
            logger.error(f"Error updating template: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_delete_template_handler(self, request: Request) -> Response:
        """Handle delete template endpoint."""
        try:
            template_id = request.match_info["template_id"]

            template_engine = self._get_template_engine()
            template = template_engine.get_template(template_id)
            if not template:
                return web.json_response({"error": "Template not found"}, status=404)

            try:
                template_engine.remove_template(template_id)
            except ValueError as exc:
                return web.json_response({"error": str(exc)}, status=400)

            return web.json_response({"success": True, "message": "Template deleted successfully"})

        except Exception as e:
            logger.error(f"Error deleting template: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_notifications_stats_handler(self, request: Request) -> Response:
        """Handle notification statistics endpoint."""
        try:
            if getattr(self.app, "notification_manager", None):
                stats = self.app.notification_manager.get_notification_stats()
                return web.json_response(stats)

            subscriber_manager = self._get_subscriber_manager()
            subscriber_stats = subscriber_manager.get_subscriber_stats()
            stats = {
                "subscribers": subscriber_stats,
                "notifiers": {"email": 0, "webhook": 0, "push": 0, "sms": 0},
                "delivery_queue": {"total_items": 0, "pending": 0, "sent": 0, "failed": 0},
            }

            return web.json_response(stats)

        except Exception as e:
            logger.error(f"Error getting notification stats: {e}")
            return web.json_response({"error": str(e)}, status=500)
