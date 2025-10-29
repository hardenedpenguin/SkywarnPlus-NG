"""
Code examples generator for SkywarnPlus-NG API.
"""

from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class CodeExample:
    """Code example data structure."""
    language: str
    title: str
    description: str
    code: str
    endpoint: str
    method: str


class CodeExampleGenerator:
    """Generate code examples for SkywarnPlus-NG API in multiple languages."""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
    
    def generate_python_examples(self) -> List[CodeExample]:
        """Generate Python code examples."""
        examples = []
        
        # Basic client setup
        examples.append(CodeExample(
            language="python",
            title="Basic Client Setup",
            description="Set up the SkywarnPlus-NG API client",
            code='''import requests
import json

class SkywarnPlusClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "SkywarnPlus-Python-Client/1.0"
        })
    
    def _make_request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

# Initialize client
client = SkywarnPlusClient()''',
            endpoint="/",
            method="GET"
        ))
        
        # Get status
        examples.append(CodeExample(
            language="python",
            title="Get System Status",
            description="Retrieve current system status",
            code='''# Get system status
status = client._make_request("GET", "/api/status")
print(f"System running: {status['running']}")
print(f"Active alerts: {status['active_alerts']}")
print(f"Uptime: {status['uptime_seconds']} seconds")''',
            endpoint="/api/status",
            method="GET"
        ))
        
        # Get alerts
        examples.append(CodeExample(
            language="python",
            title="Get Active Alerts",
            description="Retrieve currently active weather alerts",
            code='''# Get all active alerts
alerts = client._make_request("GET", "/api/alerts")
print(f"Found {len(alerts)} active alerts")

for alert in alerts:
    print(f"Alert: {alert['event']} - {alert['area_desc']}")
    print(f"Severity: {alert['severity']}")
    print(f"Effective: {alert['effective']}")
    print("---")''',
            endpoint="/api/alerts",
            method="GET"
        ))
        
        # Get alerts with filters
        examples.append(CodeExample(
            language="python",
            title="Get Alerts by County",
            description="Filter alerts by county code",
            code='''# Get alerts for specific county
county_alerts = client._make_request("GET", "/api/alerts", params={"county": "TXC039"})
print(f"Found {len(county_alerts)} alerts for county TXC039")

# Get alerts by severity
severe_alerts = client._make_request("GET", "/api/alerts", params={"severity": "Severe"})
print(f"Found {len(severe_alerts)} severe alerts")''',
            endpoint="/api/alerts",
            method="GET"
        ))
        
        # Get alert history
        examples.append(CodeExample(
            language="python",
            title="Get Alert History",
            description="Retrieve historical weather alerts",
            code='''# Get alert history with pagination
history = client._make_request("GET", "/api/alerts/history", params={
    "limit": 50,
    "offset": 0
})

print(f"Total alerts: {history['total']}")
print(f"Retrieved: {len(history['alerts'])} alerts")

for alert in history['alerts']:
    print(f"{alert['sent']}: {alert['event']} - {alert['area_desc']}")''',
            endpoint="/api/alerts/history",
            method="GET"
        ))
        
        # Test email connection
        examples.append(CodeExample(
            language="python",
            title="Test Email Connection",
            description="Test email SMTP connection",
            code='''# Test email connection
email_config = {
    "provider": "gmail",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "your-email@gmail.com",
    "password": "your-app-password",
    "use_tls": True,
    "use_ssl": False
}

result = client._make_request("POST", "/api/notifications/test-email", json=email_config)
if result['success']:
    print("Email connection test successful!")
else:
    print(f"Email connection test failed: {result.get('error', 'Unknown error')}")''',
            endpoint="/api/notifications/test-email",
            method="POST"
        ))
        
        # Add subscriber
        examples.append(CodeExample(
            language="python",
            title="Add Notification Subscriber",
            description="Add a new notification subscriber",
            code='''# Add a new subscriber
subscriber_data = {
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

result = client._make_request("POST", "/api/notifications/subscribers", json=subscriber_data)
if result['success']:
    print(f"Subscriber added successfully! ID: {result['subscriber_id']}")
else:
    print(f"Failed to add subscriber: {result.get('error', 'Unknown error')}")''',
            endpoint="/api/notifications/subscribers",
            method="POST"
        ))
        
        # Get subscribers
        examples.append(CodeExample(
            language="python",
            title="Get All Subscribers",
            description="Retrieve all notification subscribers",
            code='''# Get all subscribers
subscribers = client._make_request("GET", "/api/notifications/subscribers")
print(f"Found {len(subscribers)} subscribers")

for subscriber in subscribers:
    print(f"Name: {subscriber['name']}")
    print(f"Email: {subscriber['email']}")
    print(f"Status: {subscriber['status']}")
    print(f"Methods: {', '.join(subscriber['preferences']['enabled_methods'])}")
    print("---")''',
            endpoint="/api/notifications/subscribers",
            method="GET"
        ))
        
        # Update configuration
        examples.append(CodeExample(
            language="python",
            title="Update Configuration",
            description="Update system configuration settings",
            code='''# Update configuration
config_update = {
    "poll_interval": 300,  # 5 minutes
    "nws": {
        "timeout": 30
    },
    "notifications": {
        "email": {
            "enabled": True,
            "provider": "gmail"
        }
    }
}

result = client._make_request("POST", "/api/config", json=config_update)
if result['success']:
    print("Configuration updated successfully!")
else:
    print(f"Configuration update failed: {result.get('error', 'Unknown error')}")''',
            endpoint="/api/config",
            method="POST"
        ))
        
        # Get health
        examples.append(CodeExample(
            language="python",
            title="Get System Health",
            description="Retrieve detailed system health information",
            code='''# Get system health
health = client._make_request("GET", "/api/health")
print(f"Overall status: {health['status']}")

for component, status in health['components'].items():
    print(f"{component}: {status['status']} - {status['message']}")
    if 'response_time_ms' in status:
        print(f"  Response time: {status['response_time_ms']}ms")''',
            endpoint="/api/health",
            method="GET"
        ))
        
        return examples
    
    def generate_javascript_examples(self) -> List[CodeExample]:
        """Generate JavaScript/Node.js code examples."""
        examples = []
        
        # Basic client setup
        examples.append(CodeExample(
            language="javascript",
            title="Basic Client Setup (Node.js)",
            description="Set up the SkywarnPlus-NG API client in Node.js",
            code='''const axios = require('axios');

class SkywarnPlusClient {
    constructor(baseUrl = 'http://localhost:8080') {
        this.baseUrl = baseUrl;
        this.client = axios.create({
            baseURL: baseUrl,
            headers: {
                'Content-Type': 'application/json',
                'User-Agent': 'SkywarnPlus-JS-Client/1.0'
            }
        });
    }
    
    async makeRequest(method, endpoint, data = null) {
        try {
            const response = await this.client.request({
                method,
                url: endpoint,
                data
            });
            return response.data;
        } catch (error) {
            throw new Error(`API request failed: ${error.message}`);
        }
    }
}

// Initialize client
const client = new SkywarnPlusClient();''',
            endpoint="/",
            method="GET"
        ))
        
        # Get status
        examples.append(CodeExample(
            language="javascript",
            title="Get System Status",
            description="Retrieve current system status",
            code='''// Get system status
async function getStatus() {
    try {
        const status = await client.makeRequest('GET', '/api/status');
        console.log(`System running: ${status.running}`);
        console.log(`Active alerts: ${status.active_alerts}`);
        console.log(`Uptime: ${status.uptime_seconds} seconds`);
    } catch (error) {
        console.error('Failed to get status:', error.message);
    }
}

getStatus();''',
            endpoint="/api/status",
            method="GET"
        ))
        
        # Get alerts
        examples.append(CodeExample(
            language="javascript",
            title="Get Active Alerts",
            description="Retrieve currently active weather alerts",
            code='''// Get all active alerts
async function getAlerts() {
    try {
        const alerts = await client.makeRequest('GET', '/api/alerts');
        console.log(`Found ${alerts.length} active alerts`);
        
        alerts.forEach(alert => {
            console.log(`Alert: ${alert.event} - ${alert.area_desc}`);
            console.log(`Severity: ${alert.severity}`);
            console.log(`Effective: ${alert.effective}`);
            console.log('---');
        });
    } catch (error) {
        console.error('Failed to get alerts:', error.message);
    }
}

getAlerts();''',
            endpoint="/api/alerts",
            method="GET"
        ))
        
        # Get alerts with filters
        examples.append(CodeExample(
            language="javascript",
            title="Get Alerts by County",
            description="Filter alerts by county code",
            code='''// Get alerts for specific county
async function getCountyAlerts() {
    try {
        const countyAlerts = await client.makeRequest('GET', '/api/alerts?county=TXC039');
        console.log(`Found ${countyAlerts.length} alerts for county TXC039`);
        
        // Get alerts by severity
        const severeAlerts = await client.makeRequest('GET', '/api/alerts?severity=Severe');
        console.log(`Found ${severeAlerts.length} severe alerts`);
    } catch (error) {
        console.error('Failed to get county alerts:', error.message);
    }
}

getCountyAlerts();''',
            endpoint="/api/alerts",
            method="GET"
        ))
        
        # Add subscriber
        examples.append(CodeExample(
            language="javascript",
            title="Add Notification Subscriber",
            description="Add a new notification subscriber",
            code='''// Add a new subscriber
async function addSubscriber() {
    const subscriberData = {
        name: "John Doe",
        email: "john.doe@example.com",
        status: "active",
        preferences: {
            counties: ["TXC039", "TXC201"],
            enabled_severities: ["Severe", "Extreme"],
            enabled_urgencies: ["Immediate", "Expected"],
            enabled_certainties: ["Likely", "Observed"],
            enabled_methods: ["email", "webhook"],
            max_notifications_per_hour: 10,
            max_notifications_per_day: 50
        },
        webhook_url: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
    };
    
    try {
        const result = await client.makeRequest('POST', '/api/notifications/subscribers', subscriberData);
        if (result.success) {
            console.log(`Subscriber added successfully! ID: ${result.subscriber_id}`);
        } else {
            console.log(`Failed to add subscriber: ${result.error || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Failed to add subscriber:', error.message);
    }
}

addSubscriber();''',
            endpoint="/api/notifications/subscribers",
            method="POST"
        ))
        
        # WebSocket connection
        examples.append(CodeExample(
            language="javascript",
            title="WebSocket Connection",
            description="Connect to real-time WebSocket updates",
            code='''// WebSocket connection for real-time updates
const WebSocket = require('ws');

function connectWebSocket() {
    const ws = new WebSocket('ws://localhost:8080/ws');
    
    ws.on('open', function open() {
        console.log('WebSocket connected');
    });
    
    ws.on('message', function message(data) {
        try {
            const update = JSON.parse(data);
            console.log('Received update:', update);
            
            if (update.type === 'alert') {
                console.log(`New alert: ${update.alert.event} - ${update.alert.area_desc}`);
            } else if (update.type === 'status') {
                console.log(`Status update: ${update.status.running ? 'Running' : 'Stopped'}`);
            }
        } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
        }
    });
    
    ws.on('close', function close() {
        console.log('WebSocket disconnected');
        // Reconnect after 5 seconds
        setTimeout(connectWebSocket, 5000);
    });
    
    ws.on('error', function error(err) {
        console.error('WebSocket error:', err);
    });
}

connectWebSocket();''',
            endpoint="/ws",
            method="GET"
        ))
        
        return examples
    
    def generate_curl_examples(self) -> List[CodeExample]:
        """Generate cURL examples."""
        examples = []
        
        # Status
        examples.append(CodeExample(
            language="bash",
            title="Get System Status",
            description="Retrieve current system status",
            code=f"curl -X GET '{self.base_url}/api/status'",
            endpoint="/api/status",
            method="GET"
        ))
        
        # Alerts
        examples.append(CodeExample(
            language="bash",
            title="Get Active Alerts",
            description="Retrieve currently active weather alerts",
            code=f"curl -X GET '{self.base_url}/api/alerts'",
            endpoint="/api/alerts",
            method="GET"
        ))
        
        # Alerts with filters
        examples.append(CodeExample(
            language="bash",
            title="Get Alerts by County",
            description="Filter alerts by county code",
            code=f"curl -X GET '{self.base_url}/api/alerts?county=TXC039'",
            endpoint="/api/alerts",
            method="GET"
        ))
        
        # Health
        examples.append(CodeExample(
            language="bash",
            title="Get System Health",
            description="Retrieve detailed system health information",
            code=f"curl -X GET '{self.base_url}/api/health'",
            endpoint="/api/health",
            method="GET"
        ))
        
        # Test email
        examples.append(CodeExample(
            language="bash",
            title="Test Email Connection",
            description="Test email SMTP connection",
            code=f'''curl -X POST '{self.base_url}/api/notifications/test-email' \\
  -H 'Content-Type: application/json' \\
  -d '{{"provider": "gmail", "smtp_server": "smtp.gmail.com", "smtp_port": 587, "username": "your-email@gmail.com", "password": "your-app-password"}}' ''',
            endpoint="/api/notifications/test-email",
            method="POST"
        ))
        
        # Add subscriber
        examples.append(CodeExample(
            language="bash",
            title="Add Subscriber",
            description="Add a new notification subscriber",
            code=f'''curl -X POST '{self.base_url}/api/notifications/subscribers' \\
  -H 'Content-Type: application/json' \\
  -d '{{"name": "John Doe", "email": "john@example.com", "preferences": {{"counties": ["TXC039"], "enabled_methods": ["email"]}}}}' ''',
            endpoint="/api/notifications/subscribers",
            method="POST"
        ))
        
        # Update config
        examples.append(CodeExample(
            language="bash",
            title="Update Configuration",
            description="Update system configuration",
            code=f'''curl -X POST '{self.base_url}/api/config' \\
  -H 'Content-Type: application/json' \\
  -d '{{"poll_interval": 300}}' ''',
            endpoint="/api/config",
            method="POST"
        ))
        
        return examples
    
    def generate_all_examples(self) -> Dict[str, List[CodeExample]]:
        """Generate all code examples."""
        return {
            "python": self.generate_python_examples(),
            "javascript": self.generate_javascript_examples(),
            "curl": self.generate_curl_examples()
        }
