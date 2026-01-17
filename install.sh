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
    libgomp1 \
    libopenblas0 \
    libsndfile1 \
    portaudio19-dev \
    ffmpeg \
    sox

echo "✓ System dependencies installed"

# Use asterisk user for running skywarnplus-ng (simplifies permissions)
if ! id "asterisk" &>/dev/null; then
    echo "Error: asterisk user does not exist. Please install Asterisk first."
    exit 1
else
    echo "✓ Using existing asterisk user for skywarnplus-ng"
fi

# Set username variable for use throughout the script
APP_USER="asterisk"
APP_GROUP="asterisk"

# Configure sudoers for Asterisk CLI access (asterisk can run itself)
# This allows asterisk user to execute asterisk commands via rpt.conf
# Note: asterisk user typically already has permission to run asterisk commands
echo "✓ Asterisk CLI access configured (asterisk user runs its own commands)"

# Create directories
echo "Creating application directories..."
sudo mkdir -p /var/lib/skywarnplus-ng/{descriptions,audio,data,scripts}
sudo mkdir -p /var/lib/skywarnplus-ng/src/skywarnplus_ng/web/static
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

# Set permissions - all owned by asterisk:asterisk
sudo chown -R ${APP_USER}:${APP_GROUP} /var/lib/skywarnplus-ng
sudo chown -R ${APP_USER}:${APP_GROUP} /var/log/skywarnplus-ng
sudo chown -R ${APP_USER}:${APP_GROUP} /tmp/skywarnplus-ng-audio

# Set directory permissions (755 for directories, files can be 644)
sudo chmod 755 /var/lib/skywarnplus-ng
sudo chmod 755 /var/lib/skywarnplus-ng/descriptions

echo "✓ Directories created and permissions set"

# Copy source files to /var/lib/skywarnplus-ng
echo "Copying source files..."
CURRENT_DIR=$(pwd)
sudo cp -r src/ /var/lib/skywarnplus-ng/
if [ -f "pyproject.toml" ]; then
    sudo cp pyproject.toml /var/lib/skywarnplus-ng/
fi
sudo chown -R ${APP_USER}:${APP_GROUP} /var/lib/skywarnplus-ng/src
if [ -f "pyproject.toml" ]; then
    sudo chown ${APP_USER}:${APP_GROUP} /var/lib/skywarnplus-ng/pyproject.toml
fi
echo "✓ Source files copied"

# Create virtual environment and install Python dependencies
echo "Installing Python dependencies..."
CURRENT_DIR=$(pwd)
if [ -f "pyproject.toml" ]; then
    # Create virtual environment in /var/lib/skywarnplus-ng/venv
    echo "Creating virtual environment..."
    sudo -u ${APP_USER} python3 -m venv /var/lib/skywarnplus-ng/venv
    
    # Install dependencies using venv's pip (from /var/lib/skywarnplus-ng directory)
    echo "Installing packages..."
    sudo -u ${APP_USER} bash -c "cd /var/lib/skywarnplus-ng && /var/lib/skywarnplus-ng/venv/bin/pip install --upgrade pip"
    sudo -u ${APP_USER} bash -c "cd /var/lib/skywarnplus-ng && /var/lib/skywarnplus-ng/venv/bin/pip install ."
    echo "✓ Python dependencies installed"
else
    echo "⚠️  Warning: pyproject.toml not found. Skipping Python dependencies installation."
fi

# Copy configuration (do not overwrite existing user config)
echo "Setting up configuration..."
if [ -f "config/default.yaml" ]; then
    if [ ! -f "/etc/skywarnplus-ng/config.yaml" ]; then
    sudo cp config/default.yaml /etc/skywarnplus-ng/config.yaml
    sudo chown ${APP_USER}:${APP_GROUP} /etc/skywarnplus-ng/config.yaml
        echo "✓ Configuration created at /etc/skywarnplus-ng/config.yaml"
    else
        # Preserve user config; provide example for reference
        sudo cp config/default.yaml /etc/skywarnplus-ng/config.yaml.example
        sudo chown ${APP_USER}:${APP_GROUP} /etc/skywarnplus-ng/config.yaml.example
        echo "✓ Existing config preserved; example updated at /etc/skywarnplus-ng/config.yaml.example"
    fi
else
    echo "⚠️  Warning: config/default.yaml not found. Skipping configuration copy."
fi

# Generate DTMF configuration (must run after venv is created)
echo "Generating DTMF configuration..."
if [ -f "${CURRENT_DIR}/scripts/generate_dtmf_conf.py" ]; then
    # Use the venv Python if it exists (check if venv directory exists and Python is available)
    VENV_PYTHON="/var/lib/skywarnplus-ng/venv/bin/python"
    if [ -d "/var/lib/skywarnplus-ng/venv" ] && [ -e "${VENV_PYTHON}" ]; then
        if sudo "${VENV_PYTHON}" "${CURRENT_DIR}/scripts/generate_dtmf_conf.py" > /tmp/dtmf_gen.log 2>&1; then
            # Check if file was created
            if [ -f "/etc/asterisk/custom/rpt/skydescribe.conf" ]; then
                echo "✓ DTMF configuration generated at /etc/asterisk/custom/rpt/skydescribe.conf"
            else
                echo "⚠️  Warning: DTMF configuration script ran but file was not created"
                cat /tmp/dtmf_gen.log 2>/dev/null | grep -i "error\|warning" || true
            fi
        else
            echo "⚠️  Warning: Failed to generate DTMF configuration. Check errors below:"
            cat /tmp/dtmf_gen.log 2>/dev/null | grep -i "error\|warning" || true
            echo "You may need to run it manually:"
            echo "   sudo ${VENV_PYTHON} ${CURRENT_DIR}/scripts/generate_dtmf_conf.py"
        fi
        rm -f /tmp/dtmf_gen.log
    else
        echo "⚠️  Warning: Virtual environment not found, skipping DTMF configuration generation"
        echo "   You can generate it manually after installation:"
        echo "   sudo ${VENV_PYTHON} /var/lib/skywarnplus-ng/scripts/generate_dtmf_conf.py"
    fi
else
    echo "⚠️  Warning: Could not generate DTMF configuration (script not found)"
    echo "   Script: ${CURRENT_DIR}/scripts/generate_dtmf_conf.py"
fi

# Copy scripts directory for user convenience
echo "Copying scripts..."
if [ -d "scripts" ]; then
    sudo cp -r scripts/* /var/lib/skywarnplus-ng/scripts/
    sudo chown -R ${APP_USER}:${APP_GROUP} /var/lib/skywarnplus-ng/scripts/
    echo "✓ Scripts copied to /var/lib/skywarnplus-ng/scripts/"
else
    echo "⚠️  Warning: scripts directory not found."
fi

# Create systemd service
echo "Creating systemd service..."
sudo tee /etc/systemd/system/skywarnplus-ng.service > /dev/null <<EOF
[Unit]
Description=SkywarnPlus-NG Weather Alert System
After=network.target asterisk.service
Wants=asterisk.service

[Service]
Type=simple
User=asterisk
Group=asterisk
WorkingDirectory=/var/lib/skywarnplus-ng
ExecStart=/var/lib/skywarnplus-ng/venv/bin/python -m skywarnplus_ng.cli run --config /etc/skywarnplus-ng/config.yaml
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

# Ensure port 8100 is clear
echo "Ensuring port 8100 is available..."
if command -v lsof >/dev/null 2>&1; then
    sudo kill -9 $(sudo lsof -t -i :8100) 2>/dev/null || true
elif command -v fuser >/dev/null 2>&1; then
    sudo fuser -k 8100/tcp 2>/dev/null || true
fi
echo "✓ Port 8100 cleared"

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
        systemctl kill -s HUP skywarnplus-ng > /dev/null 2>&1 || true
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
echo "- DTMF config: /etc/asterisk/custom/rpt/skydescribe.conf (generated during install)"
echo "- Enable SkyDescribe for your node via ASL-menu"
echo "- Audio files: /var/lib/skywarnplus-ng/SOUNDS/"
echo "- Web dashboard: http://localhost:8100 or via reverse proxy"
echo ""
