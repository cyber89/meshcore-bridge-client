"""
Módulo de Configuración para MeshCore Bridge.
Carga variables de entorno desde un archivo .env si existe o desde el sistema.
"""

import os
from pathlib import Path

# Cargar archivo .env desde el directorio del proyecto
env_path = Path(__file__).resolve().parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)
except ImportError:
    # Fallback si python-dotenv no está instalado: parser nativo de .env
    if env_path.is_file():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("\"'")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

# ================= Configuración Serial =================
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyACM0")
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))
SERIAL_TIMEOUT = float(os.getenv("SERIAL_TIMEOUT", "30.0"))

# ================= Configuración MQTT =================
MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "").strip() or None
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "").strip() or None
MQTT_KEEPALIVE = int(os.getenv("MQTT_KEEPALIVE", "60"))

# ================= Tópicos MQTT =================
TOPIC_PREFIX = os.getenv("TOPIC_PREFIX", "meshcore").strip("/")

TOPIC_STATE       = f"{TOPIC_PREFIX}/bridge/state"      # LWT: online / offline (retained)
TOPIC_HEALTH      = f"{TOPIC_PREFIX}/bridge/health"     # Reporte periódico de salud y métricas
TOPIC_RX_ALL      = f"{TOPIC_PREFIX}/rx/all"           # Tópico unificado para todos los eventos RX
TOPIC_RX_PUBLIC   = f"{TOPIC_PREFIX}/rx/public"        # Canal 0 / broadcast
TOPIC_RX_CHANNEL  = f"{TOPIC_PREFIX}/rx/channel"       # Canales secundarios: {prefix}/rx/channel/ch_{idx}
TOPIC_RX_DIRECT   = f"{TOPIC_PREFIX}/rx/direct"        # Mensajes directos: {prefix}/rx/direct/{sender_id}
TOPIC_RX_TELEMETRY= f"{TOPIC_PREFIX}/rx/telemetry"     # Batería, voltaje y métricas de nodos
TOPIC_RX_NODES    = f"{TOPIC_PREFIX}/rx/nodes"         # Anuncios y nodos descubiertos
TOPIC_RX_LOG      = f"{TOPIC_PREFIX}/rx/log"           # Streaming de logs RF y sniffer de paquetes

TOPIC_TX          = f"{TOPIC_PREFIX}/tx"               # Entrada de transmisión (n8n -> Heltec)
TOPIC_TX_STATUS   = f"{TOPIC_PREFIX}/tx/status"        # Confirmación / ACK de transmisión

TOPIC_ADMIN_CMD   = f"{TOPIC_PREFIX}/admin/cmd"        # Entrada de comandos de administración
TOPIC_ADMIN_STAT  = f"{TOPIC_PREFIX}/admin/status"     # Respuesta de comandos de administración
TOPIC_ADMIN_REPEATER = f"{TOPIC_PREFIX}/admin/repeater" # Gestión remota de repetidores por RF

# ================= Parámetros de Resiliencia y Control =================
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", str(Path(__file__).resolve().parent / "meshcore_buffer.db"))
TX_INTERVAL_SEC = float(os.getenv("TX_INTERVAL_SEC", "1.0"))                 # Espaciado de transmisión RF (LoRa Rate Limiter)
OFFLINE_BUFFER_MAX_SIZE = int(os.getenv("OFFLINE_BUFFER_MAX_SIZE", "1000"))   # Capacidad máxima del buffer offline SQLite
OFFLINE_BUFFER_TTL_HOURS = float(os.getenv("OFFLINE_BUFFER_TTL_HOURS", "48.0")) # TTL máximo para retención de telemetría (horas)
DEDUPLICATION_WINDOW_SEC = float(os.getenv("DEDUPLICATION_WINDOW_SEC", "60.0")) # Ventana temporal de deduplicación de paquetes (segundos)
WATCHDOG_INTERVAL_SEC = float(os.getenv("WATCHDOG_INTERVAL_SEC", "60.0"))     # Intervalo de supervisión de vivacidad serial
HEALTH_METRICS_INTERVAL_SEC = float(os.getenv("HEALTH_METRICS_INTERVAL_SEC", "60.0")) # Intervalo de reporte de salud

# ================= Parámetros de Radio y Airtime LoRa =================
LORA_DEFAULT_SF = int(os.getenv("LORA_DEFAULT_SF", "11"))                     # Spreading Factor por defecto (SF7..SF12)
LORA_DEFAULT_BW_KHZ = float(os.getenv("LORA_DEFAULT_BW_KHZ", "250.0"))       # Ancho de banda en kHz (125, 250, 500)
LORA_DEFAULT_CR = int(os.getenv("LORA_DEFAULT_CR", "5"))                      # Coding Rate (5 = 4/5, 6 = 4/6, etc.)
LORA_PREAMBLE_LEN = int(os.getenv("LORA_PREAMBLE_LEN", "8"))                 # Símbolos de preámbulo

# ================= Logging =================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
