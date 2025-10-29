"""
Notification templates and personalization system for SkywarnPlus-NG.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import re

from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)


class TemplateType(Enum):
    """Template types."""
    EMAIL = "email"
    WEBHOOK = "webhook"
    PUSH = "push"
    SMS = "sms"


class TemplateFormat(Enum):
    """Template formats."""
    TEXT = "text"
    HTML = "html"
    MARKDOWN = "markdown"
    JSON = "json"


@dataclass
class NotificationTemplate:
    """Notification template definition."""
    
    template_id: str
    name: str
    description: str
    template_type: TemplateType
    format: TemplateFormat
    subject_template: str
    body_template: str
    enabled: bool = True
    variables: List[str] = None
    
    def __post_init__(self):
        if self.variables is None:
            self.variables = self._extract_variables()
    
    def _extract_variables(self) -> List[str]:
        """Extract variables from template strings."""
        variables = set()
        
        # Extract from subject template
        subject_vars = re.findall(r'\{\{(\w+)\}\}', self.subject_template)
        variables.update(subject_vars)
        
        # Extract from body template
        body_vars = re.findall(r'\{\{(\w+)\}\}', self.body_template)
        variables.update(body_vars)
        
        return list(variables)
    
    def render(self, context: Dict[str, Any]) -> Dict[str, str]:
        """Render template with context variables."""
        try:
            subject = self._render_string(self.subject_template, context)
            body = self._render_string(self.body_template, context)
            
            return {
                "subject": subject,
                "body": body
            }
            
        except Exception as e:
            logger.error(f"Failed to render template {self.template_id}: {e}")
            raise
    
    def _render_string(self, template: str, context: Dict[str, Any]) -> str:
        """Render a single template string."""
        result = template
        
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in result:
                # Format value based on template type
                formatted_value = self._format_value(value, key)
                result = result.replace(placeholder, str(formatted_value))
        
        return result
    
    def _format_value(self, value: Any, key: str) -> str:
        """Format a value based on its key and template type."""
        if value is None:
            return "N/A"
        
        # Date formatting
        if key in ["effective", "expires", "sent", "onset", "ends"] and isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Severity formatting
        if key == "severity" and hasattr(value, 'value'):
            severity_icons = {
                "Minor": "⚠️",
                "Moderate": "⚠️",
                "Severe": "🚨",
                "Extreme": "🚨"
            }
            return f"{severity_icons.get(value.value, '⚠️')} {value.value}"
        
        # Urgency formatting
        if key == "urgency" and hasattr(value, 'value'):
            urgency_icons = {
                "Past": "⏰",
                "Future": "⏳",
                "Expected": "🔔",
                "Immediate": "🚨"
            }
            return f"{urgency_icons.get(value.value, '🔔')} {value.value}"
        
        # Certainty formatting
        if key == "certainty" and hasattr(value, 'value'):
            certainty_icons = {
                "Unlikely": "❓",
                "Possible": "❔",
                "Likely": "✅",
                "Observed": "👁️"
            }
            return f"{certainty_icons.get(value.value, '❔')} {value.value}"
        
        # List formatting
        if isinstance(value, list):
            if key in ["county_codes", "geocode"]:
                return ", ".join(value)
            else:
                return ", ".join(str(item) for item in value)
        
        # Default formatting
        return str(value)


class TemplateEngine:
    """Template engine for notification rendering."""
    
    def __init__(self):
        self.templates: Dict[str, NotificationTemplate] = {}
        self.logger = logging.getLogger(__name__)
        self._load_default_templates()
    
    def _load_default_templates(self) -> None:
        """Load default notification templates."""
        # Email templates
        self.add_template(NotificationTemplate(
            template_id="email_alert_default",
            name="Default Email Alert",
            description="Default email template for weather alerts",
            template_type=TemplateType.EMAIL,
            format=TemplateFormat.HTML,
            subject_template="Weather Alert: {{event}} - {{area_desc}}",
            body_template="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{{event}} - {{area_desc}}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
        .container { max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header { background-color: #dc3545; color: white; padding: 15px; margin: -20px -20px 20px -20px; border-radius: 8px 8px 0 0; }
        .alert-title { font-size: 24px; font-weight: bold; margin: 0; }
        .alert-subtitle { font-size: 16px; margin: 5px 0 0 0; opacity: 0.9; }
        .alert-details { background-color: #f8f9fa; padding: 15px; border-radius: 4px; margin: 15px 0; }
        .detail-row { display: flex; justify-content: space-between; margin: 8px 0; }
        .detail-label { font-weight: bold; color: #495057; }
        .detail-value { color: #212529; }
        .description { margin: 15px 0; line-height: 1.6; }
        .instructions { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 4px; margin: 15px 0; }
        .footer { margin-top: 20px; padding-top: 15px; border-top: 1px solid #dee2e6; font-size: 12px; color: #6c757d; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="alert-title">⚠️ {{event}}</h1>
            <p class="alert-subtitle">{{area_desc}}</p>
        </div>
        
        <div class="alert-details">
            <div class="detail-row">
                <span class="detail-label">Severity:</span>
                <span class="detail-value">{{severity}}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Urgency:</span>
                <span class="detail-value">{{urgency}}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Certainty:</span>
                <span class="detail-value">{{certainty}}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Alert ID:</span>
                <span class="detail-value">{{alert_id}}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Effective:</span>
                <span class="detail-value">{{effective}}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Expires:</span>
                <span class="detail-value">{{expires}}</span>
            </div>
        </div>
        
        {% if headline %}
        <h3>Headline</h3>
        <p>{{headline}}</p>
        {% endif %}
        
        <div class="description">
            <h3>Description</h3>
            <p>{{description}}</p>
        </div>
        
        {% if instruction %}
        <div class="instructions">
            <h3>Instructions</h3>
            <p>{{instruction}}</p>
        </div>
        {% endif %}
        
        <div class="footer">
            <p>This alert was sent by SkywarnPlus-NG</p>
            <p>For more information, visit your local National Weather Service office</p>
        </div>
    </div>
</body>
</html>
            """.strip()
        ))
        
        # Webhook templates
        self.add_template(NotificationTemplate(
            template_id="webhook_alert_default",
            name="Default Webhook Alert",
            description="Default webhook template for weather alerts",
            template_type=TemplateType.WEBHOOK,
            format=TemplateFormat.JSON,
            subject_template="Weather Alert: {{event}}",
            body_template="""
{
    "username": "SkywarnPlus-NG",
    "attachments": [
        {
            "color": "#dc3545",
            "title": "⚠️ {{event}}",
            "text": "Weather alert for {{area_desc}}",
            "fields": [
                {
                    "title": "Area",
                    "value": "{{area_desc}}",
                    "short": true
                },
                {
                    "title": "Severity",
                    "value": "{{severity}}",
                    "short": true
                },
                {
                    "title": "Urgency",
                    "value": "{{urgency}}",
                    "short": true
                },
                {
                    "title": "Certainty",
                    "value": "{{certainty}}",
                    "short": true
                },
                {
                    "title": "Effective",
                    "value": "{{effective}}",
                    "short": true
                },
                {
                    "title": "Expires",
                    "value": "{{expires}}",
                    "short": true
                }
            ],
            "footer": "SkywarnPlus-NG"
        }
    ]
}
            """.strip()
        ))
        
        # Push notification templates
        self.add_template(NotificationTemplate(
            template_id="push_alert_default",
            name="Default Push Alert",
            description="Default push notification template for weather alerts",
            template_type=TemplateType.PUSH,
            format=TemplateFormat.TEXT,
            subject_template="Weather Alert: {{event}}",
            body_template="⚠️ {{event}} - {{area_desc}}\nSeverity: {{severity}}\nUrgency: {{urgency}}\nEffective: {{effective}}"
        ))
    
    def add_template(self, template: NotificationTemplate) -> None:
        """Add a template."""
        self.templates[template.template_id] = template
        self.logger.debug(f"Added template: {template.template_id}")
    
    def get_template(self, template_id: str) -> Optional[NotificationTemplate]:
        """Get a template by ID."""
        return self.templates.get(template_id)
    
    def get_templates_by_type(self, template_type: TemplateType) -> List[NotificationTemplate]:
        """Get templates by type."""
        return [
            template for template in self.templates.values()
            if template.template_type == template_type
        ]
    
    def render_alert_template(
        self, 
        template_id: str, 
        alert: WeatherAlert,
        custom_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Render an alert template."""
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        
        # Create context from alert
        context = self._create_alert_context(alert)
        
        # Add custom context
        if custom_context:
            context.update(custom_context)
        
        return template.render(context)
    
    def render_notification_template(
        self,
        template_id: str,
        title: str,
        message: str,
        custom_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Render a notification template."""
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        
        # Create context
        context = {
            "title": title,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Add custom context
        if custom_context:
            context.update(custom_context)
        
        return template.render(context)
    
    def _create_alert_context(self, alert: WeatherAlert) -> Dict[str, Any]:
        """Create context dictionary from weather alert."""
        return {
            "alert_id": alert.id,
            "event": alert.event,
            "headline": alert.headline or "",
            "description": alert.description or "",
            "area_desc": alert.area_desc,
            "severity": alert.severity,
            "urgency": alert.urgency,
            "certainty": alert.certainty,
            "status": alert.status,
            "category": alert.category,
            "effective": alert.effective,
            "expires": alert.expires,
            "sent": alert.sent,
            "onset": alert.onset,
            "ends": alert.ends,
            "instruction": alert.instruction or "",
            "sender": alert.sender or "",
            "sender_name": alert.sender_name or "",
            "county_codes": alert.county_codes or [],
            "geocode": alert.geocode or []
        }
    
    def get_available_templates(self) -> Dict[str, List[str]]:
        """Get available templates by type."""
        templates_by_type = {}
        
        for template_type in TemplateType:
            templates = self.get_templates_by_type(template_type)
            templates_by_type[template_type.value] = [
                {
                    "id": t.template_id,
                    "name": t.name,
                    "description": t.description,
                    "enabled": t.enabled
                }
                for t in templates
            ]
        
        return templates_by_type
    
    def create_custom_template(
        self,
        template_id: str,
        name: str,
        description: str,
        template_type: TemplateType,
        format: TemplateFormat,
        subject_template: str,
        body_template: str
    ) -> NotificationTemplate:
        """Create a custom template."""
        template = NotificationTemplate(
            template_id=template_id,
            name=name,
            description=description,
            template_type=template_type,
            format=format,
            subject_template=subject_template,
            body_template=body_template
        )
        
        self.add_template(template)
        return template
