# {{ title }}

Get up and running with the SkywarnPlus-NG API in minutes!

## Prerequisites

- SkywarnPlus-NG instance running (see [Installation Guide](../README.md))
- API accessible at `{{ base_url }}`
- Basic knowledge of HTTP and JSON

## Quick Start

### 1. Check System Status

First, verify that the system is running:

```bash
curl {{ base_url }}/api/status
```

Expected response:
```json
{
  "running": true,
  "active_alerts": 0,
  "nws_connected": true,
  "uptime_seconds": 3600
}
```

### 2. Get Active Alerts

Retrieve currently active weather alerts:

```bash
curl {{ base_url }}/api/alerts
```

### 3. Add a Notification Subscriber

Set up email notifications for weather alerts:

```bash
curl -X POST {{ base_url }}/api/notifications/subscribers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john.doe@example.com",
    "status": "active",
    "preferences": {
      "counties": ["TXC039"],
      "enabled_severities": ["Severe", "Extreme"],
      "enabled_methods": ["email"]
    }
  }'
```

### 4. Configure Email Notifications

Set up email SMTP settings:

```bash
curl -X POST {{ base_url }}/api/notifications/test-email \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "gmail",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "your-email@gmail.com",
    "password": "your-app-password",
    "use_tls": true
  }'
```

## Using SDKs

### Python SDK

```python
from skywarnplus_ng import SkywarnPlusClient

# Initialize client
client = SkywarnPlusClient(base_url="{{ base_url }}")

# Get system status
status = client.get_status()
print(f"System running: {status.running}")

# Get active alerts
alerts = client.get_alerts()
for alert in alerts:
    print(f"Alert: {alert.event} - {alert.area_desc}")

# Add subscriber
subscriber = client.add_subscriber(
    name="John Doe",
    email="john.doe@example.com",
    counties=["TXC039"],
    enabled_methods=["email"]
)
```

### JavaScript SDK

```javascript
const SkywarnPlus = require('skywarnplus-ng-sdk');

// Initialize client
const client = new SkywarnPlus.Client('{{ base_url }}');

// Get system status
client.getStatus().then(status => {
    console.log(`System running: ${status.running}`);
});

// Get active alerts
client.getAlerts().then(alerts => {
    alerts.forEach(alert => {
        console.log(`Alert: ${alert.event} - ${alert.area_desc}`);
    });
});

// Add subscriber
client.addSubscriber({
    name: 'John Doe',
    email: 'john.doe@example.com',
    counties: ['TXC039'],
    enabledMethods: ['email']
});
```

## WebSocket Real-time Updates

Connect to real-time updates:

```javascript
const ws = new WebSocket('ws://{{ base_url }}/ws');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    if (data.type === 'alert') {
        console.log(`New alert: ${data.alert.event}`);
    } else if (data.type === 'status') {
        console.log(`Status update: ${data.status.running}`);
    }
};
```

## Common Use Cases

### 1. Monitor Alerts for Specific County

```bash
# Get alerts for Brazoria County, TX
curl "{{ base_url }}/api/alerts?county=TXC039"
```

### 2. Filter by Severity

```bash
# Get only severe alerts
curl "{{ base_url }}/api/alerts?severity=Severe"
```

### 3. Get Alert History

```bash
# Get last 50 alerts
curl "{{ base_url }}/api/alerts/history?limit=50"
```

### 4. Check System Health

```bash
# Get detailed health information
curl {{ base_url }}/api/health
```

### 5. View System Logs

```bash
# Get recent logs
curl "{{ base_url }}/api/logs?limit=20&level=INFO"
```

## Configuration Management

### Get Current Configuration

```bash
curl {{ base_url }}/api/config
```

### Update Polling Interval

```bash
curl -X POST {{ base_url }}/api/config \
  -H "Content-Type: application/json" \
  -d '{"poll_interval": 300}'
```

### Reset to Defaults

```bash
curl -X POST {{ base_url }}/api/config/reset
```

## Notification Management

### Get All Subscribers

```bash
curl {{ base_url }}/api/notifications/subscribers
```

### Update Subscriber

```bash
curl -X PUT {{ base_url }}/api/notifications/subscribers/sub_001 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe Updated",
    "preferences": {
      "counties": ["TXC039", "TXC201"],
      "enabled_severities": ["Moderate", "Severe", "Extreme"]
    }
  }'
```

### Delete Subscriber

```bash
curl -X DELETE {{ base_url }}/api/notifications/subscribers/sub_001
```

## Error Handling

Always check HTTP status codes and handle errors appropriately:

```python
import requests

try:
    response = requests.get('{{ base_url }}/api/status')
    response.raise_for_status()
    data = response.json()
    print(f"Status: {data['running']}")
except requests.exceptions.HTTPError as e:
    print(f"HTTP error: {e}")
except requests.exceptions.RequestException as e:
    print(f"Request error: {e}")
```

## Next Steps

1. **Explore the API** - Use the interactive documentation at `{{ base_url }}/docs`
2. **Set up monitoring** - Configure health checks and alerting
3. **Customize notifications** - Create custom templates and workflows
4. **Integrate with your app** - Use the SDKs for seamless integration

## Getting Help

- **Documentation**: [Full API Reference](api_reference.md)
- **Interactive Docs**: `{{ base_url }}/docs`
- **GitHub**: [skywarnplus-ng/skywarnplus-ng](https://github.com/skywarnplus-ng/skywarnplus-ng)
- **Issues**: [Report bugs or request features](https://github.com/skywarnplus-ng/skywarnplus-ng/issues)

---

**API Version:** {{ version }}  
**Base URL:** {{ base_url }}
