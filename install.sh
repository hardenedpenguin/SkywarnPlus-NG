#!/bin/bash
# SkywarnPlus-NG Traditional Installation Script
# Direct installation on host system for optimal Asterisk integration

set -e

echo "Installing SkywarnPlus-NG (Traditional Method)"
echo "=============================================="

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "Please do not run this script as root. It will use sudo when needed."
    exit 1
fi

# Check Python version
python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python $required_version or higher is required. Found: $python_version"
    exit 1
fi

echo "✓ Python version check passed: $python_version"

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    libasound2-dev \
    portaudio19-dev \
    ffmpeg

echo "✓ System dependencies installed"

# Create application user
if ! id "skywarnplus" &>/dev/null; then
    echo "Creating skywarnplus user..."
    sudo useradd -r -s /bin/false -m -d /var/lib/skywarnplus-ng skywarnplus
    echo "✓ User skywarnplus created"
else
    echo "✓ User skywarnplus already exists"
fi

# Create directories
echo "Creating application directories..."
sudo mkdir -p /var/lib/skywarnplus-ng/{descriptions,audio,data}
sudo mkdir -p /var/log/skywarnplus-ng
sudo mkdir -p /etc/skywarnplus-ng
sudo mkdir -p /tmp/skywarnplus-ng-audio

# Copy sound files
echo "Installing sound files..."
if [ -d "SOUNDS" ]; then
    sudo cp -r SOUNDS /var/lib/skywarnplus-ng/
    echo "Sound files installed to /var/lib/skywarnplus-ng/SOUNDS/"
else
    echo "Warning: SOUNDS directory not found. Sound files not installed."
fi

# Set permissions
sudo chown -R skywarnplus:skywarnplus /var/lib/skywarnplus-ng
sudo chown -R skywarnplus:skywarnplus /var/log/skywarnplus-ng
sudo chown -R skywarnplus:skywarnplus /tmp/skywarnplus-ng-audio

echo "✓ Directories created and permissions set"

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install --user -e ".[dev]"

echo "✓ Python dependencies installed"

# Copy configuration
echo "Setting up configuration..."
sudo cp config/default.yaml /etc/skywarnplus-ng/config.yaml
sudo chown skywarnplus:skywarnplus /etc/skywarnplus-ng/config.yaml

echo "✓ Configuration copied"

# Generate rpt.conf for Asterisk
echo "Generating rpt.conf for Asterisk integration..."
python3 examples/generate_rpt_conf.py --config /etc/skywarnplus-ng/config.yaml --output /tmp/rpt_skydescribe.conf
sudo cp /tmp/rpt_skydescribe.conf /etc/asterisk/rpt_skydescribe.conf
sudo chown asterisk:asterisk /etc/asterisk/rpt_skydescribe.conf

echo "✓ rpt.conf generated and installed"

# Create systemd service
echo "Creating systemd service..."
sudo tee /etc/systemd/system/skywarnplus-ng.service > /dev/null <<EOF
[Unit]
Description=SkywarnPlus-NG Weather Alert System
After=network.target asterisk.service
Wants=asterisk.service

[Service]
Type=simple
User=skywarnplus
Group=skywarnplus
WorkingDirectory=/var/lib/skywarnplus-ng
ExecStart=/usr/local/bin/skywarnplus-ng run --config /etc/skywarnplus-ng/config.yaml
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment
Environment=SKYWARNPLUS_NG_DATA=/var/lib/skywarnplus-ng/data
Environment=SKYWARNPLUS_NG_LOGS=/var/log/skywarnplus-ng

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable skywarnplus-ng

echo "✓ Systemd service created and enabled"

# Create logrotate configuration
echo "Setting up log rotation..."
sudo tee /etc/logrotate.d/skywarnplus-ng > /dev/null <<EOF
/var/log/skywarnplus-ng/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 skywarnplus skywarnplus
    postrotate
        systemctl reload skywarnplus-ng > /dev/null 2>&1 || true
    endscript
}
EOF

echo "✓ Log rotation configured"

echo ""
echo "Installation complete!"
echo "====================="
echo ""
echo "Next steps:"
echo "1. Edit configuration: sudo nano /etc/skywarnplus-ng/config.yaml"
echo "2. Update county codes and Asterisk node numbers"
echo "3. Start the service: sudo systemctl start skywarnplus-ng"
echo "4. Check status: sudo systemctl status skywarnplus-ng"
echo "5. View logs: sudo journalctl -u skywarnplus-ng -f"
echo "6. Web dashboard: http://localhost:8100"
echo ""
echo "Asterisk integration:"
echo "- rpt.conf configuration: /etc/asterisk/rpt_skydescribe.conf"
echo "- Audio files: /var/lib/skywarnplus-ng/descriptions/"
echo "- Test DTMF: skywarnplus-ng dtmf current_alerts"
echo ""
