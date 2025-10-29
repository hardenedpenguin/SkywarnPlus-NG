# {{ title }}

Welcome to the SkywarnPlus-NG API documentation. This comprehensive guide covers all available endpoints, request/response formats, and code examples.

## Table of Contents

- [Getting Started](#getting-started)
- [Authentication](#authentication)
- [Base URL](#base-url)
- [Rate Limiting](#rate-limiting)
- [Error Handling](#error-handling)
- [Endpoints](#endpoints)
  - [Status](#status)
  - [Alerts](#alerts)
  - [Configuration](#configuration)
  - [Notifications](#notifications)
  - [Monitoring](#monitoring)
  - [WebSocket](#websocket)
- [Data Models](#data-models)
- [Code Examples](#code-examples)
- [SDKs](#sdks)

## Getting Started

The SkywarnPlus-NG API provides programmatic access to weather alert monitoring and notification management. All API endpoints return JSON responses and use standard HTTP status codes.

### Base URL

```
{{ base_url }}
```

### Version

Current API version: **{{ version }}**

## Authentication

Currently, the API does not require authentication. This may change in future versions.

## Rate Limiting

API requests are not currently rate-limited, but this may be implemented in future versions. Please be respectful with your API usage.

## Error Handling

The API uses standard HTTP status codes to indicate success or failure:

- `200 OK` - Request successful
- `400 Bad Request` - Invalid request parameters
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

Error responses include a JSON object with error details:

```json
{
  "error": "Error message",
  "code": "ERROR_CODE",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Endpoints

### Status

#### Get System Status

Retrieve current system status and health information.

**Endpoint:** `GET /api/status`

**Response:**
```json
{
  "running": true,
  "last_poll": "2024-01-01T12:00:00Z",
  "active_alerts": 3,
  "total_alerts": 150,
  "nws_connected": true,
  "audio_available": true,
  "asterisk_available": true,
  "uptime_seconds": 86400
}
```

#### Get System Health

Retrieve detailed system health information.

**Endpoint:** `GET /api/health`

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z",
  "components": {
    "nws_api": {
      "status": "healthy",
      "message": "Connected",
      "last_check": "2024-01-01T12:00:00Z",
      "response_time_ms": 150
    },
    "audio_system": {
      "status": "healthy",
      "message": "Available",
      "last_check": "2024-01-01T12:00:00Z"
    }
  }
}
```

### Alerts

#### Get Active Alerts

Retrieve currently active weather alerts.

**Endpoint:** `GET /api/alerts`

**Query Parameters:**
- `county` (optional) - Filter by county code
- `severity` (optional) - Filter by severity level

**Response:**
```json
[
  {
    "id": "TXC039-20241201-001",
    "event": "Tornado Warning",
    "headline": "Tornado Warning for Brazoria County",
    "description": "A tornado warning has been issued...",
    "area_desc": "Brazoria County, TX",
    "severity": "Extreme",
    "urgency": "Immediate",
    "certainty": "Observed",
    "status": "Actual",
    "category": "Met",
    "effective": "2024-01-01T12:00:00Z",
    "expires": "2024-01-01T13:00:00Z",
    "sent": "2024-01-01T12:00:00Z",
    "county_codes": ["TXC039"],
    "geocode": ["TXC039"]
  }
]
```

#### Get Alert History

Retrieve historical weather alerts.

**Endpoint:** `GET /api/alerts/history`

**Query Parameters:**
- `limit` (optional) - Maximum number of alerts (default: 100, max: 1000)
- `offset` (optional) - Number of alerts to skip (default: 0)
- `start_date` (optional) - Start date filter (ISO 8601)
- `end_date` (optional) - End date filter (ISO 8601)

**Response:**
```json
{
  "alerts": [...],
  "total": 150,
  "limit": 100,
  "offset": 0
}
```

### Configuration

#### Get Configuration

Retrieve current system configuration.

**Endpoint:** `GET /api/config`

**Response:**
```json
{
  "enabled": true,
  "poll_interval": 300,
  "nws": {
    "base_url": "https://api.weather.gov",
    "timeout": 30
  },
  "counties": [...],
  "asterisk": {...},
  "audio": {...}
}
```

#### Update Configuration

Update system configuration settings.

**Endpoint:** `POST /api/config`

**Request Body:**
```json
{
  "poll_interval": 300,
  "nws": {
    "timeout": 30
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Configuration updated successfully"
}
```

### Notifications

#### Test Email Connection

Test email SMTP connection with provided credentials.

**Endpoint:** `POST /api/notifications/test-email`

**Request Body:**
```json
{
  "provider": "gmail",
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "username": "your-email@gmail.com",
  "password": "your-app-password",
  "use_tls": true,
  "use_ssl": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Email connection test completed"
}
```

#### Get Subscribers

Retrieve all notification subscribers.

**Endpoint:** `GET /api/notifications/subscribers`

**Response:**
```json
[
  {
    "subscriber_id": "sub_001",
    "name": "John Doe",
    "email": "john.doe@example.com",
    "status": "active",
    "preferences": {
      "counties": ["TXC039"],
      "enabled_severities": ["Severe", "Extreme"],
      "enabled_methods": ["email", "webhook"],
      "max_notifications_per_hour": 10,
      "max_notifications_per_day": 50
    },
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

#### Add Subscriber

Add a new notification subscriber.

**Endpoint:** `POST /api/notifications/subscribers`

**Request Body:**
```json
{
  "name": "John Doe",
  "email": "john.doe@example.com",
  "status": "active",
  "preferences": {
    "counties": ["TXC039", "TXC201"],
    "enabled_severities": ["Severe", "Extreme"],
    "enabled_urgencies": ["Immediate", "Expected"],
    "enabled_certainties": ["Likely", "Observed"],
    "enabled_methods": ["email", "webhook"],
    "max_notifications_per_hour": 10,
    "max_notifications_per_day": 50
  },
  "webhook_url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Subscriber added successfully",
  "subscriber_id": "sub_001"
}
```

### Monitoring

#### Get System Logs

Retrieve system logs with filtering options.

**Endpoint:** `GET /api/logs`

**Query Parameters:**
- `level` (optional) - Log level filter (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `limit` (optional) - Maximum number of log entries (default: 100)
- `since` (optional) - Get logs since timestamp (ISO 8601)

**Response:**
```json
[
  {
    "timestamp": "2024-01-01T12:00:00Z",
    "level": "INFO",
    "message": "System started successfully",
    "module": "skywarnplus_ng.core.application",
    "function": "start",
    "line": 45
  }
]
```

#### Get System Metrics

Retrieve system performance metrics.

**Endpoint:** `GET /api/metrics`

**Response:**
```json
{
  "cpu_usage": 25.5,
  "memory_usage": 60.2,
  "disk_usage": 45.8,
  "alerts_processed": 150,
  "alerts_per_hour": 12.5,
  "api_requests": 1250,
  "uptime_seconds": 86400
}
```

### WebSocket

#### WebSocket Connection

Establish WebSocket connection for real-time updates.

**Endpoint:** `GET /ws`

**Protocol:** WebSocket

**Connection URL:** `ws://{{ base_url }}/ws`

**Message Types:**
- `alert` - New weather alert
- `status` - System status update
- `health` - Health status update

**Example Message:**
```json
{
  "type": "alert",
  "alert": {
    "id": "TXC039-20241201-001",
    "event": "Tornado Warning",
    "area_desc": "Brazoria County, TX",
    "severity": "Extreme"
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

## Data Models

### WeatherAlert

```json
{
  "id": "string",
  "event": "string",
  "headline": "string",
  "description": "string",
  "area_desc": "string",
  "severity": "Minor|Moderate|Severe|Extreme",
  "urgency": "Past|Future|Expected|Immediate",
  "certainty": "Unlikely|Possible|Likely|Observed",
  "status": "Actual|Exercise|Test|Draft",
  "category": "Met|Geo|Safety|Rescue|Fire|Health|Env|Transport|Infra|CBRNE|Other",
  "effective": "2024-01-01T12:00:00Z",
  "expires": "2024-01-01T13:00:00Z",
  "sent": "2024-01-01T12:00:00Z",
  "onset": "2024-01-01T11:50:00Z",
  "ends": "2024-01-01T12:30:00Z",
  "instruction": "string",
  "sender": "string",
  "sender_name": "string",
  "county_codes": ["string"],
  "geocode": ["string"]
}
```

### Subscriber

```json
{
  "subscriber_id": "string",
  "name": "string",
  "email": "string",
  "status": "active|inactive|suspended|unsubscribed",
  "preferences": {
    "counties": ["string"],
    "states": ["string"],
    "enabled_severities": ["string"],
    "enabled_urgencies": ["string"],
    "enabled_certainties": ["string"],
    "enabled_methods": ["email|webhook|push|sms"],
    "max_notifications_per_hour": 10,
    "max_notifications_per_day": 50,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "06:00",
    "timezone": "UTC"
  },
  "phone": "string",
  "webhook_url": "string",
  "push_tokens": ["string"],
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

## Code Examples

### Python

```python
import requests

# Get system status
response = requests.get('{{ base_url }}/api/status')
status = response.json()
print(f"System running: {status['running']}")

# Get active alerts
alerts = requests.get('{{ base_url }}/api/alerts').json()
for alert in alerts:
    print(f"Alert: {alert['event']} - {alert['area_desc']}")
```

### JavaScript

```javascript
// Get system status
fetch('{{ base_url }}/api/status')
  .then(response => response.json())
  .then(status => {
    console.log(`System running: ${status.running}`);
  });

// Get active alerts
fetch('{{ base_url }}/api/alerts')
  .then(response => response.json())
  .then(alerts => {
    alerts.forEach(alert => {
      console.log(`Alert: ${alert.event} - ${alert.area_desc}`);
    });
  });
```

### cURL

```bash
# Get system status
curl -X GET '{{ base_url }}/api/status'

# Get active alerts
curl -X GET '{{ base_url }}/api/alerts'

# Add subscriber
curl -X POST '{{ base_url }}/api/notifications/subscribers' \
  -H 'Content-Type: application/json' \
  -d '{"name": "John Doe", "email": "john@example.com"}'
```

## SDKs

Official SDKs are available for:

- **Python** - `pip install skywarnplus-ng-sdk`
- **JavaScript/Node.js** - `npm install skywarnplus-ng-sdk`
- **TypeScript** - `npm install skywarnplus-ng-sdk`
- **Go** - `go get github.com/skywarnplus-ng/sdk-go`
- **Rust** - Add to `Cargo.toml`

For more information and examples, visit our [GitHub repository](https://github.com/skywarnplus-ng/skywarnplus-ng).

---

**API Version:** {{ version }}  
**Last Updated:** {{ "now" | strftime("%Y-%m-%d") }}  
**Base URL:** {{ base_url }}
