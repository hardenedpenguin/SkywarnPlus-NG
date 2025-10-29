"""
OpenAPI/Swagger specification generator for SkywarnPlus-NG.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ..core.models import WeatherAlert, AlertSeverity, AlertUrgency, AlertCertainty, AlertStatus, AlertCategory


@dataclass
class OpenAPISpec:
    """OpenAPI specification data structure."""
    
    openapi: str = "3.0.3"
    info: Dict[str, Any] = field(default_factory=dict)
    servers: List[Dict[str, str]] = field(default_factory=list)
    paths: Dict[str, Any] = field(default_factory=dict)
    components: Dict[str, Any] = field(default_factory=dict)
    tags: List[Dict[str, str]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "openapi": self.openapi,
            "info": self.info,
            "servers": self.servers,
            "paths": self.paths,
            "components": self.components,
            "tags": self.tags
        }


class OpenAPIGenerator:
    """Generate OpenAPI/Swagger specification for SkywarnPlus-NG API."""
    
    def __init__(self, base_url: str = "http://localhost:8080", version: str = "2.0.0"):
        self.base_url = base_url
        self.version = version
        self.spec = OpenAPISpec()
        self._generate_spec()
    
    def _generate_spec(self) -> None:
        """Generate the complete OpenAPI specification."""
        self._generate_info()
        self._generate_servers()
        self._generate_tags()
        self._generate_components()
        self._generate_paths()
    
    def _generate_info(self) -> None:
        """Generate API info section."""
        self.spec.info = {
            "title": "SkywarnPlus-NG API",
            "description": "Professional weather alert monitoring and notification system API",
            "version": self.version,
            "contact": {
                "name": "SkywarnPlus-NG Support",
                "email": "support@skywarnplus-ng.com"
            },
            "license": {
                "name": "MIT",
                "url": "https://opensource.org/licenses/MIT"
            }
        }
    
    def _generate_servers(self) -> None:
        """Generate servers section."""
        self.spec.servers = [
            {
                "url": self.base_url,
                "description": "Production server"
            },
            {
                "url": "http://localhost:8080",
                "description": "Development server"
            }
        ]
    
    def _generate_tags(self) -> None:
        """Generate API tags."""
        self.spec.tags = [
            {"name": "Status", "description": "System status and health endpoints"},
            {"name": "Alerts", "description": "Weather alert management"},
            {"name": "Configuration", "description": "System configuration management"},
            {"name": "Notifications", "description": "Notification system management"},
            {"name": "Database", "description": "Database statistics and management"},
            {"name": "Monitoring", "description": "System monitoring and metrics"},
            {"name": "WebSocket", "description": "Real-time WebSocket connections"}
        ]
    
    def _generate_components(self) -> None:
        """Generate components section with schemas."""
        self.spec.components = {
            "schemas": {
                "WeatherAlert": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Unique alert identifier"},
                        "event": {"type": "string", "description": "Alert event type"},
                        "headline": {"type": "string", "description": "Alert headline"},
                        "description": {"type": "string", "description": "Detailed alert description"},
                        "area_desc": {"type": "string", "description": "Affected area description"},
                        "severity": {"$ref": "#/components/schemas/AlertSeverity"},
                        "urgency": {"$ref": "#/components/schemas/AlertUrgency"},
                        "certainty": {"$ref": "#/components/schemas/AlertCertainty"},
                        "status": {"$ref": "#/components/schemas/AlertStatus"},
                        "category": {"$ref": "#/components/schemas/AlertCategory"},
                        "effective": {"type": "string", "format": "date-time", "description": "Alert effective time"},
                        "expires": {"type": "string", "format": "date-time", "description": "Alert expiration time"},
                        "sent": {"type": "string", "format": "date-time", "description": "Alert sent time"},
                        "onset": {"type": "string", "format": "date-time", "description": "Alert onset time"},
                        "ends": {"type": "string", "format": "date-time", "description": "Alert end time"},
                        "instruction": {"type": "string", "description": "Safety instructions"},
                        "sender": {"type": "string", "description": "Alert sender email"},
                        "sender_name": {"type": "string", "description": "Alert sender name"},
                        "county_codes": {"type": "array", "items": {"type": "string"}, "description": "Affected county codes"},
                        "geocode": {"type": "array", "items": {"type": "string"}, "description": "Geographic codes"}
                    },
                    "required": ["id", "event", "area_desc", "severity", "urgency", "certainty"]
                },
                "AlertSeverity": {
                    "type": "string",
                    "enum": ["Minor", "Moderate", "Severe", "Extreme"],
                    "description": "Alert severity level"
                },
                "AlertUrgency": {
                    "type": "string",
                    "enum": ["Past", "Future", "Expected", "Immediate"],
                    "description": "Alert urgency level"
                },
                "AlertCertainty": {
                    "type": "string",
                    "enum": ["Unlikely", "Possible", "Likely", "Observed"],
                    "description": "Alert certainty level"
                },
                "AlertStatus": {
                    "type": "string",
                    "enum": ["Actual", "Exercise", "Test", "Draft"],
                    "description": "Alert status"
                },
                "AlertCategory": {
                    "type": "string",
                    "enum": ["Met", "Geo", "Safety", "Rescue", "Fire", "Health", "Env", "Transport", "Infra", "CBRNE", "Other"],
                    "description": "Alert category"
                },
                "SystemStatus": {
                    "type": "object",
                    "properties": {
                        "running": {"type": "boolean", "description": "System running status"},
                        "last_poll": {"type": "string", "format": "date-time", "description": "Last NWS API poll"},
                        "active_alerts": {"type": "integer", "description": "Number of active alerts"},
                        "total_alerts": {"type": "integer", "description": "Total alerts processed"},
                        "nws_connected": {"type": "boolean", "description": "NWS API connection status"},
                        "audio_available": {"type": "boolean", "description": "Audio system availability"},
                        "asterisk_available": {"type": "boolean", "description": "Asterisk system availability"},
                        "uptime_seconds": {"type": "number", "description": "System uptime in seconds"}
                    }
                },
                "HealthCheck": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["healthy", "degraded", "unhealthy"]},
                        "timestamp": {"type": "string", "format": "date-time"},
                        "components": {
                            "type": "object",
                            "properties": {
                                "nws_api": {"$ref": "#/components/schemas/ComponentHealth"},
                                "audio_system": {"$ref": "#/components/schemas/ComponentHealth"},
                                "asterisk": {"$ref": "#/components/schemas/ComponentHealth"},
                                "database": {"$ref": "#/components/schemas/ComponentHealth"},
                                "notifications": {"$ref": "#/components/schemas/ComponentHealth"}
                            }
                        }
                    }
                },
                "ComponentHealth": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["healthy", "degraded", "unhealthy"]},
                        "message": {"type": "string", "description": "Status message"},
                        "last_check": {"type": "string", "format": "date-time"},
                        "response_time_ms": {"type": "number", "description": "Response time in milliseconds"}
                    }
                },
                "ErrorResponse": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string", "description": "Error message"},
                        "code": {"type": "string", "description": "Error code"},
                        "timestamp": {"type": "string", "format": "date-time"}
                    }
                },
                "Subscriber": {
                    "type": "object",
                    "properties": {
                        "subscriber_id": {"type": "string", "description": "Unique subscriber identifier"},
                        "name": {"type": "string", "description": "Subscriber name"},
                        "email": {"type": "string", "format": "email", "description": "Subscriber email"},
                        "status": {"type": "string", "enum": ["active", "inactive", "suspended", "unsubscribed"]},
                        "preferences": {"$ref": "#/components/schemas/SubscriptionPreferences"},
                        "phone": {"type": "string", "description": "Phone number"},
                        "webhook_url": {"type": "string", "format": "uri", "description": "Webhook URL"},
                        "push_tokens": {"type": "array", "items": {"type": "string"}, "description": "Push notification tokens"},
                        "created_at": {"type": "string", "format": "date-time"},
                        "updated_at": {"type": "string", "format": "date-time"}
                    }
                },
                "SubscriptionPreferences": {
                    "type": "object",
                    "properties": {
                        "counties": {"type": "array", "items": {"type": "string"}, "description": "Subscribed counties"},
                        "states": {"type": "array", "items": {"type": "string"}, "description": "Subscribed states"},
                        "enabled_severities": {"type": "array", "items": {"$ref": "#/components/schemas/AlertSeverity"}},
                        "enabled_urgencies": {"type": "array", "items": {"$ref": "#/components/schemas/AlertUrgency"}},
                        "enabled_certainties": {"type": "array", "items": {"$ref": "#/components/schemas/AlertCertainty"}},
                        "enabled_methods": {"type": "array", "items": {"type": "string", "enum": ["email", "webhook", "push", "sms"]}},
                        "max_notifications_per_hour": {"type": "integer", "minimum": 1, "maximum": 100},
                        "max_notifications_per_day": {"type": "integer", "minimum": 1, "maximum": 1000},
                        "quiet_hours_start": {"type": "string", "pattern": "^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"},
                        "quiet_hours_end": {"type": "string", "pattern": "^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"},
                        "timezone": {"type": "string", "default": "UTC"}
                    }
                },
                "NotificationTemplate": {
                    "type": "object",
                    "properties": {
                        "template_id": {"type": "string", "description": "Unique template identifier"},
                        "name": {"type": "string", "description": "Template name"},
                        "description": {"type": "string", "description": "Template description"},
                        "template_type": {"type": "string", "enum": ["email", "webhook", "push", "sms"]},
                        "format": {"type": "string", "enum": ["text", "html", "markdown", "json"]},
                        "subject_template": {"type": "string", "description": "Subject template"},
                        "body_template": {"type": "string", "description": "Body template"},
                        "enabled": {"type": "boolean", "default": True},
                        "variables": {"type": "array", "items": {"type": "string"}, "description": "Template variables"}
                    }
                }
            },
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "API key for authentication"
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "JWT token for authentication"
                }
            }
        }
    
    def _generate_paths(self) -> None:
        """Generate API paths."""
        self.spec.paths = {
            "/api/status": self._generate_status_endpoint(),
            "/api/alerts": self._generate_alerts_endpoint(),
            "/api/alerts/history": self._generate_alerts_history_endpoint(),
            "/api/health": self._generate_health_endpoint(),
            "/api/logs": self._generate_logs_endpoint(),
            "/api/metrics": self._generate_metrics_endpoint(),
            "/api/database/stats": self._generate_database_stats_endpoint(),
            "/api/config": self._generate_config_endpoints(),
            "/api/notifications/test-email": self._generate_notifications_test_email_endpoint(),
            "/api/notifications/subscribers": self._generate_subscribers_endpoints(),
            "/api/notifications/templates": self._generate_templates_endpoints(),
            "/api/notifications/stats": self._generate_notifications_stats_endpoint(),
            "/ws": self._generate_websocket_endpoint()
        }
    
    def _generate_status_endpoint(self) -> Dict[str, Any]:
        """Generate status endpoint specification."""
        return {
            "get": {
                "tags": ["Status"],
                "summary": "Get system status",
                "description": "Retrieve current system status and health information",
                "responses": {
                    "200": {
                        "description": "System status retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/SystemStatus"}
                            }
                        }
                    },
                    "500": {
                        "description": "Internal server error",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_alerts_endpoint(self) -> Dict[str, Any]:
        """Generate alerts endpoint specification."""
        return {
            "get": {
                "tags": ["Alerts"],
                "summary": "Get active alerts",
                "description": "Retrieve currently active weather alerts",
                "parameters": [
                    {
                        "name": "county",
                        "in": "query",
                        "description": "Filter by county code",
                        "required": False,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "severity",
                        "in": "query",
                        "description": "Filter by severity level",
                        "required": False,
                        "schema": {"$ref": "#/components/schemas/AlertSeverity"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Active alerts retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/WeatherAlert"}
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_alerts_history_endpoint(self) -> Dict[str, Any]:
        """Generate alerts history endpoint specification."""
        return {
            "get": {
                "tags": ["Alerts"],
                "summary": "Get alert history",
                "description": "Retrieve historical weather alerts",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "description": "Maximum number of alerts to return",
                        "required": False,
                        "schema": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100}
                    },
                    {
                        "name": "offset",
                        "in": "query",
                        "description": "Number of alerts to skip",
                        "required": False,
                        "schema": {"type": "integer", "minimum": 0, "default": 0}
                    },
                    {
                        "name": "start_date",
                        "in": "query",
                        "description": "Start date for filtering (ISO 8601)",
                        "required": False,
                        "schema": {"type": "string", "format": "date-time"}
                    },
                    {
                        "name": "end_date",
                        "in": "query",
                        "description": "End date for filtering (ISO 8601)",
                        "required": False,
                        "schema": {"type": "string", "format": "date-time"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Alert history retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "alerts": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/WeatherAlert"}
                                        },
                                        "total": {"type": "integer", "description": "Total number of alerts"},
                                        "limit": {"type": "integer", "description": "Limit applied"},
                                        "offset": {"type": "integer", "description": "Offset applied"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_health_endpoint(self) -> Dict[str, Any]:
        """Generate health endpoint specification."""
        return {
            "get": {
                "tags": ["Monitoring"],
                "summary": "Get system health",
                "description": "Retrieve detailed system health information",
                "responses": {
                    "200": {
                        "description": "Health information retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/HealthCheck"}
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_logs_endpoint(self) -> Dict[str, Any]:
        """Generate logs endpoint specification."""
        return {
            "get": {
                "tags": ["Monitoring"],
                "summary": "Get system logs",
                "description": "Retrieve system logs with filtering options",
                "parameters": [
                    {
                        "name": "level",
                        "in": "query",
                        "description": "Log level filter",
                        "required": False,
                        "schema": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]}
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "description": "Maximum number of log entries",
                        "required": False,
                        "schema": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100}
                    },
                    {
                        "name": "since",
                        "in": "query",
                        "description": "Get logs since timestamp (ISO 8601)",
                        "required": False,
                        "schema": {"type": "string", "format": "date-time"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Logs retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "timestamp": {"type": "string", "format": "date-time"},
                                            "level": {"type": "string"},
                                            "message": {"type": "string"},
                                            "module": {"type": "string"},
                                            "function": {"type": "string"},
                                            "line": {"type": "integer"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_metrics_endpoint(self) -> Dict[str, Any]:
        """Generate metrics endpoint specification."""
        return {
            "get": {
                "tags": ["Monitoring"],
                "summary": "Get system metrics",
                "description": "Retrieve system performance metrics",
                "responses": {
                    "200": {
                        "description": "Metrics retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "cpu_usage": {"type": "number", "description": "CPU usage percentage"},
                                        "memory_usage": {"type": "number", "description": "Memory usage percentage"},
                                        "disk_usage": {"type": "number", "description": "Disk usage percentage"},
                                        "alerts_processed": {"type": "integer", "description": "Total alerts processed"},
                                        "alerts_per_hour": {"type": "number", "description": "Average alerts per hour"},
                                        "api_requests": {"type": "integer", "description": "Total API requests"},
                                        "uptime_seconds": {"type": "number", "description": "System uptime in seconds"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_database_stats_endpoint(self) -> Dict[str, Any]:
        """Generate database stats endpoint specification."""
        return {
            "get": {
                "tags": ["Database"],
                "summary": "Get database statistics",
                "description": "Retrieve database statistics and health information",
                "responses": {
                    "200": {
                        "description": "Database statistics retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "total_alerts": {"type": "integer"},
                                        "active_alerts": {"type": "integer"},
                                        "database_size_mb": {"type": "number"},
                                        "last_backup": {"type": "string", "format": "date-time"},
                                        "connection_pool": {
                                            "type": "object",
                                            "properties": {
                                                "active_connections": {"type": "integer"},
                                                "max_connections": {"type": "integer"},
                                                "idle_connections": {"type": "integer"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_config_endpoints(self) -> Dict[str, Any]:
        """Generate configuration endpoints specification."""
        return {
            "get": {
                "tags": ["Configuration"],
                "summary": "Get system configuration",
                "description": "Retrieve current system configuration",
                "responses": {
                    "200": {
                        "description": "Configuration retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        }
                    }
                }
            },
            "post": {
                "tags": ["Configuration"],
                "summary": "Update system configuration",
                "description": "Update system configuration settings",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"type": "object"}
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Configuration updated successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "message": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "400": {
                        "description": "Invalid configuration",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_notifications_test_email_endpoint(self) -> Dict[str, Any]:
        """Generate test email endpoint specification."""
        return {
            "post": {
                "tags": ["Notifications"],
                "summary": "Test email connection",
                "description": "Test email SMTP connection with provided credentials",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "provider": {"type": "string", "enum": ["gmail", "outlook", "yahoo", "icloud", "custom"]},
                                    "smtp_server": {"type": "string"},
                                    "smtp_port": {"type": "integer"},
                                    "username": {"type": "string"},
                                    "password": {"type": "string"},
                                    "use_tls": {"type": "boolean"},
                                    "use_ssl": {"type": "boolean"}
                                },
                                "required": ["provider", "smtp_server", "smtp_port", "username", "password"]
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Email connection test completed",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "message": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_subscribers_endpoints(self) -> Dict[str, Any]:
        """Generate subscribers endpoints specification."""
        return {
            "get": {
                "tags": ["Notifications"],
                "summary": "Get all subscribers",
                "description": "Retrieve list of all notification subscribers",
                "responses": {
                    "200": {
                        "description": "Subscribers retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Subscriber"}
                                }
                            }
                        }
                    }
                }
            },
            "post": {
                "tags": ["Notifications"],
                "summary": "Add new subscriber",
                "description": "Add a new notification subscriber",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Subscriber"}
                        }
                    }
                },
                "responses": {
                    "201": {
                        "description": "Subscriber added successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "message": {"type": "string"},
                                        "subscriber_id": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_templates_endpoints(self) -> Dict[str, Any]:
        """Generate templates endpoints specification."""
        return {
            "get": {
                "tags": ["Notifications"],
                "summary": "Get all templates",
                "description": "Retrieve list of all notification templates",
                "responses": {
                    "200": {
                        "description": "Templates retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/NotificationTemplate"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "post": {
                "tags": ["Notifications"],
                "summary": "Add new template",
                "description": "Add a new notification template",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/NotificationTemplate"}
                        }
                    }
                },
                "responses": {
                    "201": {
                        "description": "Template added successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "message": {"type": "string"},
                                        "template_id": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_notifications_stats_endpoint(self) -> Dict[str, Any]:
        """Generate notifications stats endpoint specification."""
        return {
            "get": {
                "tags": ["Notifications"],
                "summary": "Get notification statistics",
                "description": "Retrieve notification system statistics",
                "responses": {
                    "200": {
                        "description": "Statistics retrieved successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "subscribers": {
                                            "type": "object",
                                            "properties": {
                                                "total_subscribers": {"type": "integer"},
                                                "active_subscribers": {"type": "integer"},
                                                "inactive_subscribers": {"type": "integer"}
                                            }
                                        },
                                        "notifiers": {
                                            "type": "object",
                                            "properties": {
                                                "email": {"type": "integer"},
                                                "webhook": {"type": "integer"},
                                                "push": {"type": "integer"}
                                            }
                                        },
                                        "delivery_queue": {
                                            "type": "object",
                                            "properties": {
                                                "total_items": {"type": "integer"},
                                                "pending": {"type": "integer"},
                                                "sent": {"type": "integer"},
                                                "failed": {"type": "integer"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_websocket_endpoint(self) -> Dict[str, Any]:
        """Generate WebSocket endpoint specification."""
        return {
            "get": {
                "tags": ["WebSocket"],
                "summary": "WebSocket connection",
                "description": "Establish WebSocket connection for real-time updates",
                "parameters": [
                    {
                        "name": "token",
                        "in": "query",
                        "description": "Authentication token",
                        "required": False,
                        "schema": {"type": "string"}
                    }
                ],
                "responses": {
                    "101": {
                        "description": "Switching protocols to WebSocket"
                    },
                    "400": {
                        "description": "Bad request"
                    },
                    "401": {
                        "description": "Unauthorized"
                    }
                }
            }
        }
    
    def generate_spec(self) -> Dict[str, Any]:
        """Generate the complete OpenAPI specification."""
        return self.spec.to_dict()
    
    def save_spec(self, file_path: str) -> None:
        """Save OpenAPI specification to file."""
        spec_dict = self.generate_spec()
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(spec_dict, f, indent=2, ensure_ascii=False)
    
    def get_yaml_spec(self) -> str:
        """Get OpenAPI specification in YAML format."""
        import yaml
        spec_dict = self.generate_spec()
        return yaml.dump(spec_dict, default_flow_style=False, sort_keys=False)
