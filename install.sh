#!/bin/bash
# SkywarnPlus-NG Traditional Installation Script
# Direct installation on host system for optimal Asterisk integration

set -e

# ============================================================================
# Configuration Constants
# ============================================================================

APP_USER="asterisk"
APP_GROUP="asterisk"
REQUIRED_PYTHON_VERSION="3.11"
WEB_PORT=8100
# Pip/Python use TMPDIR for wheel downloads and builds; /tmp is often a small tmpfs on ARM/ASL nodes.
SKYWARN_TMPDIR="${SKYWARN_TMPDIR:-/var/tmp}"

# Installation paths
INSTALL_ROOT="/var/lib/skywarnplus-ng"
LOG_DIR="/var/log/skywarnplus-ng"
CONFIG_DIR="/etc/skywarnplus-ng"
TMP_AUDIO_DIR="/tmp/skywarnplus-ng-audio"
VENV_PATH="${INSTALL_ROOT}/venv"
VENV_PYTHON="${VENV_PATH}/bin/python"
# When using sudo -u asterisk, use app-owned paths (not the installer's $HOME/.cache/pip).
APP_HOME="${INSTALL_ROOT}"
APP_CACHE="${INSTALL_ROOT}/.cache"
PIP_CACHE_DIR="${APP_CACHE}/pip"
PIPER_MODEL_DIR="${INSTALL_ROOT}/piper"
# Piper voice: "low" (smaller, faster) or "medium" (better quality). Set PIPER_QUALITY=medium to use medium.
PIPER_QUALITY="${PIPER_QUALITY:-low}"
PIPER_MODEL="en_US-amy-${PIPER_QUALITY}"
PIPER_BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/${PIPER_QUALITY}"

# System paths
SYSTEMD_SERVICE="/etc/systemd/system/skywarnplus-ng.service"
LOGROTATE_CONFIG="/etc/logrotate.d/skywarnplus-ng"
DTMF_CONFIG="/etc/asterisk/custom/rpt/skydescribe.conf"
APACHE_PROXY_SRC="config/apache/skywarnplus-ng-proxy.conf"
APACHE_PROXY_NAME="skywarnplus-ng-proxy"
APACHE_PROXY_AVAILABLE="/etc/apache2/conf-available/${APACHE_PROXY_NAME}.conf"

# Current directory (set once at start)
CURRENT_DIR=$(pwd)

# ============================================================================
# Helper Functions
# ============================================================================

# Set ownership recursively for a path
set_ownership() {
    local path="$1"
    sudo chown -R "${APP_USER}:${APP_GROUP}" "${path}"
}

# Copy file and set ownership
copy_file_with_ownership() {
    local src="$1"
    local dst="$2"
    sudo cp "${src}" "${dst}"
    set_ownership "${dst}"
}

# Copy directory recursively and set ownership
copy_dir_with_ownership() {
    local src="$1"
    local dst="$2"
    sudo cp -r "${src}" "${dst}"
    set_ownership "${dst}"
}

# Run command as app user (HOME/cache under INSTALL_ROOT so pip does not use installer's ~/.cache).
run_as_app_user() {
    sudo -u "${APP_USER}" env \
        HOME="${APP_HOME}" \
        XDG_CACHE_HOME="${APP_CACHE}" \
        PIP_CACHE_DIR="${PIP_CACHE_DIR}" \
        bash -c "$1"
}

# Run as app user with TMPDIR on persistent storage (see SKYWARN_TMPDIR).
run_as_app_user_tmp() {
    run_as_app_user "export TMPDIR='${SKYWARN_TMPDIR}' && $1"
}

# Print section header
print_section() {
    echo ""
    echo "$1"
    echo "$(printf '=%.0s' {1..50})"
}

# Print success message
print_success() {
    echo "✓ $1"
}

# Print warning message
print_warning() {
    echo "⚠️  Warning: $1"
}

# ============================================================================
# Validation Functions
# ============================================================================

check_not_root() {
    if [ "$EUID" -eq 0 ]; then
        echo "Error: Please do not run this script as root. It will use sudo when needed."
        exit 1
    fi
}

check_python_version() {
    local python_version
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    
    if [ "$(printf '%s\n' "${REQUIRED_PYTHON_VERSION}" "${python_version}" | sort -V | head -n1)" != "${REQUIRED_PYTHON_VERSION}" ]; then
        echo "Error: Python ${REQUIRED_PYTHON_VERSION} or higher is required. Found: ${python_version}"
        exit 1
    fi
    
    print_success "Python version check passed: ${python_version}"
}

check_asterisk_user() {
    if ! id "${APP_USER}" &>/dev/null; then
        echo "Error: ${APP_USER} user does not exist. Please install Asterisk first."
        exit 1
    fi
    print_success "Using existing ${APP_USER} user for skywarnplus-ng"
}

# ============================================================================
# Installation Functions
# ============================================================================

install_system_dependencies() {
    print_section "Installing system dependencies"
    
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
        sox \
        curl
    
    print_success "System dependencies installed"
}

create_directories() {
    print_section "Creating application directories"
    
    # Main application directories
    sudo mkdir -p "${INSTALL_ROOT}"/{descriptions,audio,data,scripts,piper}
    sudo mkdir -p "${INSTALL_ROOT}/src/skywarnplus_ng/web/static"
    sudo mkdir -p "${PIP_CACHE_DIR}"
    sudo mkdir -p "${LOG_DIR}"
    sudo mkdir -p "${CONFIG_DIR}"
    sudo mkdir -p "${TMP_AUDIO_DIR}"
    
    # Set ownership
    set_ownership "${INSTALL_ROOT}"
    set_ownership "${LOG_DIR}"
    set_ownership "${TMP_AUDIO_DIR}"
    set_ownership "${CONFIG_DIR}"
    
    # Set directory permissions
    sudo chmod 755 "${INSTALL_ROOT}"
    sudo chmod 755 "${INSTALL_ROOT}/descriptions"
    
    print_success "Directories created and permissions set"
}

install_piper_model() {
    print_section "Installing Piper TTS voice model (en_US-amy-${PIPER_QUALITY})"
    
    if [ "${PIPER_QUALITY}" != "low" ] && [ "${PIPER_QUALITY}" != "medium" ]; then
        print_warning "PIPER_QUALITY must be 'low' or 'medium'; got '${PIPER_QUALITY}'. Using 'low'."
        PIPER_QUALITY="low"
        PIPER_MODEL="en_US-amy-low"
        PIPER_BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/low"
    fi
    
    local onnx="${PIPER_MODEL_DIR}/${PIPER_MODEL}.onnx"
    local json="${PIPER_MODEL_DIR}/${PIPER_MODEL}.onnx.json"
    
    if [ -f "${onnx}" ] && [ -f "${json}" ]; then
        print_success "Piper model already present: ${onnx}"
        return 0
    fi
    
    if ! command -v curl &>/dev/null; then
        print_warning "curl not found. Skipping Piper model download. Install manually to ${PIPER_MODEL_DIR}."
        return 1
    fi
    
    echo "Downloading ${PIPER_MODEL}.onnx and .onnx.json from Hugging Face..."
    if sudo curl -f -L -o "${onnx}" "${PIPER_BASE_URL}/${PIPER_MODEL}.onnx" && \
       sudo curl -f -L -o "${json}" "${PIPER_BASE_URL}/${PIPER_MODEL}.onnx.json"; then
        set_ownership "${PIPER_MODEL_DIR}"
        print_success "Piper model installed at ${PIPER_MODEL_DIR}"
        return 0
    else
        print_warning "Piper model download failed. Default config expects a model under ${PIPER_MODEL_DIR}. Retry install, copy a model manually, or set audio.tts.engine to gtts in ${CONFIG_DIR}/config.yaml."
        sudo rm -f "${onnx}" "${json}"
        return 1
    fi
}

install_sound_files() {
    print_section "Installing sound files"
    
    if [ -d "SOUNDS" ]; then
        copy_dir_with_ownership "SOUNDS" "${INSTALL_ROOT}/"
        echo "Sound files installed to ${INSTALL_ROOT}/SOUNDS/"
    else
        print_warning "SOUNDS directory not found. Sound files not installed."
    fi
}

copy_source_files() {
    print_section "Copying source files"
    
    copy_dir_with_ownership "src/" "${INSTALL_ROOT}/"
    
    if [ -f "pyproject.toml" ]; then
        copy_file_with_ownership "pyproject.toml" "${INSTALL_ROOT}/pyproject.toml"
    fi

    # Pre-built dashboard stylesheet (no Node.js needed at install time; must exist in src/)
    if [ ! -f "${INSTALL_ROOT}/src/skywarnplus_ng/web/static/tailwind.css" ]; then
        print_warning "Dashboard stylesheet missing: src/skywarnplus_ng/web/static/tailwind.css"
        echo "   The web UI will look broken until this file is present. If you build from git, run:"
        echo "   npm install && npm run build:css"
        echo "   then copy src/ again or recreate the release tarball."
    fi
    
    print_success "Source files copied"
}

install_python_dependencies() {
    print_section "Installing Python dependencies"
    
    if [ ! -f "pyproject.toml" ]; then
        print_warning "pyproject.toml not found. Skipping Python dependencies installation."
        return
    fi
    
    echo "Creating virtual environment (TMPDIR=${SKYWARN_TMPDIR})..."
    run_as_app_user_tmp "python3 -m venv ${VENV_PATH}"
    
    echo "Installing packages (upgrading deps to latest versions allowed by pyproject.toml)..."
    run_as_app_user_tmp "cd ${INSTALL_ROOT} && ${VENV_PYTHON} -m pip install --upgrade pip"
    # --upgrade + eager: otherwise pip leaves e.g. onnxruntime on an older satisfying release on reinstalls.
    run_as_app_user_tmp "cd ${INSTALL_ROOT} && ${VENV_PYTHON} -m pip install --upgrade --upgrade-strategy eager ."
    
    SKYWARN_PKG_DIR=$("${VENV_PYTHON}" -c "import os, skywarnplus_ng as s; print(os.path.dirname(s.__file__))")
    print_success "Python dependencies installed (package: ${SKYWARN_PKG_DIR})"
    echo "   The systemd service runs code from that venv path, not ${INSTALL_ROOT}/src alone."
}

setup_configuration() {
    print_section "Setting up configuration"
    
    if [ ! -f "config/default.yaml" ]; then
        print_warning "config/default.yaml not found. Skipping configuration copy."
        return
    fi
    
    if [ ! -f "${CONFIG_DIR}/config.yaml" ]; then
        copy_file_with_ownership "config/default.yaml" "${CONFIG_DIR}/config.yaml"
        print_success "Configuration created at ${CONFIG_DIR}/config.yaml"
    else
        # Preserve user config; provide example for reference
        copy_file_with_ownership "config/default.yaml" "${CONFIG_DIR}/config.yaml.example"
        print_success "Existing config preserved; example updated at ${CONFIG_DIR}/config.yaml.example"
    fi
    
    # Ensure /etc/skywarnplus-ng and all its contents are properly owned
    set_ownership "${CONFIG_DIR}"
}

generate_dtmf_configuration() {
    print_section "Generating DTMF configuration"
    
    local dtmf_script="${CURRENT_DIR}/scripts/generate_dtmf_conf.py"
    
    if [ ! -f "${dtmf_script}" ]; then
        print_warning "Could not generate DTMF configuration (script not found)"
        echo "   Script: ${dtmf_script}"
        return
    fi
    
    if [ ! -d "${VENV_PATH}" ] || [ ! -e "${VENV_PYTHON}" ]; then
        print_warning "Virtual environment not found, skipping DTMF configuration generation"
        echo "   You can generate it manually after installation:"
        echo "   sudo ${VENV_PYTHON} ${INSTALL_ROOT}/scripts/generate_dtmf_conf.py"
        return
    fi
    
    local log_file="${SKYWARN_TMPDIR}/skywarnplus-ng-dtmf-install.log"
    
    if sudo env TMPDIR="${SKYWARN_TMPDIR}" "${VENV_PYTHON}" "${dtmf_script}" > "${log_file}" 2>&1; then
        if [ -f "${DTMF_CONFIG}" ]; then
            print_success "DTMF configuration generated at ${DTMF_CONFIG}"
        else
            print_warning "DTMF configuration script ran but file was not created"
            grep -i "error\|warning" "${log_file}" 2>/dev/null || true
        fi
    else
        print_warning "Failed to generate DTMF configuration. Check errors below:"
        grep -i "error\|warning" "${log_file}" 2>/dev/null || true
        echo "You may need to run it manually:"
        echo "   sudo ${VENV_PYTHON} ${dtmf_script}"
    fi
    
    rm -f "${log_file}"
}

copy_scripts() {
    print_section "Copying scripts"
    
    if [ -d "scripts" ]; then
        sudo cp -r scripts/* "${INSTALL_ROOT}/scripts/"
        set_ownership "${INSTALL_ROOT}/scripts/"
        print_success "Scripts copied to ${INSTALL_ROOT}/scripts/"
    else
        print_warning "scripts directory not found."
    fi
}

create_systemd_service() {
    print_section "Creating systemd service"
    
    sudo tee "${SYSTEMD_SERVICE}" > /dev/null <<EOF
[Unit]
Description=SkywarnPlus-NG Weather Alert System
After=network.target asterisk.service
Wants=asterisk.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${INSTALL_ROOT}
ExecStart=${VENV_PYTHON} -m skywarnplus_ng.cli run --config ${CONFIG_DIR}/config.yaml
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment
Environment=SKYWARNPLUS_NG_DATA=${INSTALL_ROOT}/data
Environment=SKYWARNPLUS_NG_LOGS=${LOG_DIR}

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable skywarnplus-ng
    
    print_success "Systemd service created and enabled"
}

clear_port() {
    print_section "Ensuring port ${WEB_PORT} is available"

    # If our service is running (e.g. reinstall/upgrade), stop it cleanly.
    if command -v systemctl >/dev/null 2>&1; then
        if sudo systemctl is-active --quiet skywarnplus-ng; then
            echo "skywarnplus-ng is running; stopping service to free port ${WEB_PORT}..."
            sudo systemctl stop skywarnplus-ng
        fi
    fi

    # Check if something else is still listening on the web port.
    local in_use="false"
    if command -v ss >/dev/null 2>&1; then
        if sudo ss -ltnp "sport = :${WEB_PORT}" 2>/dev/null | grep -q ":${WEB_PORT}"; then
            in_use="true"
        fi
    elif command -v lsof >/dev/null 2>&1; then
        if sudo lsof -iTCP:"${WEB_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
            in_use="true"
        fi
    fi

    if [ "${in_use}" = "true" ]; then
        print_warning "Port ${WEB_PORT} is in use by another process; not attempting to kill it."
        echo "   Either stop the process using ${WEB_PORT}, or change monitoring.http_server.port in:"
        echo "     ${CONFIG_DIR}/config.yaml"
        echo "   Then rerun ./install.sh"
        exit 1
    fi

    print_success "Port ${WEB_PORT} is available"
}

install_apache_proxy() {
    print_section "Configuring Apache reverse proxy (if present)"

    if ! command -v apache2ctl >/dev/null 2>&1 && ! command -v apachectl >/dev/null 2>&1; then
        echo "Apache not detected; skipping reverse proxy setup."
        echo "   Dashboard: http://localhost:${WEB_PORT}/skywarnplus-ng/"
        return 0
    fi

    if [ ! -f "${CURRENT_DIR}/${APACHE_PROXY_SRC}" ]; then
        print_warning "Apache proxy template not found (${APACHE_PROXY_SRC}); skipping."
        return 0
    fi

    local apache_ctl="apache2ctl"
    if ! command -v apache2ctl >/dev/null 2>&1; then
        apache_ctl="apachectl"
    fi

    echo "Enabling Apache proxy modules..."
    sudo a2enmod proxy proxy_http proxy_wstunnel >/dev/null 2>&1 || true

    echo "Installing ${APACHE_PROXY_AVAILABLE}..."
    sudo cp "${CURRENT_DIR}/${APACHE_PROXY_SRC}" "${APACHE_PROXY_AVAILABLE}"

    if command -v a2enconf >/dev/null 2>&1; then
        sudo a2enconf "${APACHE_PROXY_NAME}" >/dev/null 2>&1 || true
    else
        print_warning "a2enconf not found; enable ${APACHE_PROXY_NAME}.conf manually."
        return 0
    fi

    if sudo "${apache_ctl}" configtest >/dev/null 2>&1; then
        if command -v systemctl >/dev/null 2>&1; then
            sudo systemctl reload apache2 2>/dev/null || sudo systemctl reload httpd 2>/dev/null || true
        else
            sudo "${apache_ctl}" graceful 2>/dev/null || true
        fi
        print_success "Apache proxy enabled at /skywarnplus-ng (WebSocket + HTTP)"
        echo "   Dashboard (via Apache): http://$(hostname -f 2>/dev/null || hostname)/skywarnplus-ng/"
    else
        print_warning "Apache configtest failed after installing proxy; not reloading Apache."
        echo "   Run: sudo ${apache_ctl} configtest"
    fi
}

create_logrotate_config() {
    print_section "Setting up log rotation"
    
    sudo tee "${LOGROTATE_CONFIG}" > /dev/null <<EOF
${LOG_DIR}/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 ${APP_USER} ${APP_GROUP}
    postrotate
        systemctl kill -s HUP skywarnplus-ng > /dev/null 2>&1 || true
    endscript
}
EOF
    
    print_success "Log rotation configured"
}

print_completion_message() {
    local host_hint
    host_hint="$(hostname -f 2>/dev/null || hostname 2>/dev/null || echo 'this-host')"
    echo ""
    echo "Installation complete!"
    echo "====================="
    echo ""
    echo "Next steps:"
    echo "1. Start the service (it is already enabled for boot):"
    echo "      sudo systemctl start skywarnplus-ng"
    echo "2. Confirm it is running:"
    echo "      sudo systemctl status skywarnplus-ng"
    echo "3. Open the web dashboard and use the Configuration section for counties,"
    echo "   Asterisk node numbers, TTS, scripts, and other settings. You do not need"
    echo "   to edit ${CONFIG_DIR}/config.yaml by hand for normal setup."
    if command -v apache2ctl >/dev/null 2>&1 && [ -f "${APACHE_PROXY_AVAILABLE}" ]; then
        echo "      http://localhost/skywarnplus-ng/"
        echo "   Direct (bypass Apache): http://localhost:${WEB_PORT}/skywarnplus-ng/"
        echo "   Remote (firewall permitting):"
        echo "      http://${host_hint}/skywarnplus-ng/"
    else
        echo "      http://localhost:${WEB_PORT}/skywarnplus-ng/"
        echo "   From another machine (firewall permitting):"
        echo "      http://${host_hint}:${WEB_PORT}/skywarnplus-ng/"
    fi
    echo "4. After saving changes in the UI, restart the service if prompted, or run:"
    echo "      sudo systemctl restart skywarnplus-ng"
    echo ""
    echo "Logs:"
    echo "      sudo journalctl -u skywarnplus-ng -f"
    echo ""
    echo "Asterisk integration:"
    echo "- DTMF config: ${DTMF_CONFIG} (generated during install)"
    echo "- Enable SkyDescribe for your node via ASL-menu"
    echo "- Audio files: ${INSTALL_ROOT}/SOUNDS/"
    echo "- Apache reverse proxy: /skywarnplus-ng → 127.0.0.1:${WEB_PORT} (installed when Apache is present)"
    echo ""
    echo "Piper TTS (default local voice):"
    if [ -f "${PIPER_MODEL_DIR}/${PIPER_MODEL}.onnx" ]; then
        echo "- Model installed at: ${PIPER_MODEL_DIR}/${PIPER_MODEL}.onnx"
    else
        echo "- Model not found at ${PIPER_MODEL_DIR}/${PIPER_MODEL}.onnx (download may have failed)."
        echo "  Install a .onnx + .onnx.json pair there or switch to gTTS in the Configuration tab."
    fi
    echo "- Default engine is Piper; the Web UI can leave model path blank to use the install path."
    echo "- Use PIPER_QUALITY=medium before install to use en_US-amy-medium instead of low."
    echo ""
}

# ============================================================================
# Main Installation Flow
# ============================================================================

main() {
    print_section "Installing SkywarnPlus-NG (Traditional Method)"
    
    # Pre-installation checks
    check_not_root
    check_python_version
    check_asterisk_user
    
    # Installation steps
    install_system_dependencies
    create_directories
    install_piper_model
    install_sound_files
    copy_source_files
    install_python_dependencies
    setup_configuration
    generate_dtmf_configuration
    copy_scripts
    create_systemd_service
    clear_port
    create_logrotate_config
    install_apache_proxy
    
    # Completion message
    print_completion_message
}

# Run main function
main
