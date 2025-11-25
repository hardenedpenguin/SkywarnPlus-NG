# SkywarnPlus-NG

Modern weather alert system for Asterisk/app_rpt nodes with DTMF integration.

## Quick Start

```bash
# Download the signed release tarball
wget https://github.com/hardenedpenguin/SkywarnPlus-NG/releases/download/v1.0.1/skywarnplus-ng-1.0.1.tar.gz

# Extract and run the installer (will prompt for sudo where required)
tar -xzf skywarnplus-ng-1.0.1.tar.gz
cd skywarnplus-ng-1.0.1
./install.sh

# Edit your configuration
sudo nano /etc/skywarnplus-ng/config.yaml

# Enable and start the service
sudo systemctl enable skywarnplus-ng
sudo systemctl start skywarnplus-ng

# Web dashboard (default creds admin/skywarn123) – adjust base_path if using a reverse proxy
http://localhost:8100
```

> **Heads up:** The installer targets Debian 13 (trixie) and Python 3.13. On other distros ensure the prerequisites listed below are installed before running the script.

## Requirements

- 64-bit Linux host (Debian 13 recommended)
- Python 3.13 with `python3-venv`, `python3-dev`
- GCC toolchain (`build-essential` or `gcc g++`)
- System dependencies: `ffmpeg`, `sox`, `libsndfile1`, `libopenblas0`, `libgomp1`, `libffi-dev`, `libssl-dev`, `libasound2-dev`, `portaudio19-dev`
- Optional: Asterisk/app_rpt node for on-air playback
- Outbound Internet access (NWS API, optional gTTS/Pushover)

All of the above are installed automatically when you run `install.sh` on a clean Debian 13 system. For other distributions install the equivalents using your package manager before running the installer.

## Installation Steps

1. **Download & Verify**
```bash
   wget https://github.com/hardenedpenguin/SkywarnPlus-NG/releases/download/v1.0.1/skywarnplus-ng-1.0.1.tar.gz
   sha256sum skywarnplus-ng-1.0.1.tar.gz
   ```
   Compare the checksum against the value published on the release page.

2. **Extract & Install**
```bash
   tar -xzf skywarnplus-ng-1.0.1.tar.gz
   cd skywarnplus-ng-1.0.1
   ./install.sh
   ```
   The installer creates the service account, virtualenv, systemd unit, logrotate config, and copies sounds/scripts.

3. **Configure**
```bash
   sudo nano /etc/skywarnplus-ng/config.yaml
   ```
   - Add your county codes under `counties`.
   - Set Asterisk node numbers (optional).
   - Configure alerts, TTS engine (gTTS or Piper), and notifications.
   
   > Prefer a UI? Sign in to the web dashboard and use the **Configuration** tab to edit every setting (including counties, audio, notifications, and scripts) without touching the YAML file. All changes saved there are written back to `/etc/skywarnplus-ng/config.yaml`.

4. **Start & Verify**
   ```bash
   sudo systemctl start skywarnplus-ng
   sudo systemctl status skywarnplus-ng
   sudo journalctl -u skywarnplus-ng -f
   ```
   Visit the dashboard at `http://<hostname>:8100` (or behind your reverse proxy). Default login: `admin / skywarn123`.

5. **Reverse Proxy (optional)**
   When fronting with Apache/Nginx under `/skywarnplus-ng`, set `monitoring.http_server.base_path: "/skywarnplus-ng"` in `config.yaml`, ensure static assets are proxied, and forward WebSocket upgrades to `/ws`.

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
