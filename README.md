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
./scripts/restart.sh
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
│   └── notifications/           # Notification system
├── config/                      # Configuration files
├── SOUNDS/                      # Audio files for alerts
├── scripts/                     # Development and utility scripts
│   ├── generate_asterisk_config.py # Asterisk config generator
│   ├── test_asterisk_integration.py # Integration testing
│   ├── create_release.py        # Release tarball creator
│   ├── restart.sh               # Server restart script
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

### `restart.sh`
Safely restart the SkywarnPlus-NG server:
```bash
./scripts/restart.sh
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
alerts = await client.get_alerts_for_county("TXC039")

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