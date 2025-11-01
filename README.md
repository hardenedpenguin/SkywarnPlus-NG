# SkywarnPlus-NG

Modern weather alert system for Asterisk/app_rpt nodes with DTMF integration.

## Quick Start

```bash
# Extract and install
tar -xzf skywarnplus-ng-*.tar.gz
cd skywarnplus-ng-*
./install.sh

# Configure
sudo nano /etc/skywarnplus-ng/config.yaml

# Start service
sudo systemctl enable skywarnplus-ng
sudo systemctl start skywarnplus-ng

# Web dashboard: http://localhost:8100
```

## Requirements

- Python 3.11+
- Asterisk/app_rpt (optional, for voice announcements)
- Network access (for NWS API)

## Configuration

Edit `/etc/skywarnplus-ng/config.yaml`:

```yaml
# Configure counties to monitor
counties:
  - code: "TXC039"
    name: "Brazoria County"
    enabled: true

# Asterisk nodes for announcements
asterisk:
  enabled: true
  nodes: [546050]

# Web dashboard
monitoring:
  http_server:
    port: 8100
    auth:
      username: "admin"
      password: "your_password"
```

## Features

- **Weather Alerts**: Real-time NWS alert monitoring and voice announcements
- **SkyDescribe DTMF**: On-demand weather info via DTMF codes (*1, *2, *3, etc.)
- **Web Dashboard**: Modern web interface for monitoring and configuration
- **Tail Messages**: Continuous alert announcements via tail message system
- **Courtesy Tones**: Automatic tone switching based on alert status
- **ID Changes**: Dynamic node ID switching for weather alerts
- **AlertScript**: Execute commands (BASH/DTMF) on alert detection
- **County Audio**: Play county-specific audio files in announcements
- **PushOver**: Mobile push notifications for alerts

## DTMF Commands

- `*1` - Current active alerts
- `*2xxxx` - Specific alert by ID
- `*3` - All-clear status
- `*4` - System status
- `*9` - Help

## Service Management

```bash
sudo systemctl restart skywarnplus-ng
sudo systemctl status skywarnplus-ng
journalctl -u skywarnplus-ng -f
```

## License

MIT License - see LICENSE file for details.
