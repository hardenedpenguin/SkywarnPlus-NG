"""
Postman collection generator for SkywarnPlus-NG API.
"""

import json
from typing import Dict, Any, List
from datetime import datetime


class PostmanCollectionGenerator:
    """Generate Postman collection for SkywarnPlus-NG API."""
    
    def __init__(self, base_url: str = "http://localhost:8080", version: str = "2.0.0"):
        self.base_url = base_url
        self.version = version
    
    def generate_collection(self) -> Dict[str, Any]:
        """Generate Postman collection."""
        return {
            "info": {
                "name": "SkywarnPlus-NG API",
                "description": "Complete API collection for SkywarnPlus-NG weather alert monitoring system",
                "version": self.version,
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "variable": [
                {
                    "key": "base_url",
                    "value": self.base_url,
                    "type": "string"
                },
                {
                    "key": "api_key",
                    "value": "your-api-key-here",
                    "type": "string"
                }
            ],
            "item": [
                self._generate_status_folder(),
                self._generate_alerts_folder(),
                self._generate_configuration_folder(),
                self._generate_notifications_folder(),
                self._generate_monitoring_folder(),
                self._generate_websocket_folder()
            ]
        }
    
    def _generate_status_folder(self) -> Dict[str, Any]:
        """Generate status folder with requests."""
        return {
            "name": "Status",
            "description": "System status and health endpoints",
            "item": [
                {
                    "name": "Get System Status",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/status",
                            "host": ["{{base_url}}"],
                            "path": ["api", "status"]
                        },
                        "description": "Retrieve current system status and health information"
                    },
                    "response": []
                },
                {
                    "name": "Get System Health",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/health",
                            "host": ["{{base_url}}"],
                            "path": ["api", "health"]
                        },
                        "description": "Retrieve detailed system health information"
                    },
                    "response": []
                }
            ]
        }
    
    def _generate_alerts_folder(self) -> Dict[str, Any]:
        """Generate alerts folder with requests."""
        return {
            "name": "Alerts",
            "description": "Weather alert management endpoints",
            "item": [
                {
                    "name": "Get Active Alerts",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/alerts",
                            "host": ["{{base_url}}"],
                            "path": ["api", "alerts"]
                        },
                        "description": "Retrieve currently active weather alerts"
                    },
                    "response": []
                },
                {
                    "name": "Get Alerts by County",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/alerts?county=TXC039",
                            "host": ["{{base_url}}"],
                            "path": ["api", "alerts"],
                            "query": [
                                {
                                    "key": "county",
                                    "value": "TXC039",
                                    "description": "County code filter"
                                }
                            ]
                        },
                        "description": "Get alerts for a specific county"
                    },
                    "response": []
                },
                {
                    "name": "Get Alerts by Severity",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/alerts?severity=Severe",
                            "host": ["{{base_url}}"],
                            "path": ["api", "alerts"],
                            "query": [
                                {
                                    "key": "severity",
                                    "value": "Severe",
                                    "description": "Severity level filter"
                                }
                            ]
                        },
                        "description": "Get alerts by severity level"
                    },
                    "response": []
                },
                {
                    "name": "Get Alert History",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/alerts/history?limit=50&offset=0",
                            "host": ["{{base_url}}"],
                            "path": ["api", "alerts", "history"],
                            "query": [
                                {
                                    "key": "limit",
                                    "value": "50",
                                    "description": "Maximum number of alerts to return"
                                },
                                {
                                    "key": "offset",
                                    "value": "0",
                                    "description": "Number of alerts to skip"
                                }
                            ]
                        },
                        "description": "Retrieve historical weather alerts"
                    },
                    "response": []
                }
            ]
        }
    
    def _generate_configuration_folder(self) -> Dict[str, Any]:
        """Generate configuration folder with requests."""
        return {
            "name": "Configuration",
            "description": "System configuration management endpoints",
            "item": [
                {
                    "name": "Get Configuration",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/config",
                            "host": ["{{base_url}}"],
                            "path": ["api", "config"]
                        },
                        "description": "Retrieve current system configuration"
                    },
                    "response": []
                },
                {
                    "name": "Update Configuration",
                    "request": {
                        "method": "POST",
                        "header": [
                            {
                                "key": "Content-Type",
                                "value": "application/json"
                            }
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": "{\n  \"poll_interval\": 300,\n  \"nws\": {\n    \"timeout\": 30\n  }\n}",
                            "options": {
                                "raw": {
                                    "language": "json"
                                }
                            }
                        },
                        "url": {
                            "raw": "{{base_url}}/api/config",
                            "host": ["{{base_url}}"],
                            "path": ["api", "config"]
                        },
                        "description": "Update system configuration settings"
                    },
                    "response": []
                },
                {
                    "name": "Reset Configuration",
                    "request": {
                        "method": "POST",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/config/reset",
                            "host": ["{{base_url}}"],
                            "path": ["api", "config", "reset"]
                        },
                        "description": "Reset configuration to defaults"
                    },
                    "response": []
                },
                {
                    "name": "Backup Configuration",
                    "request": {
                        "method": "POST",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/config/backup",
                            "host": ["{{base_url}}"],
                            "path": ["api", "config", "backup"]
                        },
                        "description": "Create configuration backup"
                    },
                    "response": []
                }
            ]
        }
    
    def _generate_notifications_folder(self) -> Dict[str, Any]:
        """Generate notifications folder with requests."""
        return {
            "name": "Notifications",
            "description": "Notification system management endpoints",
            "item": [
                {
                    "name": "Test Email Connection",
                    "request": {
                        "method": "POST",
                        "header": [
                            {
                                "key": "Content-Type",
                                "value": "application/json"
                            }
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": "{\n  \"provider\": \"gmail\",\n  \"smtp_server\": \"smtp.gmail.com\",\n  \"smtp_port\": 587,\n  \"username\": \"your-email@gmail.com\",\n  \"password\": \"your-app-password\",\n  \"use_tls\": true,\n  \"use_ssl\": false\n}",
                            "options": {
                                "raw": {
                                    "language": "json"
                                }
                            }
                        },
                        "url": {
                            "raw": "{{base_url}}/api/notifications/test-email",
                            "host": ["{{base_url}}"],
                            "path": ["api", "notifications", "test-email"]
                        },
                        "description": "Test email SMTP connection"
                    },
                    "response": []
                },
                {
                    "name": "Get All Subscribers",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/notifications/subscribers",
                            "host": ["{{base_url}}"],
                            "path": ["api", "notifications", "subscribers"]
                        },
                        "description": "Retrieve all notification subscribers"
                    },
                    "response": []
                },
                {
                    "name": "Add Subscriber",
                    "request": {
                        "method": "POST",
                        "header": [
                            {
                                "key": "Content-Type",
                                "value": "application/json"
                            }
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": "{\n  \"name\": \"John Doe\",\n  \"email\": \"john.doe@example.com\",\n  \"status\": \"active\",\n  \"preferences\": {\n    \"counties\": [\"TXC039\", \"TXC201\"],\n    \"enabled_severities\": [\"Severe\", \"Extreme\"],\n    \"enabled_urgencies\": [\"Immediate\", \"Expected\"],\n    \"enabled_certainties\": [\"Likely\", \"Observed\"],\n    \"enabled_methods\": [\"email\", \"webhook\"],\n    \"max_notifications_per_hour\": 10,\n    \"max_notifications_per_day\": 50\n  },\n  \"webhook_url\": \"https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK\"\n}",
                            "options": {
                                "raw": {
                                    "language": "json"
                                }
                            }
                        },
                        "url": {
                            "raw": "{{base_url}}/api/notifications/subscribers",
                            "host": ["{{base_url}}"],
                            "path": ["api", "notifications", "subscribers"]
                        },
                        "description": "Add a new notification subscriber"
                    },
                    "response": []
                },
                {
                    "name": "Update Subscriber",
                    "request": {
                        "method": "PUT",
                        "header": [
                            {
                                "key": "Content-Type",
                                "value": "application/json"
                            }
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": "{\n  \"name\": \"John Doe Updated\",\n  \"email\": \"john.doe@example.com\",\n  \"status\": \"active\",\n  \"preferences\": {\n    \"counties\": [\"TXC039\", \"TXC201\", \"TXC157\"],\n    \"enabled_severities\": [\"Moderate\", \"Severe\", \"Extreme\"],\n    \"enabled_urgencies\": [\"Immediate\", \"Expected\"],\n    \"enabled_certainties\": [\"Likely\", \"Observed\"],\n    \"enabled_methods\": [\"email\", \"webhook\", \"push\"],\n    \"max_notifications_per_hour\": 15,\n    \"max_notifications_per_day\": 100\n  }\n}",
                            "options": {
                                "raw": {
                                    "language": "json"
                                }
                            }
                        },
                        "url": {
                            "raw": "{{base_url}}/api/notifications/subscribers/{{subscriber_id}}",
                            "host": ["{{base_url}}"],
                            "path": ["api", "notifications", "subscribers", "{{subscriber_id}}"]
                        },
                        "description": "Update an existing subscriber"
                    },
                    "response": []
                },
                {
                    "name": "Delete Subscriber",
                    "request": {
                        "method": "DELETE",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/notifications/subscribers/{{subscriber_id}}",
                            "host": ["{{base_url}}"],
                            "path": ["api", "notifications", "subscribers", "{{subscriber_id}}"]
                        },
                        "description": "Delete a subscriber"
                    },
                    "response": []
                },
                {
                    "name": "Get All Templates",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/notifications/templates",
                            "host": ["{{base_url}}"],
                            "path": ["api", "notifications", "templates"]
                        },
                        "description": "Retrieve all notification templates"
                    },
                    "response": []
                },
                {
                    "name": "Add Template",
                    "request": {
                        "method": "POST",
                        "header": [
                            {
                                "key": "Content-Type",
                                "value": "application/json"
                            }
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": "{\n  \"name\": \"Custom Email Template\",\n  \"description\": \"Custom email template for weather alerts\",\n  \"template_type\": \"email\",\n  \"format\": \"html\",\n  \"subject_template\": \"Weather Alert: {{event}} - {{area_desc}}\",\n  \"body_template\": \"<h2>{{event}}</h2><p>{{description}}</p><p>Area: {{area_desc}}</p><p>Severity: {{severity}}</p>\",\n  \"enabled\": true\n}",
                            "options": {
                                "raw": {
                                    "language": "json"
                                }
                            }
                        },
                        "url": {
                            "raw": "{{base_url}}/api/notifications/templates",
                            "host": ["{{base_url}}"],
                            "path": ["api", "notifications", "templates"]
                        },
                        "description": "Add a new notification template"
                    },
                    "response": []
                },
                {
                    "name": "Get Notification Stats",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/notifications/stats",
                            "host": ["{{base_url}}"],
                            "path": ["api", "notifications", "stats"]
                        },
                        "description": "Get notification system statistics"
                    },
                    "response": []
                }
            ]
        }
    
    def _generate_monitoring_folder(self) -> Dict[str, Any]:
        """Generate monitoring folder with requests."""
        return {
            "name": "Monitoring",
            "description": "System monitoring and metrics endpoints",
            "item": [
                {
                    "name": "Get System Logs",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/logs?limit=100&level=INFO",
                            "host": ["{{base_url}}"],
                            "path": ["api", "logs"],
                            "query": [
                                {
                                    "key": "limit",
                                    "value": "100",
                                    "description": "Maximum number of log entries"
                                },
                                {
                                    "key": "level",
                                    "value": "INFO",
                                    "description": "Log level filter"
                                }
                            ]
                        },
                        "description": "Retrieve system logs with filtering"
                    },
                    "response": []
                },
                {
                    "name": "Get System Metrics",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/metrics",
                            "host": ["{{base_url}}"],
                            "path": ["api", "metrics"]
                        },
                        "description": "Retrieve system performance metrics"
                    },
                    "response": []
                },
                {
                    "name": "Get Database Stats",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/api/database/stats",
                            "host": ["{{base_url}}"],
                            "path": ["api", "database", "stats"]
                        },
                        "description": "Retrieve database statistics"
                    },
                    "response": []
                }
            ]
        }
    
    def _generate_websocket_folder(self) -> Dict[str, Any]:
        """Generate WebSocket folder with requests."""
        return {
            "name": "WebSocket",
            "description": "Real-time WebSocket connections",
            "item": [
                {
                    "name": "WebSocket Connection",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{base_url}}/ws",
                            "host": ["{{base_url}}"],
                            "path": ["ws"],
                            "protocol": "ws"
                        },
                        "description": "Establish WebSocket connection for real-time updates"
                    },
                    "response": []
                }
            ]
        }
    
    def save_collection(self, file_path: str) -> None:
        """Save Postman collection to file."""
        collection = self.generate_collection()
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(collection, f, indent=2, ensure_ascii=False)
    
    def generate_environment(self) -> Dict[str, Any]:
        """Generate Postman environment."""
        return {
            "id": "skywarnplus-ng-env",
            "name": "SkywarnPlus-NG Environment",
            "values": [
                {
                    "key": "base_url",
                    "value": self.base_url,
                    "enabled": True,
                    "type": "default"
                },
                {
                    "key": "api_key",
                    "value": "your-api-key-here",
                    "enabled": True,
                    "type": "secret"
                },
                {
                    "key": "subscriber_id",
                    "value": "sub_001",
                    "enabled": True,
                    "type": "default"
                },
                {
                    "key": "template_id",
                    "value": "template_001",
                    "enabled": True,
                    "type": "default"
                }
            ],
            "_postman_variable_scope": "environment"
        }
    
    def save_environment(self, file_path: str) -> None:
        """Save Postman environment to file."""
        environment = self.generate_environment()
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(environment, f, indent=2, ensure_ascii=False)
