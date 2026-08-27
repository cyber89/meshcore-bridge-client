# Guía de Despliegue: MeshCore Universal Bridge <-> MQTT <-> n8n

Esta guía describe el procedimiento para desplegar el puente **MeshCore Bridge** en **Armbian (Orange Pi 2W)**, **Raspberry Pi**, **Debian** o **Ubuntu** con arranque automático mediante **systemd**, broker **Mosquitto** y conexión a **n8n**.

---

## 📻 Dispositivos de Radio LoRa Compatibles

El puente es **100% compatible con cualquier placa** que ejecute el firmware **MeshCore Companion USB (v1.17+)**:

| Fabricante / Familia | Modelos Soportados | Chipset USB Típico | Puerto Serial Habitual |
| :--- | :--- | :--- | :--- |
| **Heltec Automation** | WiFi LoRa 32 (v2/v3/v4), Wireless Stick / Lite, Wireless Tracker, Wireless Paper, Capsule. | CP2102 / CH9102 / ESP32-S3 CDC | `/dev/ttyACM0` o `/dev/ttyUSB0` |
| **LilyGO TTGO** | T-Beam (v1.1/v1.2/Supreme), T-Echo (nRF52840), T3S3, T-Deck, LoRa32. | CH9102 / CP2104 / CDC ACM | `/dev/ttyACM0` o `/dev/ttyUSB0` |
| **RAKwireless** | WisBlock RAK4631 (nRF52840), RAK11200, RAK11310 (RP2040), WisMesh Hub/Pocket. | Nordic CDC-ACM / RP2040 CDC | `/dev/ttyACM0` |
| **Seeed Studio** | SenseCAP Indicator/Tracker, Wio-E5 mini, Xiao ESP32-S3 / Xiao nRF52840. | CP2102 / CDC ACM | `/dev/ttyACM0` o `/dev/ttyUSB0` |
| **Raspberry Pi** | Pico / Pico W + Waveshare SX1262 LoRa Node / RP2040 LoRa. | RP2040 USB CDC | `/dev/ttyACM0` |

---

## ⚡ Método 1: Instalación Rápida en 1 Comando (Recomendado)

Si ya clonaste o descargaste esta carpeta en tu Orange Pi / servidor Linux, simplemente ejecuta el instalador automatizado:

```bash
cd meshcore-bridge
# Para instalar desde cero:
sudo bash install.sh

# Para actualizar una instalación existente (conservando .env y base de datos):
sudo bash install.sh --update
```

**El instalador realizará todo de forma 100% automática:**
1. Instala paquetes del sistema (`python3-venv`, `pip`, `mosquitto`, `git`, `udev`).
2. Configura e inicia el broker **Mosquitto** escuchando en `127.0.0.1:1883`.
3. Asigna permisos al usuario para el puerto serial (`dialout` / `tty`).
4. **Detecta automáticamente el puerto de tu placa LoRa** conectada por USB.
5. Despliega los archivos en `/opt/meshcore-bridge` y crea el archivo de configuración `.env`.
6. Crea el entorno virtual e instala las librerías (`paho-mqtt`, `meshcore`, `python-dotenv`).
7. Registra, habilita y arranca el servicio **`meshcore-bridge.service`** en systemd.

---

## 🛠️ Método 2: Despliegue Manual Paso a Paso

### 1. Requisitos Previos

- Placa de desarrollo LoRa (Heltec, LilyGO, RAKwireless, Seeed, RP2040) flasheada con firmware **MeshCore Companion** (v1.17+).
- Cable USB con soporte de datos conectado al host Linux.
- Sistema Operativo Linux (Armbian, Debian 11/12, Ubuntu 22.04/24.04, Raspberry Pi OS).
- Python 3.10 o superior (`python3 --version`).
- Broker Mosquitto y Servidor n8n instalados (local o en red).

---

### 2. Identificación del Dispositivo Serial y Permisos

1. Conecta tu placa LoRa por USB y localiza el puerto asignado:
   ```bash
   dmesg | grep -E "ttyACM|ttyUSB"
   # O lista los dispositivos seriales por ID persistente:
   ls -la /dev/serial/by-id/
   ```
   Generalmente se reconocerá como `/dev/ttyACM0` o `/dev/ttyUSB0`.

2. Agrega tu usuario al grupo `dialout` (o `tty`) para permitir acceso sin permisos de superusuario:
   ```bash
   sudo usermod -aG dialout $USER
   sudo usermod -aG tty $USER
   ```
   *(Cierra sesión y vuelve a entrar para aplicar los cambios).*

---

### 3. Instalación de Dependencias del Sistema

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv mosquitto mosquitto-clients git
```

---

### 4. Configuración del Broker Mosquitto

Crea el archivo de configuración para permitir conexiones locales:

```bash
sudo tee /etc/mosquitto/conf.d/meshcore_local.conf << 'EOF'
listener 1883 0.0.0.0
allow_anonymous true
EOF

sudo systemctl restart mosquitto
sudo systemctl enable mosquitto
```

---

### 5. Configuración del Entorno Python

1. Copia los archivos del proyecto a `/opt/meshcore-bridge`:
   ```bash
   sudo mkdir -p /opt/meshcore-bridge
   sudo cp -r . /opt/meshcore-bridge/
   sudo chown -R $USER:$USER /opt/meshcore-bridge
   cd /opt/meshcore-bridge
   ```

2. Crea y activa un entorno virtual Python:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Configura el archivo de variables de entorno `.env`:
    ```bash
    cp .env.example .env
    nano .env
    ```
    *Verifica que `SERIAL_PORT` apunte a tu dispositivo (ej. `/dev/ttyACM0`, `/dev/ttyUSB0` o `AUTO`) y que `SQLITE_DB_PATH` use `data/meshcore_buffer.db`.*

---

### 6. Configuración del Servicio systemd

1. Copia y edita la plantilla de servicio:
   ```bash
   sudo cp meshcore-bridge.service /etc/systemd/system/
   ```

2. Recarga los demonios de systemd y activa el servicio:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable meshcore-bridge.service
   sudo systemctl start meshcore-bridge.service
   ```

3. Verifica el estado y los logs en vivo:
   ```bash
   sudo systemctl status meshcore-bridge.service
   sudo journalctl -u meshcore-bridge.service -f
   ```

---

## 🌐 Acceso a la Estación Web SPA y Seguridad

Una vez iniciado el servicio, accede desde cualquier navegador en la misma red local:

- **URL de la Estación Web**: `http://<IP_DE_TU_SERVIDOR>:8080`
- **Indicador de Vivacidad**: El badge en la barra superior mostrará **`⬤ Conectado`** en tiempo real mediante WebSockets RFC 6455.
- **Autenticación (Opcional)**: Si configuras `BRIDGE_API_KEY=tu_clave_secreta` en `.env`:
  1. Ve a **⚙️ Ajustes ➔ 🔐 Seguridad & API**.
  2. Escribe tu clave secreta en el campo correspondiente y pulsa **Guardar**.
  3. Tu navegador quedará automáticamente autorizado para emitir mensajes y enviar comandos administrativos.

---

## 📱 Conexión con Companion Apps Móviles (Android / iOS / CLI)

El bridge incluye un servidor TCP Companion integrado (compatible con el protocolo oficial MeshCore):
- **Host**: IP de tu servidor o Raspberry Pi
- **Puerto**: `5000` (configurable mediante `TCP_SERVER_PORT`)
- **Límite Conexiones**: Hasta 8 clientes simultáneos (`MAX_COMPANION_CLIENTS=8`) con protección contra DoS.
- **Token de Acceso (Opcional)**: Configurable mediante `COMPANION_TOKEN` en `.env`.

---

## 🔄 Cómo Cambiar de Placa LoRa

Si en cualquier momento cambias de placa (por ejemplo, cambias un Heltec por un RAK4631 o LilyGO T-Echo):

1. Desconecta la placa anterior y conecta la nueva por USB.
2. Ejecuta una actualización rápida:
   ```bash
   sudo bash install.sh --update
   ```
3. El instalador detectará el nuevo puerto serial y reiniciará el servicio automáticamente.

---

## 📊 Monitoreo y Verificación

### 1. Monitorear mensajes de radio recibidos (RX):
```bash
mosquitto_sub -t "meshcore/rx/#" -v
```

### 2. Enviar mensaje de prueba por radio (TX):
```bash
mosquitto_pub -t "meshcore/tx" -m '{"to": "broadcast", "channel_index": 0, "text": "Prueba de enlace LoRa"}'
```

### 3. Consultar telemetría de salud del bridge:
```bash
mosquitto_sub -t "meshcore/bridge/health" -v
```

### 4. Consultar API REST de estado:
```bash
curl -s http://127.0.0.1:8080/api/status | jq .
```
