#!/usr/bin/env bash
# ==============================================================================
# MeshCore Bridge - Script de Instalación, Actualización y Despliegue Automatizado
# Versión: 2.1.0 (Producción)
# Compatible con Armbian (Orange Pi 2W), Debian, Ubuntu y Raspberry Pi OS
# ==============================================================================

set -euo pipefail

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
TARGET_USER="${SUDO_USER:-$USER}"

echo -e "${CYAN}"
echo "=================================================================="
echo "    🚀 GESTOR UNIVERSAL DE MESHCORE BRIDGE (v2.1.0)"
echo "    Heltec / LilyGO / RAKwireless / Seeed / RP2040 <-> MQTT <-> n8n"
echo "=================================================================="
echo -e "${NC}"

# 1. Comprobar privilegios de superusuario
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}[ERROR] Este script debe ejecutarse con permisos de superusuario (root o sudo).${NC}"
   echo "Por favor ejecuta: sudo bash install.sh [opciones]"
   exit 1
fi

# 2. Manejo de Desinstalación (--uninstall)
if [[ "${1:-}" == "--uninstall" ]]; then
    echo -e "${YELLOW}[!] Iniciando desinstalación de MeshCore Bridge...${NC}"
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/$SERVICE_NAME"
    systemctl daemon-reload
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}[OK] MeshCore Bridge desinstalado correctamente.${NC}"
    exit 0
fi

# 3. Manejo de Actualización en Caliente (--update)
if [[ "${1:-}" == "--update" ]]; then
    echo -e "${CYAN}==================================================================${NC}"
    echo -e "${YELLOW}    🔄 ACTUALIZANDO INSTALACIÓN EXISTENTE DE MESHCORE BRIDGE${NC}"
    echo -e "${CYAN}==================================================================${NC}"
    
    if [[ ! -d "$INSTALL_DIR" ]]; then
        echo -e "${RED}[ERROR] No se encontró una instalación previa en ${INSTALL_DIR}.${NC}"
        echo "Ejecuta 'sudo bash install.sh' para realizar una instalación completa."
        exit 1
    fi

    echo -e "${BLUE}[1/5] Deteniendo servicio actual...${NC}"
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true

    echo -e "${BLUE}[2/5] Actualizando archivos de código fuente, paquete src/ y documentación...${NC}"
    cp -f "$CURRENT_DIR/config.py" "$INSTALL_DIR/"
    cp -f "$CURRENT_DIR/meshcore_bridge.py" "$INSTALL_DIR/"
    cp -f "$CURRENT_DIR/pyproject.toml" "$INSTALL_DIR/" 2>/dev/null || true
    cp -f "$CURRENT_DIR/requirements.txt" "$INSTALL_DIR/"
    cp -f "$CURRENT_DIR/meshcore-bridge.service" "$INSTALL_DIR/"
    
    # Copiar paquete modular src/
    mkdir -p "$INSTALL_DIR/src"
    cp -rf "$CURRENT_DIR/src/"* "$INSTALL_DIR/src/"
    
    # Copiar documentación
    mkdir -p "$INSTALL_DIR/docs"
    cp -rf "$CURRENT_DIR/docs/"* "$INSTALL_DIR/docs/" 2>/dev/null || true

    # Si .env existe, conservarlo e incorporar nuevas variables si faltan
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        if ! grep -q "SQLITE_DB_PATH" "$INSTALL_DIR/.env"; then
            echo "" >> "$INSTALL_DIR/.env"
            echo "# Base de datos SQLite persistente Store & Forward" >> "$INSTALL_DIR/.env"
            echo "SQLITE_DB_PATH=${INSTALL_DIR}/meshcore_buffer.db" >> "$INSTALL_DIR/.env"
            echo -e "${GREEN}[OK] Variable SQLITE_DB_PATH añadida a tu .env existente.${NC}"
        fi
    fi

    # Corregir configuración de Mosquitto por si tenía directivas duplicadas
    MOSQUITTO_CONF_DIR="/etc/mosquitto/conf.d"
    if [[ -d "$MOSQUITTO_CONF_DIR" ]]; then
        cat << 'EOF' > "$MOSQUITTO_CONF_DIR/meshcore_local.conf"
# Configuración de acceso para MeshCore Bridge
listener 1883 0.0.0.0
allow_anonymous true
EOF
        systemctl restart mosquitto 2>/dev/null || true
    fi

    echo -e "${BLUE}[3/5] Actualizando dependencias de Python en entorno virtual...${NC}"
    if [[ -d "$INSTALL_DIR/venv" ]]; then
        "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
        "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
    else
        python3 -m venv "$INSTALL_DIR/venv"
        "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
        "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
    fi

    chown -R "$TARGET_USER:$TARGET_USER" "$INSTALL_DIR"

    echo -e "${BLUE}[4/5] Actualizando unidad systemd...${NC}"
    cp -f "$INSTALL_DIR/meshcore-bridge.service" "$SYSTEMD_DIR/$SERVICE_NAME"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
    systemctl restart "$SERVICE_NAME"

    echo -e "${BLUE}[5/5] Verificando estado del servicio...${NC}"
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}[OK] ¡Servicio ${SERVICE_NAME} actualizado y en ejecución!${NC}"
    else
        echo -e "${YELLOW}[AVISO] El servicio está reiniciando o conectando serial.${NC}"
        echo "       Revisa logs con: sudo journalctl -u $SERVICE_NAME -n 20"
    fi

    echo ""
    echo -e "${GREEN}    🎉 ¡ACTUALIZACIÓN COMPLETADA CON ÉXITO!${NC}"
    echo "Tu configuración (.env) y base de datos persistente se conservaron intactas."
    echo "Para ver los logs en vivo: sudo journalctl -u meshcore-bridge.service -f"
    echo ""
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

# Asignar permisos de puerto serial al usuario
echo -e "${BLUE}[3/7] Configurando permisos de puerto serial (dialout/tty)...${NC}"
usermod -aG dialout "$TARGET_USER" 2>/dev/null || true
usermod -aG tty "$TARGET_USER" 2>/dev/null || true
echo -e "${GREEN}[OK] Usuario '${TARGET_USER}' añadido al grupo dialout.${NC}"

# Detección automática del puerto serial del dispositivo MeshCore
echo -e "${BLUE}[4/7] Detectando dispositivo MeshCore Companion USB conectado (Heltec, LilyGO, RAK, Seeed, RP2040)...${NC}"
DETECTED_PORT="AUTO"

if ls /dev/serial/by-id/* >/dev/null 2>&1; then
    DETECTED_PORT="$(ls /dev/serial/by-id/* | head -n 1)"
    echo -e "${GREEN}[OK] Puerto persistente detectado: ${DETECTED_PORT}${NC}"
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

cp -rf "$CURRENT_DIR/config.py" "$INSTALL_DIR/"
cp -rf "$CURRENT_DIR/meshcore_bridge.py" "$INSTALL_DIR/"
cp -rf "$CURRENT_DIR/pyproject.toml" "$INSTALL_DIR/" 2>/dev/null || true
cp -rf "$CURRENT_DIR/requirements.txt" "$INSTALL_DIR/"
cp -rf "$CURRENT_DIR/meshcore-bridge.service" "$INSTALL_DIR/"

mkdir -p "$INSTALL_DIR/src"
cp -rf "$CURRENT_DIR/src/"* "$INSTALL_DIR/src/"

mkdir -p "$INSTALL_DIR/docs"
cp -rf "$CURRENT_DIR/docs/"* "$INSTALL_DIR/docs/" 2>/dev/null || true

# Configurar .env si no existe
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    cat << EOF > "$INSTALL_DIR/.env"
# ================================================================
# Configuración del Puente MeshCore <-> MQTT Bridge v2.1
# ================================================================

# Puerto Serial detectado automáticamente (o valor explícito ej: /dev/ttyACM0)
SERIAL_PORT=${DETECTED_PORT}
BAUD_RATE=115200
SERIAL_TIMEOUT=30.0

# Broker Mosquitto MQTT Local
MQTT_BROKER=127.0.0.1
MQTT_PORT=1883
MQTT_USER=
MQTT_PASSWORD=
MQTT_KEEPALIVE=60

# Prefijo de Tópicos MQTT
TOPIC_PREFIX=meshcore

# Base de datos SQLite persistente Store & Forward
SQLITE_DB_PATH=${INSTALL_DIR}/meshcore_buffer.db

# Parámetros de Resiliencia y Radio LoRa
TX_INTERVAL_SEC=1.0
OFFLINE_BUFFER_MAX_SIZE=1000
OFFLINE_BUFFER_TTL_HOURS=48.0
DEDUPLICATION_WINDOW_SEC=60.0
LORA_DEFAULT_SF=11
LORA_DEFAULT_BW_KHZ=250.0
WATCHDOG_INTERVAL_SEC=60.0
HEALTH_METRICS_INTERVAL_SEC=60.0

# Registro
LOG_LEVEL=INFO
EOF
    echo -e "${GREEN}[OK] Archivo .env generado con SERIAL_PORT=${DETECTED_PORT}.${NC}"
else
    echo -e "${YELLOW}[!] Archivo .env existente conservado.${NC}"
fi

# Crear entorno virtual Python e instalar dependencias
echo -e "${BLUE}[6/7] Creando entorno virtual Python e instalando librerías...${NC}"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

# Asegurar permisos del usuario sobre todo el directorio y venv
chown -R "$TARGET_USER:$TARGET_USER" "$INSTALL_DIR"
echo -e "${GREEN}[OK] Entorno virtual y dependencias Python instaladas exitosamente.${NC}"

# Instalar y arrancar el servicio systemd
echo -e "${BLUE}[7/7] Registrando y activando el servicio systemd (${SERVICE_NAME})...${NC}"
cp -f "$INSTALL_DIR/meshcore-bridge.service" "$SYSTEMD_DIR/$SERVICE_NAME"
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
