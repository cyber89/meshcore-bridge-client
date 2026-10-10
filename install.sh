#!/usr/bin/env bash
# ==============================================================================
# MeshCore Bridge - Installation, Update and Deployment
# Version: 3.0.0 (Production)
# Architecture: CPython >= 3.14.8 | FastAPI ASGI | LoRa MeshCore Companion
# For Armbian (Orange Pi), Debian, Ubuntu, Raspberry Pi OS and derivatives
# ==============================================================================

set -Eeuo pipefail

# Terminal styles; plain output when redirected or NO_COLOR is set
BOLD='\033[1m'
DIM='\033[2m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # Reset style
if [[ ! -t 1 || -n "${NO_COLOR+x}" || "${TERM:-}" == "dumb" ]]; then
    BOLD='' DIM='' RED='' GREEN='' YELLOW='' BLUE='' CYAN='' NC=''
fi

# Production directories and paths
INSTALL_DIR="/opt/meshcore-bridge"
SERVICE_NAME="meshcore-bridge.service"
SYSTEMD_DIR="/etc/systemd/system"
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TARGET_USER="${SUDO_USER:-${USER:-root}}"
SERVICE_USER="${MESHCORE_SERVICE_USER:-$TARGET_USER}"
if [[ "$SERVICE_USER" == "root" ]]; then SERVICE_USER="meshcore"; fi
SERVICE_GROUP=""

# Terminal presentation helpers
print_step() {
    local step="$1" title="$2"
    printf '\n%b%s%b  %b%s%b\n' "$CYAN" "$step" "$NC" "$BOLD" "$title" "$NC"
}

print_ok() {
    local msg="$1"
    printf '  %bOK%b    %s\n' "$GREEN" "$NC" "$msg"
}

print_info() {
    local msg="$1"
    printf '  %bINFO%b  %s\n' "$BLUE" "$NC" "$msg"
}

print_warn() {
    local msg="$1"
    printf '  %bWARN%b  %s\n' "$YELLOW" "$NC" "$msg"
}

print_fail() {
    local msg="$1"
    printf '  %bERROR%b %s\n' "$RED" "$NC" "$msg" >&2
}

print_summary() {
    local title="$1"
    printf '\n%b%s%b\n' "$GREEN$BOLD" "$title" "$NC"
    printf '%b%s%b\n' "$DIM" '------------------------------------------------------------' "$NC"
}

print_service_commands() {
    printf '\n%bManage your station%b\n' "$BOLD" "$NC"
    printf '  Status   sudo systemctl status %s\n' "$SERVICE_NAME"
    printf '  Logs     sudo journalctl -u %s -f\n' "$SERVICE_NAME"
    printf '  Restart  sudo systemctl restart %s\n' "$SERVICE_NAME"
    printf '  Update   sudo bash install.sh --update\n'
}

# Command-line options
ACTION="${1:-}"
case "$ACTION" in
    ""|--uninstall|--dev|--update)
        ;;
    --help|-h)
        echo "Usage: sudo bash install.sh [OPTION]"
        echo ""
        echo "Options:"
        echo "  (no option)    Install production files and services in /opt/meshcore-bridge"
        echo "  --update       Update an existing installation; preserve configuration and data"
        echo "  --dev          Set up a local development environment and run quality checks"
        echo "  --uninstall    Remove the service and installation, including configuration and data"
        echo "  --help, -h     Show this help"
        exit 0
        ;;
    *)
        print_fail "Unknown option: '$ACTION'"
        echo "Use 'bash install.sh --help' to see available options."
        exit 1
        ;;
esac

printf '\n%bMeshCore Bridge%b  %b3.0 | Linux installer%b\n' "$CYAN$BOLD" "$NC" "$DIM" "$NC"
printf '  LoRa Companion / MQTT / Web Station\n'
ACTION_NAME="${ACTION#--}"
printf '  Mode: %s\n' "${ACTION_NAME:-install}"

# Help is available without administrator privileges.
if [[ $EUID -ne 0 ]]; then
    print_fail "Administrator privileges are required (root or sudo)."
    printf '  Run: sudo bash install.sh [options]\n'
    exit 1
fi

# A fresh installation must have an independent source before any changes.
if [[ -z "$ACTION" && -d "$INSTALL_DIR" ]]; then
    INSTALL_ROOT="$(cd "$INSTALL_DIR" && pwd -P)"
    if [[ "$CURRENT_DIR" -ef "$INSTALL_DIR" || "$CURRENT_DIR" == "$INSTALL_ROOT/"* ]]; then
        print_fail "The source checkout is inside the installation directory."
        print_info "Use --update, or run a fresh installation from a separate checkout."
        exit 1
    fi
fi

# 2. Uninstall (--uninstall)
if [[ "$ACTION" == "--uninstall" ]]; then
    print_step "1/2" "Remove the system service"
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/$SERVICE_NAME"
    systemctl daemon-reload
    print_ok "System service removed."

    print_step "2/2" "Remove installation files from ${INSTALL_DIR}"
    rm -rf "$INSTALL_DIR"
    print_ok "Installation directory removed."

    print_summary "MeshCore Bridge removed"
    printf '  Removed service, installation files, configuration and data.\n'
    exit 0
fi

# 3. Select stable CPython >= 3.14.8 with virtual environment support
select_runtime_python() {
    local candidate=""
    if [[ -n "${MESHCORE_PYTHON:-}" ]]; then
        candidate="$MESHCORE_PYTHON"
    else
        for py in python3.15 python3.14 python3; do
            if command -v "$py" >/dev/null 2>&1; then
                if "$py" -c 'import sys, venv, ensurepip; raise SystemExit(0 if sys.implementation.name == "cpython" and sys.version_info[:3] >= (3, 14, 8) and sys.version_info.releaselevel == "final" else 1)' 2>/dev/null; then
                    candidate="$py"
                    break
                fi
            fi
        done
    fi

    if [[ -z "$candidate" ]] || ! "$candidate" -c 'import sys, venv, ensurepip; raise SystemExit(0 if sys.implementation.name == "cpython" and sys.version_info[:3] >= (3, 14, 8) and sys.version_info.releaselevel == "final" else 1)' 2>/dev/null; then
        print_fail "No stable CPython >= 3.14.8 with venv and ensurepip was found."
        echo "Candidates: python3.15, python3.14, python3." >&2
        echo "Install venv/ensurepip support for your Python or set MESHCORE_PYTHON to its executable path." >&2
        return 1
    fi
    PYTHON_RUNTIME="$candidate"
    local py_ver
    py_ver="$("$PYTHON_RUNTIME" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
    print_ok "Python runtime: Python ${py_ver} ($("$PYTHON_RUNTIME" -c 'import sys; print(sys.executable)'))"
}

# Service identity and serial access
configure_service_identity() {
    if [[ ! "$SERVICE_USER" =~ ^[a-z_][a-z0-9_-]*\$?$ ]]; then
        print_fail "Invalid MESHCORE_SERVICE_USER: '$SERVICE_USER'"
        return 1
    fi
    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        print_info "Create system service account: $SERVICE_USER..."
        useradd --system --user-group --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
        print_ok "Service account $SERVICE_USER created."
    fi
    if [[ "$(id -u "$SERVICE_USER")" == "0" ]]; then
        print_fail "The production service requires a non-root account (UID must not be 0)."
        return 1
    fi
    SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

    # Grant serial group access
    local group
    for group in ${MESHCORE_SERIAL_GROUPS:-dialout uucp tty}; do
        if getent group "$group" >/dev/null 2>&1; then
            usermod -aG "$group" "$SERVICE_USER"
            print_ok "Added $SERVICE_USER to serial group: $group"
        fi
    done
}

render_service() {
    local template="$1" destination="$2"
    sed -e "s/^User=.*/User=$SERVICE_USER/" -e "s/^Group=.*/Group=$SERVICE_GROUP/" "$template" > "$destination"
}

# 4. Development mode (--dev)
if [[ "$ACTION" == "--dev" ]]; then
    print_step "1/4" "Select Python runtime"
    select_runtime_python
    QA_VENV="$CURRENT_DIR/.venv"
    if [[ ! -x "$QA_VENV/bin/python" ]]; then
        print_info "Create development environment in $QA_VENV"
        "$PYTHON_RUNTIME" -m venv "$QA_VENV"
    fi
    PYTHON_BIN="$QA_VENV/bin/python"
    "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.implementation.name == "cpython" and sys.version_info[:3] >= (3, 14, 8) and sys.version_info.releaselevel == "final" else 1)' || {
        print_fail "The existing .venv is unsupported. Recreate it with stable CPython >= 3.14.8, then rerun --dev."
        exit 1
    }

    print_step "2/4" "Install production and development dependencies"
    "$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel -q
    "$PYTHON_BIN" -m pip install -r "$CURRENT_DIR/requirements.txt" -r "$CURRENT_DIR/requirements-dev.txt"
    print_ok "Production and development dependencies installed."

    print_step "3/4" "Install Chromium for Playwright"
    "$PYTHON_BIN" -m playwright install chromium
    print_ok "Chromium installed."

    print_step "4/4" "Run project quality checks"
    cd "$CURRENT_DIR"
    "$PYTHON_BIN" "$CURRENT_DIR/scripts/run_quality_checks.py"
    print_summary "Development environment ready"
    printf '  Environment  %s\n' "$QA_VENV"
    printf '  Checks       Project quality runner passed\n'
    printf '  Activate     source .venv/bin/activate\n'
    exit 0
fi

# 5. Update mode (--update)
if [[ "$ACTION" == "--update" ]]; then
    print_step "1/5" "Check update prerequisites"
    select_runtime_python
    [[ -d "$INSTALL_DIR" ]] || { print_fail "Installation directory does not exist: $INSTALL_DIR"; exit 1; }
    UPDATE_HELPER="$CURRENT_DIR/scripts/staged_update.py"
    [[ -f "$UPDATE_HELPER" ]] || { print_fail "Update helper not found: $UPDATE_HELPER"; exit 1; }

    print_step "2/5" "Prepare staged release"
    STAGE_DIR="$("$PYTHON_RUNTIME" "$UPDATE_HELPER" prepare "$CURRENT_DIR" "$INSTALL_DIR")"
    STAGE_APPLIED=0
    SERVICE_STOPPED=0
    WAS_ACTIVE=0
    HAD_UNIT=0

    rollback_update() {
        local status="$?"
        trap - ERR INT TERM
        print_warn "Update interrupted; restore the previous installation."
        if [[ "$STAGE_APPLIED" == "1" ]]; then
            "$PYTHON_RUNTIME" "$UPDATE_HELPER" rollback "$STAGE_DIR" || {
                print_fail "Rollback incomplete. Keep $STAGE_DIR for manual recovery."
                exit 1
            }
        fi
        if [[ "$SERVICE_STOPPED" == "1" ]]; then
            if [[ "$HAD_UNIT" == "1" ]]; then
                cp -f "$STAGE_DIR/systemd.previous" "$SYSTEMD_DIR/$SERVICE_NAME"
            else
                rm -f "$SYSTEMD_DIR/$SERVICE_NAME"
            fi
            systemctl daemon-reload
            if [[ "$WAS_ACTIVE" == "1" ]]; then
                systemctl start "$SERVICE_NAME" || print_warn "The previous service could not restart automatically."
            fi
        fi
        "$PYTHON_RUNTIME" "$UPDATE_HELPER" finish "$STAGE_DIR"
        exit "$((status == 0 ? 1 : status))"
    }
    trap rollback_update ERR INT TERM

    print_step "3/5" "Build release environment and install dependencies"
    "$PYTHON_RUNTIME" -m venv "$STAGE_DIR/release/venv"
    STAGED_PYTHON="$STAGE_DIR/release/venv/bin/python"
    "$STAGED_PYTHON" -m pip install --upgrade pip setuptools wheel -q
    "$STAGED_PYTHON" -m pip install -r "$STAGE_DIR/release/requirements.txt"
    "$STAGED_PYTHON" "$STAGE_DIR/release/scripts/check_runtime_dependencies.py" --profile web
    "$STAGED_PYTHON" -m compileall -q "$STAGE_DIR/release/src" "$STAGE_DIR/release/config.py"
    print_ok "Staged dependencies verified and source syntax compiled."

    print_step "4/5" "Apply staged release with rollback support"
    configure_service_identity
    render_service "$STAGE_DIR/release/meshcore-bridge.service" "$STAGE_DIR/systemd.next"
    if [[ -f "$SYSTEMD_DIR/$SERVICE_NAME" ]]; then
        cp -f "$SYSTEMD_DIR/$SERVICE_NAME" "$STAGE_DIR/systemd.previous"
        HAD_UNIT=1
    fi
    if systemctl is-active --quiet "$SERVICE_NAME"; then WAS_ACTIVE=1; fi
    SERVICE_STOPPED=1
    systemctl stop "$SERVICE_NAME"
    STAGE_APPLIED=1
    "$PYTHON_RUNTIME" "$UPDATE_HELPER" apply "$STAGE_DIR"
    "$PYTHON_RUNTIME" "$UPDATE_HELPER" relocate "$STAGE_DIR"
    "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/scripts/check_runtime_dependencies.py" --profile web
    mkdir -p "$INSTALL_DIR/logs" "$INSTALL_DIR/data"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
    cp -f "$STAGE_DIR/systemd.next" "$SYSTEMD_DIR/$SERVICE_NAME"
    systemctl daemon-reload

    print_step "5/5" "Restart and check the updated service"
    systemctl restart "$SERVICE_NAME"
    systemctl is-active --quiet "$SERVICE_NAME"
    trap - ERR INT TERM
    "$PYTHON_RUNTIME" "$UPDATE_HELPER" finish "$STAGE_DIR"
    print_ok "Update complete. Configuration, data, maps and logs preserved."
    print_summary "Station updated"
    printf '  Installation  %s\n' "$INSTALL_DIR"
    printf '  Configuration %s/.env (preserved)\n' "$INSTALL_DIR"
    print_service_commands
    exit 0
fi

# ==============================================================================
# 6. Production installation
# ==============================================================================

# Step 1: System packages (APT)
print_step "1/7" "Install system packages"
apt-get update -qq
apt-get install -y -qq \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    mosquitto \
    mosquitto-clients \
    git \
    curl \
    udev \
    sudo
print_ok "System packages and build tools installed."

# Step 2: Python runtime
print_step "2/7" "Select stable CPython runtime (>= 3.14.8)"
select_runtime_python

# Step 3: Local MQTT broker
print_step "3/7" "Configure and start Mosquitto"
MOSQUITTO_CONF_DIR="/etc/mosquitto/conf.d"
mkdir -p "$MOSQUITTO_CONF_DIR"

cat << 'EOF' > "$MOSQUITTO_CONF_DIR/meshcore_local.conf"
# Local access configuration for MeshCore Bridge
listener 1883 0.0.0.0
allow_anonymous true
EOF

systemctl enable mosquitto >/dev/null 2>&1 || true
systemctl restart mosquitto >/dev/null 2>&1 || true

if systemctl is-active --quiet mosquitto; then
    print_ok "Mosquitto is active on port 1883."
else
    print_warn "Mosquitto did not start. Check: sudo systemctl status mosquitto"
fi

# Step 4: Service identity and serial access
print_step "4/7" "Configure service identity and serial access"
configure_service_identity

# Step 5: Detect connected serial devices
print_step "5/7" "Detect USB serial devices"
DETECTED_PORT="AUTO"

if compgen -G "/dev/serial/by-id/*" > /dev/null 2>&1; then
    DETECTED_PORT="$(find /dev/serial/by-id/ -type l -o -type c 2>/dev/null | head -n 1)"
    if [[ -n "$DETECTED_PORT" ]]; then
        print_ok "Persistent serial path: ${DETECTED_PORT}"
    fi
elif [[ -e /dev/ttyACM0 ]]; then
    DETECTED_PORT="/dev/ttyACM0"
    print_ok "Serial device detected: /dev/ttyACM0"
elif [[ -e /dev/ttyUSB0 ]]; then
    DETECTED_PORT="/dev/ttyUSB0"
    print_ok "Serial device detected: /dev/ttyUSB0"
else
    print_warn "No connected serial device detected. Using AUTO discovery."
fi

# Step 6: Deploy production files
print_step "6/7" "Deploy files to ${INSTALL_DIR}"
mkdir -p "$INSTALL_DIR"

cp -f "$CURRENT_DIR/config.py" "$INSTALL_DIR/"
cp -f "$CURRENT_DIR/meshcore_bridge.py" "$INSTALL_DIR/"
cp -f "$CURRENT_DIR/runtime_requirements.py" "$INSTALL_DIR/"
cp -f "$CURRENT_DIR/pyproject.toml" "$INSTALL_DIR/" 2>/dev/null || true
cp -f "$CURRENT_DIR/requirements.txt" "$INSTALL_DIR/"
cp -f "$CURRENT_DIR/meshcore-bridge.service" "$INSTALL_DIR/"
if [[ -f "$CURRENT_DIR/.env.example" ]]; then
    cp -f "$CURRENT_DIR/.env.example" "$INSTALL_DIR/" 2>/dev/null || true
fi

rm -rf "$INSTALL_DIR/src"
cp -rf "$CURRENT_DIR/src" "$INSTALL_DIR/"

if [[ -d "$CURRENT_DIR/scripts" ]]; then
    mkdir -p "$INSTALL_DIR/scripts"
    cp -rf "$CURRENT_DIR/scripts/"* "$INSTALL_DIR/scripts/" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/scripts/"*.py 2>/dev/null || true
fi

mkdir -p "$INSTALL_DIR/docs"
cp -rf "$CURRENT_DIR/docs/"* "$INSTALL_DIR/docs/" 2>/dev/null || true
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/data"

# Create configuration if missing
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    cp -f "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    sed -i "s|^SERIAL_PORT=AUTO|SERIAL_PORT=${DETECTED_PORT}|" "$INSTALL_DIR/.env"
    print_ok "Created .env with SERIAL_PORT=${DETECTED_PORT}."
else
    print_ok "Existing .env preserved."
fi

# Create the Python environment and install production dependencies
print_info "Create isolated Python environment in ${INSTALL_DIR}/venv"
"$PYTHON_RUNTIME" -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip setuptools wheel -q
print_info "Install production dependencies from requirements.txt"
"$INSTALL_DIR/venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt" -q
print_info "Check installed dependencies for the web profile"
"$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/scripts/check_runtime_dependencies.py" --profile web

chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
print_ok "Python environment ready; dependency imports and versions verified."

# Step 7: Register and start the service
print_step "7/7" "Register and start ${SERVICE_NAME}"
render_service "$INSTALL_DIR/meshcore-bridge.service" "$SYSTEMD_DIR/$SERVICE_NAME"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
systemctl restart "$SERVICE_NAME"

sleep 2

if systemctl is-active --quiet "$SERVICE_NAME"; then
    SERVICE_ACTIVE=1
    print_ok "Service ${SERVICE_NAME} is active."
else
    SERVICE_ACTIVE=0
    print_warn "The service is not active. Inspect its logs before using the station."
    echo "       Check logs: sudo journalctl -u $SERVICE_NAME -n 20"
fi

# ==============================================================================
# Installation summary
# ==============================================================================
LOCAL_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -z "$LOCAL_IP" ]]; then LOCAL_IP="localhost"; fi

if [[ "$SERVICE_ACTIVE" == "1" ]]; then
    print_summary "Installation complete"
else
    print_summary "Installation files ready; service needs attention"
fi
printf '  Installation  %s\n' "$INSTALL_DIR"
printf '  Configuration %s/.env\n' "$INSTALL_DIR"
printf '  Web default   http://%s:8080 (see .env for overrides)\n' "$LOCAL_IP"
printf '  MQTT broker   127.0.0.1:1883 (meshcore/#)\n'
printf '  Serial port   %s\n' "$DETECTED_PORT"
printf '  Service user  %s\n' "$SERVICE_USER"
print_service_commands
printf "  MQTT     mosquitto_sub -t 'meshcore/#' -v\n"
printf '  Remove   sudo bash install.sh --uninstall\n'
printf '\n'
