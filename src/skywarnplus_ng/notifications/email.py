"""
Email notification system for SkywarnPlus-NG.
Supports Gmail and other major email providers with user credentials.
"""

import smtplib
import ssl
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import json

from ..core.models import WeatherAlert

logger = logging.getLogger(__name__)


class EmailProvider(Enum):
    """Supported email providers."""
    GMAIL = "gmail"
    OUTLOOK = "outlook"
    YAHOO = "yahoo"
    ICLOUD = "icloud"
    CUSTOM = "custom"


@dataclass
class EmailConfig:
    """Email configuration."""
    
    provider: EmailProvider
    smtp_server: str
    smtp_port: int
    use_tls: bool = True
    use_ssl: bool = False
    username: str = ""
    password: str = ""
    from_name: str = "SkywarnPlus-NG"
    from_email: str = ""
    reply_to: Optional[str] = None
    
    # Provider-specific settings
    app_password: bool = False  # For Gmail with 2FA
    
    def __post_init__(self):
        if not self.from_email:
            self.from_email = self.username


class EmailNotifier:
    """Email notification system supporting major providers."""
    
    # Provider configurations
    PROVIDER_CONFIGS = {
        EmailProvider.GMAIL: {
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "use_tls": True,
            "use_ssl": False,
            "app_password": True
        },
        EmailProvider.OUTLOOK: {
            "smtp_server": "smtp-mail.outlook.com",
            "smtp_port": 587,
            "use_tls": True,
            "use_ssl": False,
            "app_password": False
        },
        EmailProvider.YAHOO: {
            "smtp_server": "smtp.mail.yahoo.com",
            "smtp_port": 587,
            "use_tls": True,
            "use_ssl": False,
            "app_password": True
        },
        EmailProvider.ICLOUD: {
            "smtp_server": "smtp.mail.me.com",
            "smtp_port": 587,
            "use_tls": True,
            "use_ssl": False,
            "app_password": True
        }
    }
    
    def __init__(self, config: EmailConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{config.provider.value}")
        
        # Apply provider-specific configuration
        if config.provider in self.PROVIDER_CONFIGS:
            provider_config = self.PROVIDER_CONFIGS[config.provider]
            self.config.smtp_server = provider_config["smtp_server"]
            self.config.smtp_port = provider_config["smtp_port"]
            self.config.use_tls = provider_config["use_tls"]
            self.config.use_ssl = provider_config["use_ssl"]
            self.config.app_password = provider_config["app_password"]
    
    async def send_alert_email(
        self, 
        alert: WeatherAlert, 
        recipients: List[str],
        template: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Send weather alert email.
        
        Args:
            alert: Weather alert to send
            recipients: List of email addresses
            template: Custom email template (optional)
            attachments: List of attachments (optional)
            
        Returns:
            Delivery result
        """
        try:
            # Create email message
            message = self._create_alert_message(alert, recipients, template, attachments)
            
            # Send email
            success_count = await self._send_message(message, recipients)
            
            return {
                "success": True,
                "sent_count": success_count,
                "total_recipients": len(recipients),
                "alert_id": alert.id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to send alert email: {e}")
            return {
                "success": False,
                "error": str(e),
                "alert_id": alert.id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def send_notification_email(
        self,
        subject: str,
        body: str,
        recipients: List[str],
        html_body: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Send general notification email.
        
        Args:
            subject: Email subject
            body: Plain text body
            recipients: List of email addresses
            html_body: HTML body (optional)
            attachments: List of attachments (optional)
            
        Returns:
            Delivery result
        """
        try:
            # Create email message
            message = MIMEMultipart("alternative")
            message["From"] = f"{self.config.from_name} <{self.config.from_email}>"
            message["To"] = ", ".join(recipients)
            message["Subject"] = subject
            
            if self.config.reply_to:
                message["Reply-To"] = self.config.reply_to
            
            # Add text part
            text_part = MIMEText(body, "plain", "utf-8")
            message.attach(text_part)
            
            # Add HTML part if provided
            if html_body:
                html_part = MIMEText(html_body, "html", "utf-8")
                message.attach(html_part)
            
            # Add attachments
            if attachments:
                self._add_attachments(message, attachments)
            
            # Send email
            success_count = await self._send_message(message, recipients)
            
            return {
                "success": True,
                "sent_count": success_count,
                "total_recipients": len(recipients),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to send notification email: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def _create_alert_message(
        self, 
        alert: WeatherAlert, 
        recipients: List[str],
        template: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> MIMEMultipart:
        """Create email message for weather alert."""
        message = MIMEMultipart("alternative")
        message["From"] = f"{self.config.from_name} <{self.config.from_email}>"
        message["To"] = ", ".join(recipients)
        message["Subject"] = f"Weather Alert: {alert.event} - {alert.area_desc}"
        
        if self.config.reply_to:
            message["Reply-To"] = self.config.reply_to
        
        # Generate email content
        if template:
            text_body, html_body = self._render_template(alert, template)
        else:
            text_body, html_body = self._generate_default_content(alert)
        
        # Add text part
        text_part = MIMEText(text_body, "plain", "utf-8")
        message.attach(text_part)
        
        # Add HTML part
        html_part = MIMEText(html_body, "html", "utf-8")
        message.attach(html_part)
        
        # Add attachments
        if attachments:
            self._add_attachments(message, attachments)
        
        return message
    
    def _generate_default_content(self, alert: WeatherAlert) -> tuple[str, str]:
        """Generate default email content for alert."""
        # Text version
        text_body = f"""
WEATHER ALERT - {alert.event.upper()}

Area: {alert.area_desc}
Severity: {alert.severity.value}
Urgency: {alert.urgency.value}
Certainty: {alert.certainty.value}

Headline: {alert.headline or 'N/A'}

Description:
{alert.description or 'No description available'}

Alert Details:
- Alert ID: {alert.id}
- Effective: {alert.effective.strftime('%Y-%m-%d %H:%M:%S UTC') if alert.effective else 'N/A'}
- Expires: {alert.expires.strftime('%Y-%m-%d %H:%M:%S UTC') if alert.expires else 'N/A'}
- Sent: {alert.sent.strftime('%Y-%m-%d %H:%M:%S UTC') if alert.sent else 'N/A'}

Instructions:
{alert.instruction or 'Please monitor local weather conditions and follow safety guidelines.'}

This alert was sent by SkywarnPlus-NG.
For more information, visit your local National Weather Service office.
        """.strip()
        
        # HTML version
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Weather Alert - {alert.event}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background-color: #dc3545; color: white; padding: 15px; margin: -20px -20px 20px -20px; border-radius: 8px 8px 0 0; }}
        .alert-title {{ font-size: 24px; font-weight: bold; margin: 0; }}
        .alert-subtitle {{ font-size: 16px; margin: 5px 0 0 0; opacity: 0.9; }}
        .alert-details {{ background-color: #f8f9fa; padding: 15px; border-radius: 4px; margin: 15px 0; }}
        .detail-row {{ display: flex; justify-content: space-between; margin: 8px 0; }}
        .detail-label {{ font-weight: bold; color: #495057; }}
        .detail-value {{ color: #212529; }}
        .severity-{alert.severity.value.lower()} {{ color: #dc3545; font-weight: bold; }}
        .description {{ margin: 15px 0; line-height: 1.6; }}
        .instructions {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 4px; margin: 15px 0; }}
        .footer {{ margin-top: 20px; padding-top: 15px; border-top: 1px solid #dee2e6; font-size: 12px; color: #6c757d; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="alert-title">⚠️ {alert.event.upper()}</h1>
            <p class="alert-subtitle">{alert.area_desc}</p>
        </div>
        
        <div class="alert-details">
            <div class="detail-row">
                <span class="detail-label">Severity:</span>
                <span class="detail-value severity-{alert.severity.value.lower()}">{alert.severity.value}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Urgency:</span>
                <span class="detail-value">{alert.urgency.value}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Certainty:</span>
                <span class="detail-value">{alert.certainty.value}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Alert ID:</span>
                <span class="detail-value">{alert.id}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Effective:</span>
                <span class="detail-value">{alert.effective.strftime('%Y-%m-%d %H:%M:%S UTC') if alert.effective else 'N/A'}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Expires:</span>
                <span class="detail-value">{alert.expires.strftime('%Y-%m-%d %H:%M:%S UTC') if alert.expires else 'N/A'}</span>
            </div>
        </div>
        
        {f'<h3>Headline</h3><p>{alert.headline}</p>' if alert.headline else ''}
        
        <div class="description">
            <h3>Description</h3>
            <p>{alert.description or 'No description available'}</p>
        </div>
        
        {f'<div class="instructions"><h3>Instructions</h3><p>{alert.instruction}</p></div>' if alert.instruction else ''}
        
        <div class="footer">
            <p>This alert was sent by SkywarnPlus-NG</p>
            <p>For more information, visit your local National Weather Service office</p>
        </div>
    </div>
</body>
</html>
        """.strip()
        
        return text_body, html_body
    
    def _render_template(self, alert: WeatherAlert, template: str) -> tuple[str, str]:
        """Render custom template for alert."""
        # Simple template rendering - in a real implementation, you'd use Jinja2
        # For now, just use the default content
        return self._generate_default_content(alert)
    
    def _add_attachments(self, message: MIMEMultipart, attachments: List[Dict[str, Any]]) -> None:
        """Add attachments to email message."""
        for attachment in attachments:
            filename = attachment.get("filename", "attachment")
            content = attachment.get("content", b"")
            content_type = attachment.get("content_type", "application/octet-stream")
            
            part = MIMEBase(*content_type.split("/"))
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {filename}"
            )
            message.attach(part)
    
    async def _send_message(self, message: MIMEMultipart, recipients: List[str]) -> int:
        """Send email message via SMTP."""
        success_count = 0
        
        try:
            # Create SMTP connection
            if self.config.use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port, context=context)
            else:
                server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port)
            
            # Enable TLS if configured
            if self.config.use_tls and not self.config.use_ssl:
                server.starttls()
            
            # Login
            server.login(self.config.username, self.config.password)
            
            # Send email
            for recipient in recipients:
                try:
                    # Update recipient for each send
                    message["To"] = recipient
                    server.send_message(message, to_addrs=[recipient])
                    success_count += 1
                    self.logger.debug(f"Email sent successfully to {recipient}")
                except Exception as e:
                    self.logger.error(f"Failed to send email to {recipient}: {e}")
            
            server.quit()
            
        except Exception as e:
            self.logger.error(f"SMTP connection failed: {e}")
            raise
        
        return success_count
    
    def test_connection(self) -> bool:
        """Test SMTP connection."""
        try:
            if self.config.use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port, context=context)
            else:
                server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port)
            
            if self.config.use_tls and not self.config.use_ssl:
                server.starttls()
            
            server.login(self.config.username, self.config.password)
            server.quit()
            
            self.logger.info(f"SMTP connection test successful for {self.config.provider.value}")
            return True
            
        except Exception as e:
            self.logger.error(f"SMTP connection test failed for {self.config.provider.value}: {e}")
            return False
    
    @classmethod
    def create_gmail_config(
        cls, 
        username: str, 
        password: str, 
        from_name: str = "SkywarnPlus-NG"
    ) -> EmailConfig:
        """Create Gmail configuration."""
        return EmailConfig(
            provider=EmailProvider.GMAIL,
            smtp_server="smtp.gmail.com",
            smtp_port=587,
            use_tls=True,
            use_ssl=False,
            username=username,
            password=password,
            from_name=from_name,
            from_email=username,
            app_password=True
        )
    
    @classmethod
    def create_outlook_config(
        cls, 
        username: str, 
        password: str, 
        from_name: str = "SkywarnPlus-NG"
    ) -> EmailConfig:
        """Create Outlook configuration."""
        return EmailConfig(
            provider=EmailProvider.OUTLOOK,
            smtp_server="smtp-mail.outlook.com",
            smtp_port=587,
            use_tls=True,
            use_ssl=False,
            username=username,
            password=password,
            from_name=from_name,
            from_email=username,
            app_password=False
        )
    
    @classmethod
    def create_custom_config(
        cls,
        smtp_server: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        from_name: str = "SkywarnPlus-NG",
        use_tls: bool = True,
        use_ssl: bool = False
    ) -> EmailConfig:
        """Create custom SMTP configuration."""
        return EmailConfig(
            provider=EmailProvider.CUSTOM,
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            use_tls=use_tls,
            use_ssl=use_ssl,
            username=username,
            password=password,
            from_name=from_name,
            from_email=from_email,
            app_password=False
        )
