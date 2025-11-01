# SkywarnPlus-NG

Modern, modular weather alert system for Asterisk/app_rpt nodes with advanced DTMF integration.

## 🌟 Overview

SkywarnPlus-NG is a complete rewrite of the original SkywarnPlus application, designed from the ground up to be modular, maintainable, and extensible. It integrates with the National Weather Service API to provide real-time weather alert announcements on Ham Radio repeaters.

## ✨ Key Features

### 🌦️ **Weather Alert System**
- Real-time weather alert monitoring via NWS API
- Automatic voice announcements via Asterisk/app_rpt
- Configurable alert triggers and filtering
- Advanced alert processing pipeline with deduplication and prioritization
- Multi-county support with individual enable/disable controls

### 🎙️ **SkyDescribe DTMF System**
- **On-demand weather descriptions** via configurable DTMF codes
- **Detailed alert information** - Full weather descriptions with area details
- **System status checks** - All-clear status and system health
- **Interactive help system** - Available commands and usage instructions
- **Asterisk integration** - Works with both app_rpt and standard Asterisk

### 🖥️ **Web Dashboard**
- Modern, responsive web interface on port 8100
- Real-time alert monitoring and system status
- Configuration management with authentication
- Performance metrics and analytics
- Light/dark theme support
- Mobile-friendly design

### 🔧 **Technical Excellence**
- Modern Python 3.11+ with full type hints
- Async/await architecture for performance
- Comprehensive error handling and logging
- Modular, extensible design
- Production-ready with systemd integration

## 🚀 Quick Start

### Installation
```bash
# Extract and install
tar -xzf skywarnplus-ng-3.0.0.tar.gz
cd skywarnplus-ng-3.0.0
./install.sh

# Web dashboard available at: http://localhost:8100
```

### Configuration
```bash
# Edit configuration
nano config/default.yaml

# Configure your counties and Asterisk nodes
# Restart to apply changes
sudo systemctl restart skywarnplus-ng
```

## 📋 System Requirements

### Prerequisites
- **Python 3.11+** - Modern Python with async support
- **Network access** - For NWS API connectivity
- **Asterisk/app_rpt** - For voice announcements (optional)

### System Dependencies
The installation script handles these automatically:
- **Python tools**: `python3-pip`, `python3-venv`, `python3-dev`, `gcc`, `g++`
- **Audio processing**: `libasound2-dev`, `portaudio19-dev`, `ffmpeg`
- **Security**: `libffi-dev`, `libssl-dev`
- **TTS Engine**: gTTS (Google Text-to-Speech) - requires internet

## 🎯 SkyDescribe DTMF Commands

SkyDescribe allows Ham Radio operators to access detailed weather information via DTMF codes:

### Default DTMF Codes
- **`*1`** - Current active weather alerts with full descriptions
- **`*2`** - Specific alert by ID (e.g., `*21234` for alert ID 1234)
- **`*3`** - All-clear status and system information
- **`*4`** - System status and health check
- **`*9`** - Help and available commands

### How It Works
1. **User dials DTMF code** on repeater (e.g., `*1`)
2. **Asterisk processes code** via rpt.conf or extensions.conf
3. **SkywarnPlus-NG generates audio** using TTS engine
4. **Audio plays via rpt localplay** with detailed weather information

## 🔧 Asterisk Integration

### For app_rpt (Repeater Nodes)
```bash
# Generate rpt.conf functions
python3 scripts/generate_asterisk_config.py --type rpt --output /etc/asterisk/custom/skywarnplus_functions.conf

# Add to your rpt.conf:
#include /etc/asterisk/custom/skywarnplus_functions.conf
```

### For Standard Asterisk (PBX/Phone Systems)
```bash
# Generate extensions.conf dialplan
python3 scripts/generate_asterisk_config.py --type extensions --output /etc/asterisk/custom/skywarnplus_extensions.conf

# Add to your extensions.conf:
#include custom/skywarnplus_extensions.conf

# Include in your main context:
include => skywarnplus-ng
```

## 🖥️ Web Dashboard

Access the modern web dashboard at `http://your-server:8100`

### Features
- **Dashboard** - Real-time system overview and active alerts
- **Active Alerts** - Current weather alerts with full details
- **Alert History** - Historical alert data and processing logs
- **Configuration** - System settings (requires authentication)
- **Health** - System health monitoring and component status
- **Logs** - Application logs and debugging information
- **Database** - Database statistics and maintenance
- **Metrics** - Performance analytics and system metrics

### Authentication
- **Public Access** - Dashboard, alerts, health, logs, metrics
- **Protected** - Configuration page only (default: admin/skywarn123)
- **Session-based** - Secure cookie authentication
- **Configurable** - Username, password, and timeout settings

## 📁 Directory Structure

```
SkywarnPlus-NG/
├── src/skywarnplus_ng/          # Application source code
│   ├── api/                     # NWS API client
│   ├── core/                    # Core application logic
│   ├── web/                     # Web dashboard
│   ├── skydescribe/             # DTMF system
│   ├── audio/                   # Audio and TTS management
│   ├── asterisk/                # Asterisk integration
│   ├── processing/              # Alert processing pipeline
│   ├── database/                # Database management
│   ├── monitoring/              # Health monitoring
│   └── notifications/           # Notification system (Email, Webhook, PushOver)
├── config/                      # Configuration files
├── SOUNDS/                      # Audio files for alerts
├── scripts/                     # Development and utility scripts
│   ├── generate_asterisk_config.py # Asterisk config generator
│   ├── test_asterisk_integration.py # Integration testing
│   ├── create_release.py        # Release tarball creator
│   └── README.md                # Scripts documentation
├── install.sh                   # Installation script
└── README.md                    # This file
```

## ⚙️ Configuration

### Main Configuration (`config/default.yaml`)
```yaml
# Counties to monitor
counties:
  - code: "TXC039"              # Brazoria County, TX
    name: "Brazoria County"
    enabled: true

# Asterisk integration
asterisk:
  enabled: true
  nodes: [546050]               # Your node numbers
  audio_delay: 0

# Audio settings
audio:
  sounds_path: "SOUNDS"
  alert_sound: "Duncecap.wav"
  all_clear_sound: "Triangles.wav"
  separator_sound: "Woodblock.wav"

# Web dashboard
monitoring:
  enabled: true
  http_server:
    enabled: true
    host: "0.0.0.0"
    port: 8100
    auth:
      enabled: true
      username: "admin"
      password: "skywarn123"      # Change this!

# PushOver notifications (optional)
pushover:
  enabled: false                  # Set to true to enable
  api_token: null                 # Your PushOver API token
  user_key: null                  # Your PushOver user key
  priority: 0                     # -2 to 2 (0=normal)
  sound: null                     # Sound name or null for device default
```

### DTMF Codes (`skydescribe.dtmf_codes`)
```yaml
skydescribe:
  dtmf_codes:
    current_alerts: "1"         # *1 for current alerts
    alert_by_id: "2"           # *2xxxx for specific alert
    all_clear: "3"             # *3 for all-clear
    system_status: "4"         # *4 for system status
    help: "9"                  # *9 for help
```

## 🛠️ Development Scripts

The `scripts/` directory contains useful development and utility tools:

### `generate_asterisk_config.py`
Generate Asterisk configuration files for DTMF integration:
```bash
# For app_rpt
python3 scripts/generate_asterisk_config.py --type rpt --show

# For standard Asterisk
python3 scripts/generate_asterisk_config.py --type extensions --show
```

### `test_asterisk_integration.py`
Test Asterisk integration and system functionality:
```bash
python3 scripts/test_asterisk_integration.py
```

### `create_release.py`
Create production-ready release tarballs:
```bash
python3 scripts/create_release.py
```

### Service Management
Restart the SkywarnPlus-NG service:
```bash
sudo systemctl restart skywarnplus-ng
```

Check service status:
```bash
sudo systemctl status skywarnplus-ng
```

## 🔍 NWS API Integration

### Features
- **Complete NWS API support** - Fetch alerts for zones, counties, or nationwide
- **Robust error handling** - Automatic retry with exponential backoff
- **Connection testing** - Verify API connectivity
- **Duplicate filtering** - Prevent duplicate alert processing
- **Rate limiting** - Respect NWS API limits

### Usage Examples
```python
from skywarnplus_ng.api.nws_client import NWSClient

# Create client
client = NWSClient(config.nws)

# Test connection
await client.test_connection()

# Get alerts for county
alerts = await client.fetch_alerts_for_zone("TXC039")

# Get all active alerts (use with caution)
all_alerts = await client.get_active_alerts()
```

## 🏥 System Health & Monitoring

### Health Monitoring
- **Component health checks** - NWS API, audio system, Asterisk, database
- **Performance metrics** - Response times, throughput, error rates
- **System resources** - CPU, memory, disk usage
- **Alert processing stats** - Success rates, processing times

### Logging
- **Structured logging** - JSON format with full context
- **Multiple levels** - DEBUG, INFO, WARNING, ERROR, CRITICAL
- **File and console output** - Configurable destinations
- **Log rotation** - Automatic cleanup and archival

## 📱 PushOver Notifications

SkywarnPlus-NG includes support for PushOver push notifications to keep you informed about weather alerts on your mobile device.

### Setup

1. **Create a PushOver account** (if you don't have one):
   - Visit https://pushover.net/ and sign up
   - Install the PushOver app on your phone/tablet
   
2. **Create an application**:
   - Go to https://pushover.net/apps/build
   - Create a new application (e.g., "SkywarnPlus-NG")
   - Copy the **API Token**

3. **Get your user key**:
   - Visit https://pushover.net/ while logged in
   - Your user key is displayed on the dashboard

4. **Configure SkywarnPlus-NG**:
   ```yaml
   pushover:
     enabled: true
     api_token: "your_api_token_here"
     user_key: "your_user_key_here"
     priority: 0  # Normal priority (0), can be -2 to 2
     sound: null  # Use device default sound
   ```

5. **Test your setup**:
   ```bash
   python3 scripts/test_pushover.py <API_TOKEN> <USER_KEY>
   ```

### Features

- **Smart priority selection** - Priority automatically adjusted based on alert severity
  - **Extreme + Immediate** → Emergency priority (requires acknowledgment, retries every 5 minutes)
  - **Severe + Immediate** → High priority (bypasses quiet hours)
  - **Moderate** → Normal priority
  - **Minor** → Normal priority with gentle sound

- **Rich formatting** - Include alert details, area description, and clickable links to full alert

- **Multiple sounds** - Choose from 24 different notification sounds or use device default

- **Automatic retries** - Failed notifications retry up to 3 times with exponential backoff

- **All-clear notifications** - Get notified when weather alerts expire and conditions clear

### Priority Levels

PushOver supports 5 priority levels:

- **Emergency (2)** - Require acknowledgment, repeat every 5 minutes until acknowledged
- **High (1)** - Bypass quiet hours, use default sound
- **Normal (0)** - Default priority, respects quiet hours
- **Low (-1)** - Silent notification, no sound or vibration
- **Lowest (-2)** - No notification at all

### Testing

Use the included test script to verify your PushOver setup:

```bash
python3 scripts/test_pushover.py <API_TOKEN> <USER_KEY>
```

This will send:
1. A simple test notification
2. A mock weather alert notification (Tornado Warning)

## 🚀 Production Deployment

### Systemd Service
```bash
# Create service file
sudo nano /etc/systemd/system/skywarnplus-ng.service

# Enable and start
sudo systemctl enable skywarnplus-ng
sudo systemctl start skywarnplus-ng

# Check status
sudo systemctl status skywarnplus-ng
```

### Directory Setup
```bash
# Create required directories
sudo mkdir -p /var/lib/skywarnplus-ng/{descriptions,audio,data}
sudo mkdir -p /var/log/skywarnplus-ng
sudo mkdir -p /etc/skywarnplus-ng

# Set permissions
sudo chown -R skywarnplus:skywarnplus /var/lib/skywarnplus-ng
```

### Firewall Configuration
```bash
# Open web dashboard port
sudo ufw allow 8100/tcp
```

## 🔧 Troubleshooting

### Common Issues
- **Port conflicts** - Ensure port 8100 is available
- **Asterisk permissions** - Add user to asterisk group
- **Sound file access** - Verify SOUNDS directory permissions
- **NWS API connectivity** - Check internet connection and firewall

### Debugging
```bash
# Check logs
journalctl -u skywarnplus-ng -f

# Test NWS connection
python3 -m skywarnplus_ng.cli test-nws

# Test DTMF commands
python3 -m skywarnplus_ng.cli dtmf current_alerts
```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📞 Support

For support and questions:
- Check the troubleshooting section above
- Review the configuration examples
- Test with the provided scripts
- Check system logs for error messages

---

**SkywarnPlus-NG** - Modern weather alerting for the Ham Radio community 🌦️📻