#!/usr/bin/env bash
# ==============================================================================
# MeshCore Bridge - Script de Instalación, Actualización y Despliegue Automatizado
# Versión: 3.0.0 (Producción)
# Compatible con Armbian (Orange Pi 2W), Debian, Ubuntu y Raspberry Pi OS
# ==============================================================================

set -Eeuo pipefail

# Colores para la terminal
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Directorios y rutas
INSTALL_DIR="/opt/meshcore-bridge"
SERVICE_NAME="meshcore-bridge.service"
SYSTEMD_DIR="/etc/systemd/system"
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_USER="${SUDO_USER:-${USER:-root}}"
SERVICE_USER="${MESHCORE_SERVICE_USER:-$TARGET_USER}"
if [[ "$SERVICE_USER" == "root" ]]; then SERVICE_USER="meshcore"; fi
SERVICE_GROUP=""

echo -e "${CYAN}"
echo "=================================================================="
echo "    🚀 GESTOR UNIVERSAL DE MESHCORE BRIDGE (v3.0.0)"
echo "    Heltec / LilyGO / RAKwireless / Seeed / RP2040 <-> MQTT <-> n8n"
echo "=================================================================="
echo -e "${NC}"

# 1. Comprobar privilegios de superusuario
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}[ERROR] Este script debe ejecutarse con permisos de superusuario (root o sudo).${NC}"
   echo "Por favor ejecuta: sudo bash install.sh [opciones]"
   exit 1
fi

# Validación de opciones CLI (INS-08)
ACTION="${1:-}"
case "$ACTION" in
    ""|--uninstall|--dev|--update)
        ;;
    --help|-h)
        echo "Uso: sudo bash install.sh [OPCIÓN]"
        echo ""
        echo "Opciones:"
        echo "  (sin opción)   Instalación completa de producción desde cero"
        echo "  --update       Actualizar instalación existente en /opt/meshcore-bridge"
        echo "  --dev          Modo desarrollo y ejecución de verificación de QA"
        echo "  --uninstall    Desinstalar MeshCore Bridge y retirar servicio"
        echo "  --help, -h     Mostrar esta ayuda"
        exit 0
        ;;
    *)
        echo -e "${RED}[ERROR] Opción desconocida: '$ACTION'${NC}"
        echo "Usa 'sudo bash install.sh --help' para ver las opciones disponibles."
        exit 1
        ;;
esac

# 2. Manejo de Desinstalación (--uninstall)
if [[ "$ACTION" == "--uninstall" ]]; then
    echo -e "${YELLOW}[!] Iniciando desinstalación de MeshCore Bridge...${NC}"
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/$SERVICE_NAME"
    systemctl daemon-reload
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}[OK] MeshCore Bridge desinstalado correctamente.${NC}"
    exit 0
fi

# --dev never falls back to globally installing QA dependencies.
if [[ "$ACTION" == "--dev" ]]; then
    QA_VENV="$CURRENT_DIR/.venv"
    if [[ ! -x "$QA_VENV/bin/python" ]]; then
        python3 -m venv "$QA_VENV"
    fi
    PYTHON_BIN="$QA_VENV/bin/python"
    "$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 10), "Python >=3.10 requerido"'
    [[ -f "$CURRENT_DIR/requirements-dev.txt" ]]
    [[ -f "$CURRENT_DIR/scripts/run_quality_checks.py" ]]
    echo "[1/3] Instalando dependencias de QA en $QA_VENV"
    "$PYTHON_BIN" -m pip install -r "$CURRENT_DIR/requirements.txt" -r "$CURRENT_DIR/requirements-dev.txt"
    echo "[2/3] Instalando Chromium para las pruebas de navegador"
    "$PYTHON_BIN" -m playwright install chromium
    echo "[3/3] Ejecutando pytest/cobertura, mypy, ruff y documentación"
    cd "$CURRENT_DIR"
    "$PYTHON_BIN" "$CURRENT_DIR/scripts/run_quality_checks.py"
    echo "[OK] Verificaciones ejecutadas: pytest/cobertura, mypy, ruff y documentación."
    echo "Bandit no forma parte de este runner; no se acredita SAST en esta ejecución."
    exit 0
fi

# Render service identity from an existing non-root invoking account, or a
# dedicated account for installations invoked directly by root.
configure_service_identity() {
    if [[ ! "$SERVICE_USER" =~ ^[a-z_][a-z0-9_-]*\$?$ ]]; then
        echo "[ERROR] MESHCORE_SERVICE_USER inválido" >&2
        return 1
    fi
    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        useradd --system --user-group --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
    fi
    if [[ "$(id -u "$SERVICE_USER")" == "0" ]]; then
        echo "[ERROR] El servicio requiere una cuenta sin UID 0" >&2
        return 1
    fi
    SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
    local group
    for group in ${MESHCORE_SERIAL_GROUPS:-dialout uucp}; do
        if getent group "$group" >/dev/null; then
            usermod -aG "$group" "$SERVICE_USER"
        fi
    done
    echo "[OK] Servicio: $SERVICE_USER:$SERVICE_GROUP. Comprueba el grupo propietario del dispositivo serial."
}

render_service() {
    local template="$1" destination="$2"
    sed -e "s/^User=.*/User=$SERVICE_USER/" -e "s/^Group=.*/Group=$SERVICE_GROUP/" "$template" > "$destination"
}

# --update stages code and a fresh environment before stopping the service.
if [[ "$ACTION" == "--update" ]]; then
    [[ -d "$INSTALL_DIR" ]] || { echo "[ERROR] No existe $INSTALL_DIR" >&2; exit 1; }
    UPDATE_HELPER="$CURRENT_DIR/scripts/staged_update.py"
    [[ -f "$UPDATE_HELPER" ]]
    STAGE_DIR="$(python3 "$UPDATE_HELPER" prepare "$CURRENT_DIR" "$INSTALL_DIR")"
    STAGE_APPLIED=0
    SERVICE_STOPPED=0
    WAS_ACTIVE=0
    HAD_UNIT=0
    rollback_update() {
        local status="$?"
        trap - ERR INT TERM
        echo "[ERROR] Actualización interrumpida; recuperando instalación anterior" >&2
        if [[ "$STAGE_APPLIED" == "1" ]]; then
            python3 "$UPDATE_HELPER" rollback "$STAGE_DIR" || {
                echo "[ERROR] Rollback incompleto. Conserva $STAGE_DIR para recuperación manual." >&2
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
                systemctl start "$SERVICE_NAME" || echo "[ERROR] Código recuperado; servicio anterior no pudo arrancar" >&2
            fi
        fi
        python3 "$UPDATE_HELPER" finish "$STAGE_DIR"
        exit "$((status == 0 ? 1 : status))"
    }
    trap rollback_update ERR INT TERM
    python3 -m venv "$STAGE_DIR/release/venv"
    STAGED_PYTHON="$STAGE_DIR/release/venv/bin/python"
    "$STAGED_PYTHON" -m pip install -r "$STAGE_DIR/release/requirements.txt"
    "$STAGED_PYTHON" "$STAGE_DIR/release/scripts/check_runtime_dependencies.py" --profile web
    "$STAGED_PYTHON" -m compileall -q "$STAGE_DIR/release/src" "$STAGE_DIR/release/config.py"
    configure_service_identity
    render_service "$STAGE_DIR/release/meshcore-bridge.service" "$STAGE_DIR/systemd.next"
    if [[ -f "$SYSTEMD_DIR/$SERVICE_NAME" ]]; then
        cp -f "$SYSTEMD_DIR/$SERVICE_NAME" "$STAGE_DIR/systemd.previous"
        HAD_UNIT=1
    fi
    if systemctl is-active --quiet "$SERVICE_NAME"; then WAS_ACTIVE=1; fi
    SERVICE_STOPPED=1
    systemctl stop "$SERVICE_NAME"
    # Mark before apply: the helper also rolls back internal rename failures.
    STAGE_APPLIED=1
    python3 "$UPDATE_HELPER" apply "$STAGE_DIR"
    python3 "$UPDATE_HELPER" relocate "$STAGE_DIR"
    "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/scripts/check_runtime_dependencies.py" --profile web
    mkdir -p "$INSTALL_DIR/logs" "$INSTALL_DIR/data"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
    cp -f "$STAGE_DIR/systemd.next" "$SYSTEMD_DIR/$SERVICE_NAME"
    systemctl daemon-reload
    systemctl restart "$SERVICE_NAME"
    systemctl is-active --quiet "$SERVICE_NAME"
    trap - ERR INT TERM
    python3 "$UPDATE_HELPER" finish "$STAGE_DIR"
    echo "[OK] Actualización verificada; .env, datos, mapas y logs conservados."
    exit 0
fi

# ==============================================================================
# 4. Instalación Completa desde Cero
# ==============================================================================

echo -e "${BLUE}[1/7] Actualizando repositorios e instalando dependencias del sistema...${NC}"
apt-get update -qq
apt-get install -y -qq \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    build-essential \
    libssl-dev \
    libffi-dev \
    mosquitto \
    mosquitto-clients \
    git \
    curl \
    udev \
    sudo

echo -e "${GREEN}[OK] Dependencias del sistema instaladas.${NC}"

# Configurar e Iniciar Mosquitto MQTT Broker
echo -e "${BLUE}[2/7] Configurando y arrancando Mosquitto MQTT Broker...${NC}"

MOSQUITTO_CONF_DIR="/etc/mosquitto/conf.d"
mkdir -p "$MOSQUITTO_CONF_DIR"

cat << 'EOF' > "$MOSQUITTO_CONF_DIR/meshcore_local.conf"
# Configuración de acceso para MeshCore Bridge
listener 1883 0.0.0.0
allow_anonymous true
EOF

systemctl enable mosquitto >/dev/null 2>&1 || true
systemctl restart mosquitto >/dev/null 2>&1 || true

if systemctl is-active --quiet mosquitto; then
    echo -e "${GREEN}[OK] Broker Mosquitto activo y escuchando en el puerto 1883.${NC}"
else
    echo -e "${YELLOW}[AVISO] Mosquitto no pudo iniciar automáticamente. Verifica con: sudo systemctl status mosquitto${NC}"
fi

# Preparar la misma identidad usada por chown y la unidad antes del despliegue.
echo -e "${BLUE}[3/7] Configurando cuenta del servicio y acceso al puerto serial...${NC}"
configure_service_identity

# Detección automática del puerto serial del dispositivo MeshCore
echo -e "${BLUE}[4/7] Detectando dispositivo MeshCore Companion USB conectado (Heltec, LilyGO, RAK, Seeed, RP2040)...${NC}"
DETECTED_PORT="AUTO"

# Comprobación segura de puertos persistentes por ID sin fallo de subshell
if compgen -G "/dev/serial/by-id/*" > /dev/null 2>&1; then
    DETECTED_PORT="$(find /dev/serial/by-id/ -type l -o -type c 2>/dev/null | head -n 1)"
    if [[ -n "$DETECTED_PORT" ]]; then
        echo -e "${GREEN}[OK] Puerto persistente detectado: ${DETECTED_PORT}${NC}"
    fi
elif [[ -e /dev/ttyACM0 ]]; then
    DETECTED_PORT="/dev/ttyACM0"
    echo -e "${GREEN}[OK] Dispositivo detectado en: /dev/ttyACM0${NC}"
elif [[ -e /dev/ttyUSB0 ]]; then
    DETECTED_PORT="/dev/ttyUSB0"
    echo -e "${GREEN}[OK] Dispositivo detectado en: /dev/ttyUSB0${NC}"
else
    echo -e "${YELLOW}[AVISO] No se detectó un puerto serial conectado actualmente. Se configurará en modo 'AUTO'.${NC}"
fi

# Despliegue de archivos en /opt/meshcore-bridge
echo -e "${BLUE}[5/7] Copiando archivos a ${INSTALL_DIR}...${NC}"
mkdir -p "$INSTALL_DIR"

cp -f "$CURRENT_DIR/config.py" "$INSTALL_DIR/"
cp -f "$CURRENT_DIR/meshcore_bridge.py" "$INSTALL_DIR/"
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
    echo -e "${GREEN}[OK] Archivo .env generado desde plantilla con SERIAL_PORT=${DETECTED_PORT}.${NC}"
else
    echo -e "${YELLOW}[!] Archivo .env existente conservado.${NC}"
fi

# Crear entorno virtual Python e instalar dependencias
echo -e "${BLUE}[6/7] Creando entorno virtual Python e instalando librerías...${NC}"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"
"$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/scripts/check_runtime_dependencies.py" --profile web

# Asegurar permisos del usuario sobre todo el directorio y venv
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
echo -e "${GREEN}[OK] Entorno virtual y dependencias Python instaladas exitosamente.${NC}"

# Instalar y arrancar el servicio systemd
echo -e "${BLUE}[7/7] Registrando y activando el servicio systemd (${SERVICE_NAME})...${NC}"
render_service "$INSTALL_DIR/meshcore-bridge.service" "$SYSTEMD_DIR/$SERVICE_NAME"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
systemctl restart "$SERVICE_NAME"

sleep 2

if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo -e "${GREEN}[OK] Servicio ${SERVICE_NAME} activo y en ejecución continua.${NC}"
else
    echo -e "${YELLOW}[AVISO] El servicio está iniciando o esperando conexión serial.${NC}"
    echo "       Revisa los logs con: sudo journalctl -u $SERVICE_NAME -n 20"
fi

echo ""
echo -e "${CYAN}==================================================================${NC}"
echo -e "${GREEN}    🎉 ¡INSTALACIÓN COMPLETADA EXITOSAMENTE!${NC}"
echo -e "${CYAN}==================================================================${NC}"
echo ""
echo -e "📂 Directorio del servicio:  ${CYAN}${INSTALL_DIR}${NC}"
echo -e "⚙️ Archivo de configuración: ${CYAN}${INSTALL_DIR}/.env${NC}"
echo -e "📡 Broker MQTT:             ${CYAN}127.0.0.1:1883${NC}"
echo -e "🔌 Puerto Serial MeshCore:  ${CYAN}${DETECTED_PORT}${NC}"
echo -e "🌐 Cliente Web Station SPA:  ${GREEN}http://localhost:8080${NC} o ${GREEN}http://$(hostname -I 2>/dev/null | awk '{print $1}'):8080${NC}"
echo ""
echo -e "${YELLOW}Comandos útiles de gestión:${NC}"
echo "  • Abrir Interfaz Web:          Navega a http://<IP-de-la-SBC>:8080"
echo "  • Actualizar servicio:         sudo bash install.sh --update"
echo "  • Ver estado del servicio:     sudo systemctl status meshcore-bridge.service"
echo "  • Ver logs en tiempo real:     sudo journalctl -u meshcore-bridge.service -f"
echo "  • Reiniciar el puente:         sudo systemctl restart meshcore-bridge.service"
echo "  • Monitorear tráfico MQTT:     mosquitto_sub -t 'meshcore/#' -v"
echo "  • Desinstalar:                 sudo bash install.sh --uninstall"
echo ""
echo -e "🔗 Para importar el workflow en n8n, utiliza el archivo:"
echo -e "   ${CYAN}${CURRENT_DIR}/n8n_workflow_meshcore.json${NC}"
echo ""
