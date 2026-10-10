# Guía de Despliegue: MeshCore Universal Bridge <-> MQTT <-> n8n

Esta guía describe el procedimiento para desplegar el puente **MeshCore Bridge** en **Armbian (Orange Pi 2W)**, **Raspberry Pi**, **Debian** o **Ubuntu** con arranque automático mediante **systemd**, broker **Mosquitto** y conexión a **n8n**.

Guía vigente revisada por lectura de código el 2026-10-09. Los contratos de instaladores comprobados en temporales y comandos simulados el 2026-10-05 son evidencia anterior; esta auditoría no ejecutó instaladores, servicios ni suites. No acredita una instalación real completada ni compatibilidad de cada modelo. Consulte el [índice documental](README.md); los informes de agosto son históricos. Los archivos vigentes son `install.sh`, `install.ps1` y `meshcore-bridge.service` en la raíz; no existe un directorio `deploy/` actual.

---

## 📻 Dispositivos de Radio LoRa Compatibles

El adaptador principal utiliza el SDK `meshcore>=2.3.8` con firmware **MeshCore Companion**. La versión del paquete Python no es la versión del firmware. La compatibilidad y los comandos disponibles dependen del dispositivo y de su firmware; estas familias son ejemplos que requieren verificación en hardware:

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

# Para actualizar una instalación existente (conservando .env y archivos de datos):
sudo bash install.sh --update
```

**El instalador realiza estas tareas si dispone de los permisos, paquetes y servicios necesarios:**
1. Instala paquetes del sistema (`python3-venv`, `pip`, `mosquitto`, `git`, `udev`).
2. Configura e inicia **Mosquitto** escuchando en `0.0.0.0:1883` con `allow_anonymous true`. Esto expone el broker a otras interfaces del host; revise el bind, autenticación y firewall para su red.
3. Utiliza la cuenta invocante `SUDO_USER` sin UID 0; si se invoca directamente como root, crea/usa la cuenta de sistema `meshcore`. Obtiene su grupo primario y añade los grupos serie existentes (`dialout`/`uucp`).
4. **Detecta automáticamente el puerto de tu placa LoRa** conectada por USB.
5. Despliega los archivos en `/opt/meshcore-bridge` y crea el archivo de configuración `.env`.
6. Crea `venv/` e instala `requirements.txt`: cuatro dependencias core y seis de ASGI, detalladas abajo. El bridge incluye un decodificador CayenneLPP propio; `pycayennelpp` y `pyserial-asyncio-fast` pueden instalarse como dependencias transitivas del SDK `meshcore`, aunque el parser raw no las importe directamente.
7. Registra, habilita y arranca el servicio **`meshcore-bridge.service`** en systemd.

### 📦 Dependencias y Perfiles de Verificación

El archivo [`requirements.txt`](../requirements.txt) y las dependencias principales de [`pyproject.toml`](../pyproject.toml) incluyen el stack completo de producción:

| Grupo | Distribuciones y política de versión |
| --- | --- |
| Core | `paho-mqtt>=2.1.0`, `meshcore>=2.3.8`, `pyserial>=3.5`, `python-dotenv>=1.0.1` |
| ASGI | `fastapi==0.143.0`, `uvicorn==0.54.0`, `pydantic==2.14.0`, `websockets==16.1.1`, `starlette==1.7.0`, `h11==0.16.0` |

Los seis pins ASGI corresponden a las interfaces evaluadas de middleware, enrutamiento y protocolo. El comprobador rechaza versiones diferentes, incluidas pre-releases, post-releases y builds locales. Las demás transitivas siguen las restricciones de sus paquetes padres; estos manifests no son un lock completo con hashes. `requirements-web.txt` conserva un punto de entrada compatible mediante `-r requirements.txt`, y el extra `web` conserva los mismos seis pins para comandos existentes.

La verificación con el mismo intérprete del launcher comprueba imports y versiones; no ejecuta endpoints ni acredita el comportamiento de la estación:

- **Perfil `web`**: Verifica cuatro dependencias core y seis ASGI. Es el default sin variable `MESHCORE_PROFILE`; ambos instaladores lo seleccionan explícitamente con `--profile web`:
  ```bash
  python scripts/check_runtime_dependencies.py                  # Por defecto (perfil web)
  python scripts/check_runtime_dependencies.py --profile web    # Explícito
  ```
- **Perfil `core`**: Verifica únicamente las cuatro dependencias mínimas y no importa ASGI durante esa comprobación:
  ```bash
  python scripts/check_runtime_dependencies.py --profile core   # Perfil core headless
  ```

`MESHCORE_PROFILE` selecciona el perfil del comprobador cuando no se pasa `--profile`. Un perfil desconocido falla; no reduce silenciosamente la verificación a core. El argumento explícito tiene prioridad sobre la variable. Este perfil no cambia la configuración de ejecución ni el manifest que instala pip. `WEB_ENABLED=false` desactiva la construcción y arranque web mediante imports diferidos en `bridge_core.py`; no elimina paquetes ya instalados. Los instaladores actuales instalan el manifest completo incluso para una estación headless; no existe un instalador ni manifest mantenido que instale sólo core.

Cuando `WEB_ENABLED=true`, el core crea [`AsgiWebServer`](../src/web/asgi_server.py), con FastAPI y Uvicorn embebido. No hay selector del servidor nativo ni fallback si faltan dependencias. La adopción está implementada en código; las pruebas funcionales de REST, WS, documentación offline, apagado e instalación por plataforma siguen pendientes para esta revisión. No se han medido RAM, arranque ni rendimiento en los gateways citados.

---

## 🛠️ Método 2: Despliegue Manual Paso a Paso

### 1. Requisitos Previos

- Placa LoRa con firmware **MeshCore Companion** compatible con los comandos usados por el SDK.
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

Cree una configuración para un broker limitado al host. Este ejemplo manual usa loopback; difiere del bind abierto que escribe la instalación inicial del instalador actual. La actualización `--update` conserva Mosquitto. Para un n8n remoto, configure explícitamente una interfaz accesible, credenciales y permisos del broker.

```bash
sudo tee /etc/mosquitto/conf.d/meshcore_local.conf << 'EOF'
listener 1883 127.0.0.1
allow_anonymous true
EOF

sudo systemctl restart mosquitto
sudo systemctl enable mosquitto
```

Para un broker remoto con TLS, configure `MQTT_TLS=true`, `MQTT_BROKER` con el nombre cubierto por su certificado y `MQTT_PORT` con el listener elegido por el operador. `MQTT_TLS_CA_FILE` puede señalar una CA propia; vacío utiliza la confianza del sistema operativo. Para mTLS, configure juntos `MQTT_TLS_CERT_FILE` y `MQTT_TLS_KEY_FILE`. Un archivo requerido ausente, una cadena no confiable o un hostname incorrecto producen fallo sin volver a texto plano. Requiere reiniciar el proceso; no se habilita automáticamente al guardar un endpoint de la WebUI. Los defaults locales siguen siendo `MQTT_TLS=false` y puerto 1883. No se instalaron certificados operativos durante esta corrección.

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
    *Verifique `SERIAL_PORT` (`/dev/ttyACM0`, `/dev/ttyUSB0`, `AUTO` o `tcp://host:port`) y `DATA_DIR`. Para USB puede utilizar una ruta persistente de `/dev/serial/by-id/`. El default de `config.py` es `/dev/ttyACM0` fuera de Windows y `AUTO` en Windows; `.env` puede sobrescribirlo.*

---

### 6. Configuración del Servicio systemd

1. Copie y edite la plantilla de servicio, incluyendo `User`, `Group` y permisos del puerto. La plantilla usa `meshcore:meshcore`, `WorkingDirectory=/opt/meshcore-bridge`, `KillMode=control-group`, `NoNewPrivileges=true` y ejecuta `venv/bin/python meshcore_bridge.py`. En instalación manual cree previamente esa cuenta/grupo o sustituya ambos por una cuenta existente sin UID 0 con acceso a datos y dispositivo:
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

El servidor FastAPI publica `/docs` y `/redoc` como visor local, con assets del
repositorio, y `/openapi.json` como catálogo OpenAPI 3.1. Si `BRIDGE_API_KEY` está
configurada, el esquema exige `X-Api-Key`: la clave en query no autentica esta
frontera documental. El formulario del visor solicita el esquema con esa cabecera;
no ejecuta operaciones de radio. El catálogo describe los contratos del dispatcher
y controladores vigentes; sus DTOs descriptivos no sustituyen la validación de
negocio de las peticiones. La comprobación funcional de este visor y las APIs
sigue pendiente de autorización de suites para la revisión actual.

---

## 📱 Conexión con Companion Apps Móviles (Android / iOS / CLI)

El bridge incluye un servidor TCP Companion que recibe comandos binarios y reenvía payloads al Companion conectado. Utiliza framing oficial (`<`/`>` y longitud little-endian); no el framing raw propio `0xAA/0x55`. Su compatibilidad efectiva depende del adaptador y firmware:
- **Host**: IP de tu servidor o Raspberry Pi
- **Puerto**: `5000` (configurable mediante `TCP_SERVER_PORT`)
- **Límite Conexiones**: Hasta 8 clientes simultáneos (`MAX_COMPANION_CLIENTS=8`) con protección contra DoS.
- **Token de Acceso (Opcional)**: Configurable mediante `COMPANION_TOKEN` en `.env`.
- **Lista de IPs (Opcional)**: `COMPANION_ALLOWED_IPS`; vacío permite todas. Estos controles son independientes de `BRIDGE_API_KEY` y de las credenciales MQTT.

---

## 🔄 Cómo Cambiar de Placa LoRa

Si en cualquier momento cambias de placa (por ejemplo, cambias un Heltec por un RAK4631 o LilyGO T-Echo):

1. Desconecta la placa anterior y conecta la nueva por USB.
2. Ejecuta una actualización rápida:
   ```bash
   sudo bash install.sh --update
   ```
3. La actualización conserva `.env` y no cambia `SERIAL_PORT` ni autodetecta la nueva placa. Revise o edite esa variable, los permisos y la identidad del nodo antes de reiniciar; una ruta persistente USB suele facilitar esa revisión.

---

## 📊 Monitoreo y Verificación

### 1. Monitorear mensajes de radio recibidos (RX):
```bash
mosquitto_sub -t "meshcore/rx/#" -v
```

### 2. Enviar mensaje de prueba por radio (TX, opcional bajo demanda):
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

### Instalación en Windows (PowerShell)
`install.ps1` crea/reutiliza `.venv` con el intérprete `python`/`py` disponible y ejecuta pip mediante el Python de ese entorno. Pasa `--profile web` en la comprobación inicial y después de instalar: valida cuatro mínimos core y seis pins ASGI exactos, con independencia de `MESHCORE_PROFILE`. Una carpeta `paho` por sí sola no acredita el entorno. Un fallo de instalación/verificación termina con código distinto de cero:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# Instalación completa
.\install.ps1

# Solo instalar dependencias
.\install.ps1 -InstallDeps

# Ejecutar el bridge
.\install.ps1 -Run
```

### Modo de Simulación
La demo mantenida utiliza datos temporales, MQTT en memoria, adaptador virtual y puerto loopback asignado por el SO. Imprime la URL efectiva al arrancar y cierra recursos antes de eliminar los temporales. `install.ps1 -Simulate` invoca esta demo:
```bash
# Demo interactiva aislada con la malla virtual disponible
python run_interactive_demo.py
```

Los otros scripts históricos de simulación deben inspeccionarse antes de ejecutar: algunos publican MQTT o arrancan componentes con configuración de estación. No constituyen fixtures mantenidos de navegador.

### Mapas Offline
`MapTileService` sirve archivos XYZ desde `data/maps/tiles/{z}/{x}/{y}.ext` o archivos `.mbtiles` de `data/maps/`. MBTiles utiliza SQLite de sólo lectura para cartografía; no es una base de nodos ni de mensajes. Consulte `/api/map/status` y recargue el índice cuando añada mapas. No basta con activar `WEB_ENABLED`: hacen falta teselas locales y seleccionar el modo de mapa correspondiente en la UI.

### Datos y actualización

Guarde copia de `.env`, archivos JSON de `DATA_DIR`, mapas y logs antes de una actualización. Canales, nodos y airtime estimado usan JSON; las capturas `PacketBuffer` y deduplicación son RAM, y chat del navegador usa IndexedDB. El código actual no mantiene una cola MQTT durable en disco ni una base SQLite de mensajes.

`install.sh --update` prepara una copia independiente de los componentes de release y un entorno nuevo, instala/verifica dependencias y comprueba sintaxis antes de detener el servicio. Después cambia componentes con copias de retorno y conserva la unidad systemd anterior. Ante un fallo de cambio o arranque, restaura código/unidad e intenta arrancar el servicio previo si estaba activo. Si la recuperación falla, conserva el staging e informa su ruta para recuperación manual. `.env`, datos, mapas y logs quedan fuera de la sustitución; no se añaden variables ni se modifica Mosquitto durante update. La propiedad de archivos se ajusta a la identidad de servicio seleccionada.

Los renames son atómicos por componente, no una transacción atómica de todo el árbol; el servicio permanece detenido durante el cambio. Las copias permiten recuperación ante errores manejados/señales y rollback manual tras interrupciones del host; no se acredita supervivencia automática a pérdida de energía. Cuando origen y destino coinciden, se prepara igualmente una copia antes de reemplazar: el retorno recupera el estado al invocar el instalador, no el código anterior a un `git pull` externo. Tras mover el venv se regenera su configuración/activación sin reinstalar paquetes ni consultar red, se actualizan los shebangs de sus scripts al destino final y se comprueban de nuevo los imports/versiones mediante `venv/bin/python`.

Para una identidad distinta, establezca `MESHCORE_SERVICE_USER` explícitamente al invocar el instalador. `MESHCORE_SERIAL_GROUPS` permite indicar los grupos existentes del dispositivo. Verifique su propietario con `stat`/`ls -l`; el instalador no inventa grupos o permisos USB. La instalación manual debe conceder también acceso de lectura a `.env` y escritura a datos/logs.

### QA explícito en Linux

`sudo bash install.sh --dev` prepara `.venv` local, instala dependencias QA y Chromium y ejecuta el runner de pytest/cobertura, mypy, Ruff y documentación. Cualquier fallo de pip, Chromium o QA interrumpe el flujo; el mensaje final enumera únicamente esas comprobaciones. Bandit puede estar instalado como herramienta, pero no forma parte de ese runner y no se presenta como SAST aprobado. El modo `--dev` no instala paquetes globales ni reinicia el servicio de producción.

La [guía n8n](N8N_WORKFLOW_GUIDE.md) describe la programación existente cada seis horas y su zona horaria a configurar. Ejecutar el bridge real, activar el workflow, enviar un TX o sondear un repetidor puede afectar hardware/RF. La lectura o edición de documentación no ejecuta esas operaciones. Para nuevas automatizaciones, intervalos o cambios de radio, aplicar el checklist de `AGENTS.md` y acordar límites con el usuario.
