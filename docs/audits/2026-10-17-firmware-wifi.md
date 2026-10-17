# Configuración local WiFi Companion (MeshCore 1.18)

Fecha: 2026-10-17. Alcance: Capa 4 — configuración privada del WiFi Companion
local en Ajustes → Telemetría y Estado (`#tab-settings`), con contraseña
estrictamente write-only y cero emisión RF.

## 1. Contrato de Firmware Oficial (`reference/meshcore/` v1.18.0)

Fuente verificada en `examples/companion_radio/MyMesh.cpp`:
- Lecturas seguras:
  - `get wifi.ssid` → `> <ssid>`
  - `get wifi.enabled` → `> on` / `> off`
  - `get wifi.status` → `> connected` / `> disconnected` / `> disabled`
  - `get wifi.ip` → `> <ip>`
- Escrituras locales (`CMD_RUN_CLI_COMMAND = 66` → `RESP_CODE_CLI_REPLY = 29`):
  - `set wifi.ssid <ssid>` (1..32 bytes UTF-8, sin caracteres de control) → `> wifi.ssid is now ... (reboot needed to apply)`
  - `set wifi.pwd <password>` (1..63 bytes UTF-8, write-only, sin lectura permitida) → `> wifi.pwd updated (reboot needed to apply)`
  - `set wifi.enabled on|off` → `> wifi.enabled is now on|off (reboot needed to apply)`
  - `wifi.clear` → `> wifi config cleared (reboot needed to apply)`
- `get wifi.pwd` y `get wifi.password` permanecen estrictamente prohibidos en la
  allowlist de lectura y redactados en todos los logs.

## 2. Redacción de Secretos en SDK y Logs (`meshcore==2.3.15`)

El SDK `meshcore` emite trazas `logger.debug("Sending cli command: %s", cmd)` en
`meshcore/commands/device.py` y `logger.debug("sending pkt : %s", pkt)` en
`meshcore/tcp_cx.py`. Para impedir fugas de `wifi.pwd`:
1. `src/protocol_types.py` (`redact_command_str`) redacta líneas `Sending cli command: ...`
   y representaciones `sending pkt : b'...set wifi.pwd ...'`.
2. `src/serial/sdk_adapter.py` instala `_MeshcoreLogRedactionFilter` sobre el
   logger `meshcore` y devuelve comandos redactados en `_run_firmware_cli_command`.
3. `src/diagnostics.py` (`SystemLogHandler.emit`) aplica `redact_command_str` antes
   de almacenar o difundir logs por WebSocket.

## 3. Superficie Backend y Frontend

- **Adaptador (`MeshcoreSDKAdapter.set_firmware_wifi`)**:
  - Valida longitud UTF-8 y ausencia de controles ASCII (`< 0x20`, `0x7f`) antes de
    adquirir el lock SDK.
  - Ejecuta secuencialmente los subcomandos solicitados bajo una única adquisición
    de `_command_lock` y la misma generación de sesión (`_cli_session_generation`).
  - No realiza rollback automático si un paso intermedio es rechazado; reporta error
    privado `firmware_wifi_rejected` sin eco del secreto.
  - Devuelve `{ssid, password_updated, enabled, cleared, reboot_required: True, acknowledged: True, hardware_verified: False}`.
- **API Administrativa (`POST /api/admin`)**:
  - `{action: "set_wifi", scope: "firmware", ssid?, password?, enabled?, clear?}`.
  - Protegido por sesión/CSRF/Origin o API key administrativa. No publica en MQTT.
- **SPA (`src/web/static/js/modules/settings.js`, `index.html`, `i18n.js`)**:
  - Exige lectura manual previa de un getter `get wifi.*` en la sesión actual antes
    de habilitar `#firmwareWifiSave` y `#firmwareWifiClear`.
  - Limpia `#firmwareWifiPassword` inmediatamente al enviar o borrar.
  - Invalida la observación tras guardar, borrar, desconectar o cambiar `session_generation`.

## 4. Checklist de Impacto en la Malla LoRa

1. **Airtime**: 0 bytes RF (comunicación local UART/TCP con el Companion).
2. **Spam / bucles**: 0 publicaciones MQTT y 0 reintentos o lecturas automáticas.
3. **Timers**: 0 timers en memoria o persistidos.

## 5. Verificación Estática y Pruebas Escritas

- Pruebas escritas (pendientes de ejecución bajo orden explícita del usuario):
  `tests/test_firmware_wifi.py` y `tests/test_firmware_wifi_browser.py`.
- Verificación estática ejecutada: `ruff check`, `mypy --strict src`,
  `node scripts/build_frontend.cjs --check`, `node scripts/audit_frontend_i18n.cjs`,
  `scripts/validate_project_docs.py`.
