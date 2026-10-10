#!/usr/bin/env bash
# ==============================================================================
# MeshCore Bridge - Script de Instalación, Actualización y Despliegue Automatizado
# Versión: 3.0.0 (Producción)
# Arquitectura: CPython >= 3.11 | FastAPI ASGI | LoRa MeshCore Companion
# Compatible con Armbian (Orange Pi), Debian, Ubuntu, Raspberry Pi OS y derivados
# ==============================================================================

set -Eeuo pipefail

# Colores y estilos ANSI
BOLD='\033[1m'
DIM='\033[2m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # Sin color

# Directorios y rutas de producción
INSTALL_DIR="/opt/meshcore-bridge"
SERVICE_NAME="meshcore-bridge.service"
SYSTEMD_DIR="/etc/systemd/system"
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_USER="${SUDO_USER:-${USER:-root}}"
SERVICE_USER="${MESHCORE_SERVICE_USER:-$TARGET_USER}"
if [[ "$SERVICE_USER" == "root" ]]; then SERVICE_USER="meshcore"; fi
SERVICE_GROUP=""

# Funciones de presentación y feedback visual
print_step() {
    local step="$1" title="$2"
    echo ""
    echo -e "${CYAN}${BOLD}[${step}]${NC} ${BOLD}${title}${NC}"
}

print_ok() {
    local msg="$1"
    echo -e "  ${GREEN}✔${NC} ${msg}"
}

print_info() {
    local msg="$1"
    echo -e "  ${BLUE}➜${NC} ${DIM}${msg}${NC}"
}

print_warn() {
    local msg="$1"
    echo -e "  ${YELLOW}▲${NC} ${YELLOW}${msg}${NC}"
}

print_fail() {
    local msg="$1"
    echo -e "  ${RED}✖${NC} ${RED}${BOLD}${msg}${NC}" >&2
}

# ==============================================================================
# Banner de Bienvenida
# ==============================================================================
echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║   📡  MeshCore Bridge — Gestor Universal de Instalación (v3.0)   ║"
echo "║   LoRa Companion ⟷ MQTT ⟷ WebSocket ⟷ Web Station SPA (SBC/Linux) ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 1. Comprobar privilegios de superusuario (root)
if [[ $EUID -ne 0 ]]; then
   print_fail "[ERROR] Este script debe ejecutarse con permisos de superusuario (root o sudo)."
   echo "Por favor ejecuta: sudo bash install.sh [opciones]"
   exit 1
fi

# Validación de opciones CLI
ACTION="${1:-}"
case "$ACTION" in
    ""|--uninstall|--dev|--update)
        ;;
    --help|-h)
        echo "Uso: sudo bash install.sh [OPCIÓN]"
        echo ""
        echo "Opciones disponibles:"
        echo "  (sin opción)   Instalación completa de producción desde cero en /opt/meshcore-bridge"
        echo "  --update       Actualizar instalación existente conservando datos y configuración"
        echo "  --dev          Modo desarrollo: configurar venv local y dependencias de QA"
        echo "  --uninstall    Desinstalar MeshCore Bridge y retirar el servicio systemd"
        echo "  --help, -h     Mostrar este menú de ayuda"
        exit 0
        ;;
    *)
        print_fail "Opción desconocida: '$ACTION'"
        echo "Usa 'sudo bash install.sh --help' para ver las opciones disponibles."
        exit 1
        ;;
esac

# 2. Manejo de Desinstalación (--uninstall)
if [[ "$ACTION" == "--uninstall" ]]; then
    print_step "1/2" "Deteniendo y retirando servicio de sistema..."
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/$SERVICE_NAME"
    systemctl daemon-reload
    print_ok "Servicio systemd retirado."

    print_step "2/2" "Eliminando archivos en ${INSTALL_DIR}..."
    rm -rf "$INSTALL_DIR"
    print_ok "Directorio de instalación eliminado."

    echo ""
    echo -e "${GREEN}${BOLD}✔ MeshCore Bridge desinstalado correctamente del sistema.${NC}"
    exit 0
fi

# 3. Selección del intérprete Python compatible (>= 3.11)
select_runtime_python() {
    local candidate=""
    if [[ -n "${MESHCORE_PYTHON:-}" ]]; then
        candidate="$MESHCORE_PYTHON"
    else
        for py in python3.14 python3.13 python3.12 python3.11 python3; do
            if command -v "$py" >/dev/null 2>&1; then
                if "$py" -c 'import sys, venv, ensurepip; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
                    candidate="$py"
                    break
                fi
            fi
        done
    fi

    if [[ -z "$candidate" ]] || ! "$candidate" -c 'import sys, venv, ensurepip; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        print_fail "No se encontró CPython >= 3.11 compatible con venv y ensurepip."
        echo "Intérpretes evaluados: python3.14, python3.13, python3.12, python3.11, python3." >&2
        echo "Instala python3-venv y python3-pip o define la variable MESHCORE_PYTHON con la ruta deseada." >&2
        return 1
    fi
    PYTHON_RUNTIME="$candidate"
    local py_ver
    py_ver="$("$PYTHON_RUNTIME" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
    print_ok "Intérprete Python compatible detectado: Python ${py_ver} ($("$PYTHON_RUNTIME" -c 'import sys; print(sys.executable)'))"
}

# Configuración de identidad de usuario y permisos seriales
configure_service_identity() {
    if [[ ! "$SERVICE_USER" =~ ^[a-z_][a-z0-9_-]*\$?$ ]]; then
        print_fail "MESHCORE_SERVICE_USER inválido: '$SERVICE_USER'"
        return 1
    fi
    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        print_info "Creando cuenta de servicio de sistema: $SERVICE_USER..."
        useradd --system --user-group --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
        print_ok "Cuenta de servicio $SERVICE_USER creada."
    fi
    if [[ "$(id -u "$SERVICE_USER")" == "0" ]]; then
        print_fail "El servicio de producción requiere una cuenta no-root (sin UID 0)"
        return 1
    fi
    SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

    # Conceder acceso a grupos seriales
    local group
    for group in ${MESHCORE_SERIAL_GROUPS:-dialout uucp tty}; do
        if getent group "$group" >/dev/null 2>&1; then
            usermod -aG "$group" "$SERVICE_USER"
            print_ok "Usuario $SERVICE_USER agregado al grupo serial: $group"
        fi
    done
}

render_service() {
    local template="$1" destination="$2"
    sed -e "s/^User=.*/User=$SERVICE_USER/" -e "s/^Group=.*/Group=$SERVICE_GROUP/" "$template" > "$destination"
}

# 4. Modo Desarrollo (--dev)
if [[ "$ACTION" == "--dev" ]]; then
    print_step "1/4" "Buscando intérprete Python compatible..."
    select_runtime_python
    QA_VENV="$CURRENT_DIR/.venv"
    if [[ ! -x "$QA_VENV/bin/python" ]]; then
        print_info "Creando entorno virtual QA en $QA_VENV..."
        "$PYTHON_RUNTIME" -m venv "$QA_VENV"
    fi
    PYTHON_BIN="$QA_VENV/bin/python"
    "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'

    print_step "2/4" "Instalando dependencias de producción y herramientas de desarrollo..."
    "$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel -q
    "$PYTHON_BIN" -m pip install -r "$CURRENT_DIR/requirements.txt" -r "$CURRENT_DIR/requirements-dev.txt"
    print_ok "Dependencias de producción y desarrollo instaladas."

    print_step "3/4" "Instalando Chromium para pruebas de navegador (Playwright)..."
    "$PYTHON_BIN" -m playwright install chromium
    print_ok "Navegador Chromium instalado."

    print_step "4/4" "Ejecutando verificador de calidad del proyecto..."
    cd "$CURRENT_DIR"
    "$PYTHON_BIN" "$CURRENT_DIR/scripts/run_quality_checks.py"
    echo ""
    print_ok "Entorno de desarrollo verificado y listo."
    exit 0
fi

# 5. Modo Actualización (--update)
if [[ "$ACTION" == "--update" ]]; then
    print_step "1/5" "Verificando entorno Python para actualización..."
    select_runtime_python
    [[ -d "$INSTALL_DIR" ]] || { print_fail "No existe el directorio de instalación $INSTALL_DIR"; exit 1; }
    UPDATE_HELPER="$CURRENT_DIR/scripts/staged_update.py"
    [[ -f "$UPDATE_HELPER" ]] || { print_fail "No se encontró el script auxiliar $UPDATE_HELPER"; exit 1; }

    print_step "2/5" "Preparando staging temporal de actualización..."
    STAGE_DIR="$("$PYTHON_RUNTIME" "$UPDATE_HELPER" prepare "$CURRENT_DIR" "$INSTALL_DIR")"
    STAGE_APPLIED=0
    SERVICE_STOPPED=0
    WAS_ACTIVE=0
    HAD_UNIT=0

    rollback_update() {
        local status="$?"
        trap - ERR INT TERM
        print_warn "Actualización interrumpida; recuperando instalación anterior..."
        if [[ "$STAGE_APPLIED" == "1" ]]; then
            "$PYTHON_RUNTIME" "$UPDATE_HELPER" rollback "$STAGE_DIR" || {
                print_fail "Rollback incompleto. Conserva $STAGE_DIR para recuperación manual."
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
                systemctl start "$SERVICE_NAME" || print_warn "Servicio anterior no pudo arrancar automáticamente."
            fi
        fi
        "$PYTHON_RUNTIME" "$UPDATE_HELPER" finish "$STAGE_DIR"
        exit "$((status == 0 ? 1 : status))"
    }
    trap rollback_update ERR INT TERM

    print_step "3/5" "Construyendo entorno virtual de release y actualizando paquetes..."
    "$PYTHON_RUNTIME" -m venv "$STAGE_DIR/release/venv"
    STAGED_PYTHON="$STAGE_DIR/release/venv/bin/python"
    "$STAGED_PYTHON" -m pip install --upgrade pip setuptools wheel -q
    "$STAGED_PYTHON" -m pip install -r "$STAGE_DIR/release/requirements.txt"
    "$STAGED_PYTHON" "$STAGE_DIR/release/scripts/check_runtime_dependencies.py" --profile web
    "$STAGED_PYTHON" -m compileall -q "$STAGE_DIR/release/src" "$STAGE_DIR/release/config.py"
    print_ok "Dependencias actualizadas y código compilado en staging."

    print_step "4/5" "Aplicando actualización de manera transaccional..."
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

    print_step "5/5" "Reiniciando servicio actualizado..."
    systemctl restart "$SERVICE_NAME"
    systemctl is-active --quiet "$SERVICE_NAME"
    trap - ERR INT TERM
    "$PYTHON_RUNTIME" "$UPDATE_HELPER" finish "$STAGE_DIR"
    print_ok "Actualización completada exitosamente. Archivos .env, datos, mapas y logs conservados."
    exit 0
fi

# ==============================================================================
# 6. Instalación Completa de Producción desde Cero
# ==============================================================================

# Paso 1: Dependencias del sistema operativo (APT)
print_step "1/7" "Actualizando repositorios e instalando paquetes del sistema..."
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
print_ok "Paquetes del sistema base y herramientas de compilación instalados."

# Paso 2: Detección del runtime de Python
print_step "2/7" "Comprobando entorno de ejecución Python (>= 3.11)..."
select_runtime_python

# Paso 3: Configurar e Iniciar Mosquitto MQTT Broker
print_step "3/7" "Configurando e iniciando Mosquitto MQTT Broker..."
MOSQUITTO_CONF_DIR="/etc/mosquitto/conf.d"
mkdir -p "$MOSQUITTO_CONF_DIR"

cat << 'EOF' > "$MOSQUITTO_CONF_DIR/meshcore_local.conf"
# Configuración local de acceso para MeshCore Bridge
listener 1883 0.0.0.0
allow_anonymous true
EOF

systemctl enable mosquitto >/dev/null 2>&1 || true
systemctl restart mosquitto >/dev/null 2>&1 || true

if systemctl is-active --quiet mosquitto; then
    print_ok "Broker Mosquitto activo y escuchando en el puerto 1883."
else
    print_warn "Mosquitto no pudo iniciar automáticamente. Verifica con: sudo systemctl status mosquitto"
fi

# Paso 4: Configurar cuenta de servicio y permisos seriales
print_step "4/7" "Configurando cuenta de servicio y permisos de puerto serie..."
configure_service_identity

# Paso 5: Detección automática del puerto serial del dispositivo MeshCore
print_step "5/7" "Detectando transceptor MeshCore LoRa conectado por USB..."
DETECTED_PORT="AUTO"

if compgen -G "/dev/serial/by-id/*" > /dev/null 2>&1; then
    DETECTED_PORT="$(find /dev/serial/by-id/ -type l -o -type c 2>/dev/null | head -n 1)"
    if [[ -n "$DETECTED_PORT" ]]; then
        print_ok "Puerto persistente detectado por ID: ${DETECTED_PORT}"
    fi
elif [[ -e /dev/ttyACM0 ]]; then
    DETECTED_PORT="/dev/ttyACM0"
    print_ok "Dispositivo LoRa detectado en: /dev/ttyACM0"
elif [[ -e /dev/ttyUSB0 ]]; then
    DETECTED_PORT="/dev/ttyUSB0"
    print_ok "Dispositivo LoRa detectado en: /dev/ttyUSB0"
else
    print_warn "No se detectó un puerto serial conectado actualmente. Se configurará en modo 'AUTO'."
fi

# Paso 6: Despliegue de archivos en /opt/meshcore-bridge
print_step "6/7" "Desplegando archivos del sistema en ${INSTALL_DIR}..."
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

# Configurar .env si no existe
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    cp -f "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    sed -i "s/^SERIAL_PORT=AUTO/SERIAL_PORT=${DETECTED_PORT}/" "$INSTALL_DIR/.env"
    print_ok "Archivo .env creado con SERIAL_PORT=${DETECTED_PORT}."
else
    print_ok "Archivo .env existente conservado intacto."
fi

# Crear entorno virtual Python e instalar dependencias completas
print_info "Creando entorno virtual Python aislado en ${INSTALL_DIR}/venv..."
"$PYTHON_RUNTIME" -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip setuptools wheel -q
print_info "Instalando paquetes desde requirements.txt (FastAPI, MeshCore SDK, MQTT, Uvicorn, Websockets)..."
"$INSTALL_DIR/venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt" -q
print_info "Verificando integridad del perfil web y dependencias instaladas..."
"$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/scripts/check_runtime_dependencies.py" --profile web

chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
print_ok "Entorno virtual y dependencias Python instaladas y certificadas con éxito."

# Paso 7: Instalar y arrancar el servicio systemd
print_step "7/7" "Registrando y activando servicio systemd (${SERVICE_NAME})..."
render_service "$INSTALL_DIR/meshcore-bridge.service" "$SYSTEMD_DIR/$SERVICE_NAME"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
systemctl restart "$SERVICE_NAME"

sleep 2

if systemctl is-active --quiet "$SERVICE_NAME"; then
    print_ok "Servicio ${SERVICE_NAME} activo y en ejecución continua."
else
    print_warn "El servicio está iniciando o esperando conexión serial."
    echo "       Revisa los logs con: sudo journalctl -u $SERVICE_NAME -n 20"
fi

# ==============================================================================
# Tarjeta de Resumen Final
# ==============================================================================
LOCAL_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -z "$LOCAL_IP" ]]; then LOCAL_IP="localhost"; fi

echo ""
echo -e "${GREEN}${BOLD}==================================================================${NC}"
echo -e "${GREEN}${BOLD}    🎉 ¡INSTALACIÓN DE MESHCORE BRIDGE COMPLETADA EXITOSAMENTE!   ${NC}"
echo -e "${GREEN}${BOLD}==================================================================${NC}"
echo -e "  📂 Directorio del servicio:  ${CYAN}${INSTALL_DIR}${NC}"
echo -e "  ⚙️ Archivo de configuración: ${CYAN}${INSTALL_DIR}/.env${NC}"
echo -e "  🌐 Web Station SPA:          ${YELLOW}http://${LOCAL_IP}:8080${NC} o ${YELLOW}http://localhost:8080${NC}"
echo -e "  📡 Broker MQTT Local:        ${CYAN}127.0.0.1:1883 (meshcore/#)${NC}"
echo -e "  🔌 Puerto Serial LoRa:       ${CYAN}${DETECTED_PORT}${NC}"
echo -e "${DIM}------------------------------------------------------------------${NC}"
echo -e "${BOLD}Comandos útiles de gestión:${NC}"
echo -e "  • Ver estado del servicio:     ${CYAN}sudo systemctl status ${SERVICE_NAME}${NC}"
echo -e "  • Ver logs en tiempo real:     ${CYAN}sudo journalctl -u ${SERVICE_NAME} -f${NC}"
echo -e "  • Reiniciar el puente:         ${CYAN}sudo systemctl restart ${SERVICE_NAME}${NC}"
echo -e "  • Actualizar a nueva versión:  ${CYAN}sudo bash install.sh --update${NC}"
echo -e "  • Monitorear tráfico MQTT:     ${CYAN}mosquitto_sub -t 'meshcore/#' -v${NC}"
echo -e "  • Desinstalar por completo:    ${CYAN}sudo bash install.sh --uninstall${NC}"
echo -e "${GREEN}${BOLD}==================================================================${NC}"
echo ""
