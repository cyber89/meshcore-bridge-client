# 📋 Reporte Colaborativo de Actividad Multi-Agente - MeshCore Bridge

Este documento es el registro central y compartido (Single Source of Truth) donde cada agente documenta sus intervenciones, módulos afectados, contratos de interfaz y estado de integración para que el **Agente Principal (Lead Orchestrator)** pueda conciliar la compatibilidad cruzada de todo el sistema.

---

## 🎯 Registro de Hitos y Tareas Recientes

### Hito: Simulación Integral Multi-Nodo, Verificación con Suites de Pruebas (120/120), Auditoría de Seguridad SAST/DAST y Limpieza de Código
- **Fecha**: 2026-08-20
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó el despliegue de una simulación completa de malla de 10 nodos cubriendo todos los roles oficiales de MeshCore (`CLIENT`, `REPEATER`, `SENSOR`, `ROOM`, `GATEWAY`) y todos los tipos de tramas de radio (`CHANNEL_MSG`, `DIRECT_MSG`, `ADVERT`, `TELEMETRY/Cayenne LPP`, `ACK/Receipt`, `TRACE_DATA`, `LOG_DATA/Sniffer`, `REPEATER_CMD/Response`, `DEVICE_INFO`, `TCP Companion`). Generó ficheros de logs estructurados (`logs/simulation_meshcore_full.log` y `logs/simulation_events.jsonl`), ejecutó las suites completas de pruebas unitarias/integración (120/120 superadas al 100%), depuró y limpió el código fuente con `ruff` y `mypy --strict` (0 errores en 23 módulos), y ejecutó una auditoría de seguridad SAST/DAST con Bandit (0 vulnerabilidades).
- **Contribuciones de Agentes**:
  1. **Agente 1 (Protocol & Firmware Investigator Agent)**:
     - Modeló los 10 nodos simulados con sus metadatos de hardware, capacidades de telemetría ambiental, canales de difusión y claves públicas en `src/virtual_mesh_adapter.py`.
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - Enriqueció `scripts/simulate_heltec_v4_mesh.py` con logging dual continuo a texto estructurado y eventos JSON Lines.
     - Añadió `get_contact` a `NodeRegistry` en `src/contact_manager.py` y `hop_count` a `PacketRecord`.
     - Depuró el despachador de comandos de repetidor en `src/admin_handler.py` y el enrutador en `src/rx_router.py`.
     - Fortaleció `src/store_forward.py` y `src/rate_limiter.py` bajo condiciones de alta carga y concurrencia.
  3. **Agente 3 (Protocol QA & Fuzzing Agent)**:
     - Ejecutó la suite completa de 120 pruebas unitarias y de integración (`pytest tests/`), logrando 100% de aprobados en concurrencia, serial watchdog, store & forward SQLite WAL, rate limiter, HA discovery, matriz n8n y enrutamiento RF.
     - Resolvió el fixture de disponibilidad para pruebas E2E de Playwright.
  4. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - Validó la semántica HTML5, sistema de tokens de diseño CSS3 (variables HSL, contraste WCAG 2.2 AA >= 4.5:1, tipografía fluida y scrollbars estilizadas) y la lógica cliente asíncrona en `src/web/static/`.
  5. **Agente 5 (Security & Vulnerability Auditor Agent)**:
     - Ejecutó la auditoría de seguridad SAST con Bandit y scripts especializados (`.agents/skills/security-code-auditor/scripts/run_security_audit.py`).
     - Verificó 100% de consultas SQL parametrizadas, aislamiento estricto de rutas canónicas contra Directory Traversal, sanitización XSS con `escapeHtml` y cabeceras HTTP defensivas.
  6. **Agente 0 (Lead Orchestrator)**:
     - Verificación estática con `ruff check src tests` (0 errores).
     - Verificación estricta de tipos con `mypy --strict src` (0 errores en 23 módulos).
     - Sincronización del paquete autónomo en `/deploy/` (`python scripts/sync_deploy.py`).
     - Sincronización con repositorio remoto (`git push origin main`).

### Hito: Medición RF de Ping y Ping Zero con RTT, SNR There, SNR Back y RSSI
- **Fecha**: 2026-08-19
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Diagnosticó e implementó la captura y medición en tiempo real de pings y ecos de radio directos (Ping Zero y Ping multi-nodo). Resolvió la causa por la cual RSSI aparecía como `-- dBm` y la latencia no reflejaba la respuesta de radio del nodo remoto, formateando la respuesta idéntica a la aplicación oficial de MeshCore: `"Duration en ms, SNR there, SNR back (RSSI en dBm)"`.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/admin_handler.py`**:
       - Añadió el sistema de promesas asíncronas `_ping_waiters` en `AdminCommandHandler` y el método `notify_ping_response` para capturar la respuesta del nodo remoto.
       - En `handle` para `action in ("ping_zero", "ping_0", "ping", "zero_hop_ping")`, envía la sonda RF, espera la respuesta del transceptor con timeout controlado, calcula la duración real de ida y vuelta (`duration_ms`), y extrae `snr_there` (SNR medido en el nodo remoto), `snr_back` (SNR medido en el transceptor local) y `rssi` (en dBm).
       - Actualiza inmediatamente el registro de nodos `node_registry.record_packet` con las métricas RF obtenidas.
     - **`src/rx_router.py`**:
       - Añadió `admin_handler` a `RxRouterContext`.
       - En `handle_event`, intercepta paquetes `ACK`, `TRACE_DATA` y respuestas de comandos de repetidor (`repeater_response`), notificando a `admin_handler.notify_ping_response` con `trip_time`, `snr_there`, `snr_back` y `rssi`.
       - Propaga `rssi` y `snr` en el evento `message_delivered`.
     - **`src/bridge_core.py`**:
       - Conectó `self.admin_handler` con `self.rx_router._ctx.admin_handler`.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - En `pingZero`, extrae `duration_ms` / `rtt_ms`, `snr_there`, `snr_back` y `rssi`.
       - Formatea la salida de terminal idéntica a MeshCore oficial: `✓ [PONG DIRECTO] Duration: ${rtt} ms | SNR there: ${snrThere} | SNR back: ${snrBack} | RSSI: ${rssi}`.
       - Actualiza el Toast, la píldora de resultado rápido (`repQuickPingResult`) y la insignia del modal (`adminModalPingZeroBadge`).
       - Actualiza inmediatamente las métricas en `this.knownNodes` y llama a `updateNodeInDom` para refrescar los chips de RF y estado del nodo en la interfaz.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - Verificación de sintaxis JS (`node -c`, código 0).
     - Verificación de sintaxis y tipos Python (`python -m compileall`, código 0).
     - Sincronización completa de paquete autónomo de despliegue (`python scripts/sync_deploy.py`).
     - Sincronización con repositorio remoto (`git push origin main`).

### Hito: Actualización Reactiva de Estado de Actividad de Nodos (En Línea / Inactivo)
- **Fecha**: 2026-08-19
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Diagnosticó y corrigió el flujo por el cual un nodo remoto con el que se interactúa o del que se recibe un mensaje permanecía erróneamente con estado visual "Inactivo" / "Fuera de línea".
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/rx_router.py`**:
       - En `handle_event`, registra los paquetes de recepción con `node_registry.record_packet` para nodos remotos y emite el evento WebSocket `contact_updated` (o `contact_discovered` para nuevos) conteniendo la información actualizada del contacto (`last_seen`, `last_rssi`, `last_snr`, `hops`), permitiendo que el cliente web reciba la señal de vivacidad en tiempo real.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - Implementó `updateNodeInDom(pubkey, node)` para conmutar inmediatamente el chip de estado a `🟢 En Línea` (`status-online`), actualizar métricas de RF (`RSSI`, `SNR`, `Saltos`) y remover `.node-card-offline` en el DOM sin necesidad de recargar la página.
       - En `handleIncomingLiveEvent`, actualiza `last_seen` en `this.knownNodes` e invoca `updateNodeInDom` al recibir mensajes ordinarios (DM o canal), confirmaciones de entrega de radio (`message_delivered` para el destinatario) y eventos de actualización (`contact_updated` / `contact_discovered`).
       - Robusteció el cálculo y normalización de `last_seen` en `renderNodesDirectory` para soportar marcas de tiempo en segundos, milisegundos y formatos de fecha ISO.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - Verificación estática con `node -c src/web/static/js/app.js` (código 0).
     - Verificación de compilación Python con `python -m compileall src` (código 0).
     - Sincronización de `/deploy/` y paquetes comprimidos vía `python scripts/sync_deploy.py`.
     - Sincronización con el repositorio remoto GitHub (`origin/main`).

### Hito: Validación y Confirmación de Entrega de Mensajes E2E (Doble Palomilla `✓✓ TX`)
- **Fecha**: 2026-08-19
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Diagnosticó e implementó la cadena completa de confirmación de entrega de mensajes (Delivery Receipts). Resolvió la causa raíz por la cual los mensajes transmitidos permanecían indefinidamente en una sola palomilla (`✓ TX`), conectando el código de ACK de 4 bytes de la radio con el ID del mensaje, persistiendo la confirmación en SQLite WAL e IndexedDB, y actualizando la interfaz reactivamente a doble palomilla (`✓✓ TX`).
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/store_forward.py`**:
       - Añadió la columna `expected_ack TEXT` e índice `idx_receipts_expected_ack` a la tabla `message_receipts` de SQLite.
       - Actualizó `record_outbound_message` para registrar el código de ACK esperado junto al `msg_id` y `recipient`.
       - Implementó `get_msg_id_by_expected_ack(expected_ack)` para resolver instantáneamente el ID del mensaje a partir del código recibido por radio.
     - **`src/serial_driver.py`**:
       - En `PySerialAsyncioAdapter.send_message`, extrajo el `expected_ack` (código hexadecimal de 4 bytes) generado por el firmware en el evento `MSG_SENT` y lo retornó en el resultado.
     - **`src/bridge_core.py`**:
       - En `_execute_tx`, capturó `expected_ack` y registró el mensaje saliente en `store_forward.record_outbound_message`.
       - Incluyó `expected_ack` en la respuesta JSON devuelta a la API REST y en el tópico MQTT `meshcore/tx/status`.
     - **`src/rx_router.py`**:
       - En `handle_event`, intercepta los eventos `EventType.ACK` / `PacketType.ACK` extrayendo `ack_code` y `trip_time`.
       - Resuelve el `msg_id` correspondiente consultando `store_forward.get_msg_id_by_expected_ack(ack_code)`.
       - Marca el mensaje como entregado en SQLite (`mark_message_delivered`) y emite el evento `message_delivered` a WebSocket y MQTT con `msg_id`, `ack_code`, `trip_time_ms` y `status: "delivered"`.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - En `MeshCoreStorage`, actualizó `saveMessage` y añadió `updateMessageDelivery` para persistir el estado `delivered: true`, `expected_ack` y `trip_time_ms` en `IndexedDB`.
       - En `initChat`, genera un `msgId` único (`msg_...`), lo envía en `POST /api/tx` como `request_id`, captura el `expected_ack` de retorno y lo asocia como `data-ack-code` en la burbuja del DOM.
       - En `handleIncomingLiveEvent`, el manejador de `message_delivered` localiza la burbuja por `data-msg-id` o `data-ack-code`, conmuta a `✓✓ TX`, actualiza el tooltip con la latencia RTT y persiste el estado en `this.channelFeeds` e IndexedDB.
       - En `appendChatMessage`, asigna los atributos `data-msg-id` y `data-ack-code`, renderizando `✓✓ TX` cuando `msg.delivered` es verdadero.
     - **`src/web/static/css/app.css`**:
       - Diseñó micro-animación `@keyframes ackPop` y estilos destacados para `.msg-ack-status.delivered` (verde esmeralda con resplandor) y `.msg-ack-status.sent`.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - Verificación estática con `node -c src/web/static/js/app.js` (código 0, sin errores).
     - Verificación de compilación Python con `python -m compileall src` (código 0, sin errores).
     - Sincronización del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `python scripts/sync_deploy.py`.
     - Sincronización de commits con el repositorio GitHub (`origin/main`).
- **Fecha**: 2026-08-19
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó la resolución integral de las 8 solicitudes de usuario relacionadas con fallas responsive en CSS, renderizado de logs, consolidación de telemetría por USB en Ajustes, eliminación de métricas obsoletas en el Sniffer RF, filtrado de DMs de repetidores, centrado interactivo del mapa geográfico, soporte de anuncios Advert estilo iOS (Hop 0, Flood Routed, Clipboard) y enriquecimiento del Directorio de Nodos.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/admin_handler.py`**:
       - Amplió `get_local_config()` y `fetch_device_config()` para consolidar telemetría en tiempo real del transceptor conectado por USB (`battery_pct`, `voltage`, `battery_mv`, `power_source`, reloj RTC, contadores del microcontrolador y estadísticas de radio).
       - Implementó `broadcast_advert(flood: bool)` para emisión por radio de anuncios en modo vecindario (Hop 0 / `flood=False`) o propagación multi-salto (Flood Routed / `flood=True`).
     - **`src/web/api_router.py`**:
       - Enriqueció el endpoint `GET /api/node/config` consolidando métricas calculadas en vivo del bridge (`uptime`, `uptime_str`, `airtime_ms`, `duty_cycle_pct`, contadores de paquetes `tx_count`, `rx_count`, `duplicate_packets`, `packet_errors`, `noise_floor_dbm`, `clock`).
       - Implementó el endpoint `POST /api/node/advert` recibiendo el flag `flood`.
     - **`src/rx_router.py`**:
       - En `_handle_mesh_direct_msg`, detecta si el emisor es un repetidor o si el texto es una respuesta de comando (`"unknown command"`, `"cmd "`, `"login "`, etc.), despachándolo como evento de telemetría/control a MQTT y WebSocket (`event_type: "repeater_response"`), evitando que se inyecte erróneamente como mensaje directo de chat de usuario en la barra lateral.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/css/app.css`**:
       - Corrigió la regla responsive en `@media (max-width: 900px)`, reemplazando `.app-container` por `.app-body { flex-direction: column; overflow: hidden; }` para que la barra lateral y el contenido principal se adapten fluidamente a pantallas pequeñas sin comprimirse.
       - Añadió reglas para compactar el header en pantallas `<= 768px` y hacer los grids de nodos y filtros responsive de 1 columna en pantallas `<= 600px`.
     - **`src/web/static/index.html`**:
       - Eliminó el texto `"Sincronización en Tiempo Real"` del encabezado de Nodos manteniendo el indicador de pulso.
       - Removió la tarjeta de `"Calidad Señal Promedio"` (`#snifferAvgRssi`) del Sniffer RF.
       - Removió los botones `#btnCopyAIDiag` y `#btnExportDiag` de la barra de acciones de logs.
       - Añadió las 3 acciones de hardware para Anuncios de Presencia estilo iOS: `Advert Hop (0 Saltos / Vecindario)`, `Advert Flood Routed (Toda la Malla)` y `Advert Clipboard (Copiar URI)`.
     - **`src/web/static/js/app.js`**:
       - Corrigió el error crítico en `createLogElement(log)` para retornar `row`, restableciendo el renderizado fluido de la Consola de Logs.
       - Removió referencias a `#snifferAvgRssi`, `#btnCopyAIDiag` y `#btnExportDiag`.
       - Enlazó la telemetría en tiempo real en `fetchLocalNodeConfig()`, poblando los 8 bloques de Ajustes (batería, voltaje, alimentación USB, reloj RTC, uptime, airtime, señal RF, piso de ruido y contadores TX/RX/dup/err).
       - Implementó `sendAdvert(flood)` y `copyAdvertToClipboard()`, enlazando botones de hardware y command palette (`action-advert-hop`, `action-advert-flood`, `action-advert-clipboard`).
       - Enriqueció las tarjetas de nodos con métricas detalladas (`Last RSSI`, `Last SNR`, `Noise Floor`, `Uptime`) y botón interactivo `🗺️ Mapa`.
       - Implementó `focusNodeOnMap(pubkey)` para centrar el mapa suavemente con `map.flyTo`, resaltar el marcador en rojo y abrir el popup.
       - Corrigió el cálculo de contadores en las píldoras de filtro en `renderNodesDirectory()`.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - Verificación estática con `node -c src/web/static/js/app.js` (código 0, sin errores de sintaxis).
     - Verificación de compilación de código Python con `python -m compileall src` (código 0, sin errores).
     - Sincronización del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `python scripts/sync_deploy.py`.
     - Actualización y sincronización de commits con el repositorio remoto GitHub (`origin/main`).
- **Fecha**: 2026-08-19
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Diseñó e integró la capacidad de realizar **Ping Zero** (sonda de 0 saltos directos sin saturar la malla) contra nodos y repetidores, calculando la latencia de ida y vuelta (RTT en ms), potencia de señal RSSI (dBm), relación señal-ruido SNR (dB) y estado de alcance en línea de vista.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/repeater_manager.py`**: Añadió soporte de normalización para comandos `ping 0`, `ping_zero`, `ping` y `trace 0`.
     - **`src/admin_handler.py`**: Implementó el manejador especializado de `ping_zero`, midiendo con alta precisión (`time.perf_counter()`) la latencia RTT, consultando las métricas de RF del registro de nodos y publicando el evento en MQTT (`meshcore/admin/repeater/{target}/ping_zero`).
     - **`src/web/api_router.py`**: Expuso los endpoints REST `POST /api/repeater/ping_zero` y `POST /api/node/ping_zero`.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/index.html`**:
       - Añadió botón y badge de **Ping Zero (0 Hops)** en el encabezado del Modal de Administración de Repetidores (`#repeaterAdminModal`).
       - Añadió tarjeta de acción dedicada a Ping Zero en la pestaña de Acciones Rápidas (`#rep-quick`).
       - Integró el comando interactivo `ping 0` en los botones rápidos de la terminal y en la guía de ayuda (`#terminalHelpDrawer`).
     - **`src/web/static/js/app.js`**:
       - Implementó `pingZero(targetNode, targetName)` con feedback visual en tiempo real, salida en terminal interactiva, actualización de badges y toasts.
       - Añadió botones `🎯 Ping 0` directamente en las tarjetas de repetidores y clientes en el Directorio de Nodos.
     - **`src/web/static/css/app.css`**:
       - Diseñó estilos para `.ping-zero-badge`, `.btn-modal-ping-zero`, `.btn-node-ping-zero`, `.stat-pill-ping` y animación de pulso `@keyframes pingPulse`.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - Verificación estática con `node -c` y `lint_frontend_standards.py` (100% aprobado).
     - Verificación de arquitectura y concurrencia (`audit_architecture.py`, `audit_async_concurrency.py`).
     - Sincronización del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `python scripts/sync_deploy.py`.
     - Sincronización completa con GitHub (`origin/main`).

---

### Hito: Corrección de Sintaxis de Bash (`!grep`) y Soporte TCP Companion en `install.sh`
- **Fecha**: 2026-08-19
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Corrigió el error de sintaxis en `install.sh` (`!grep` sin espacio) que provocaba el fallo `!grep: command not found` durante la actualización del software, e integró la migración automática de variables de entorno del servidor TCP Companion (`TCP_SERVER_ENABLED`, `TCP_SERVER_HOST`, `TCP_SERVER_PORT`).
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - Corrigió la evaluación condicional en [`install.sh`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/install.sh) a `if ! grep -q ...`.
     - Añadió la sección de auto-inyección de variables para `TCP_SERVER_ENABLED` en `.env` existentes.
  2. **Agente 0 (Agente Principal / Orchestrator)**:
     - Sincronización del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `python scripts/sync_deploy.py`.
     - Sincronización completa con GitHub (`origin/main`).

---

### Hito: Corrección de Excepción de Inicialización (TypeError) y Blindaje de Elementos DOM en la SPA
- **Fecha**: 2026-08-19
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Diagnosticó y corrigió la interrupción en la carga de la SPA provocada por referencias nulas a elementos de diagnóstico/discovery en `initPreflight()` e `initHomeAssistant()`.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - Blindó con comprobaciones de nulidad (*null checks*) estrictas todos los escuchadores de eventos en [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js) (`initPreflight`, `initHomeAssistant`, `initTheme`, `initCommandPalette`, `initChat`).
     - Restauró el ciclo de vida completo de la aplicación, permitiendo que `initChat()`, `initWebSocket()`, `initLeafletMap()` y `fetchInitialData()` se ejecuten de manera fluida y sin bloqueos.
     - Restableció la carga automática y continua de nodos de la malla, repetidores y libreta de contactos.
  2. **Agente 0 (Agente Principal / Orchestrator)**:
     - Verificación con `node -c src/web/static/js/app.js` y `lint_frontend_standards.py`.
     - Sincronización del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `python scripts/sync_deploy.py`.

---

### Hito: Implementación de Persistencia IndexedDB y Mapas Geográficos Offline con Modo Radar Táctico en la SPA
- **Fecha**: 2026-08-19
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó la implementación de la capa de almacenamiento en navegador (`MeshCoreStorage`) con IndexedDB y el sistema integral de capas cartográficas offline y radar táctico para situaciones de emergencia sin conexión a Internet.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **Capa de Almacenamiento IndexedDB (`app.js`)**:
       - Implementó `MeshCoreStorage` gestionando la base de datos `MeshCoreStationDB` con los object stores `chat_messages`, `sniffer_packets` y `app_settings`.
       - Persistencia automática de mensajes de chat salientes y entrantes por canal y DM, cargando el historial previo de forma asíncrona al iniciar o cambiar de conversación.
       - Persistencia de tramas interceptadas por el sniffer RF con recarga inmediata en el arranque y limpieza coordinada.
     - **Mapas Offline & Modo Radar Táctico (`app.js`, `app.css`, `index.html`)**:
       - Añadió barra de herramientas de capas cartográficas (`.map-layer-switcher`) con soporte para *CartoDB Dark*, *OpenStreetMap*, *Teselas Locales* y *Radar Táctico*.
       - Implementó el **Modo Radar Táctico / Grícula LoRa**: visualización geoespacial sin dependencia de internet con anillos concéntricos de alcance (1 km, 5 km, 10 km, 25 km), grícula de coordenadas y ejes cardinales centrados en el nodo local.
       - Detección y conmutación automática (*fallback*) a Radar Táctico ante fallos de conexión a teselas online (`tileerror`).
       - Añadió panel de gestión en Ajustes (`#local-storage-maps`) para vaciar IndexedDB y configurar la URL del servidor de teselas locales (`localTileUrl`).
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - **Telemetría TCP Companion en REST API (`src/web/api_router.py`)**:
       - Expuso el objeto `tcp_companion` (estado `enabled`, `host`, `port`, `connected_clients`) en el endpoint `/api/status`.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - Validación con `node -c src/web/static/js/app.js` (0 errores).
     - Verificación con `lint_frontend_standards.py`, `audit_architecture.py` y `audit_async_concurrency.py` (100% de cumplimiento).
     - Sincronización del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `python scripts/sync_deploy.py`.

---

### Hito: Incorporación de Skills de Ingeniería de Software, Arquitectura Hexagonal, Patrones GoF y Concurrencia Async
- **Fecha**: 2026-08-19
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Incorporó un conjunto integral de 4 nuevas skills técnicas especializadas con herramientas de análisis estático para blindar la arquitectura, patrones de diseño, concurrencia asíncrona y métricas de código limpio.
- **Nuevas Skills Incorporadas**:
  1. **`software-architecture-patterns`** ([`SKILL.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.agents/skills/software-architecture-patterns/SKILL.md)):
     - Guía de Arquitectura Hexagonal (Ports & Adapters), Event-Driven Architecture (EDA), Domain-Driven Design (DDD) y patrones de resiliencia (Circuit Breaker, Exponential Backoff, Bulkhead).
     - Herramienta: `scripts/audit_architecture.py` (auditoría de inversión de dependencias e inmutabilidad del dominio).
  2. **`gof-design-patterns-expert`** ([`SKILL.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.agents/skills/gof-design-patterns-expert/SKILL.md)):
     - Catálogo formal de patrones GoF (Adapter, Factory Method, Strategy, Facade, Observer, State Machine).
     - Herramienta: `scripts/analyze_design_patterns.py` (mapeo y detección de patrones en el código de producción).
  3. **`async-concurrency-engineering`** ([`SKILL.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.agents/skills/async-concurrency-engineering/SKILL.md)):
     - Directrices para evitar llamadas bloqueantes en el event loop, puente seguro entre hilos/asyncio y graceful shutdown.
     - Herramienta: `scripts/audit_async_concurrency.py` (detección de bloqueos I/O y patrones inseguros).
  4. **`refactoring-clean-architecture`** ([`SKILL.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.agents/skills/refactoring-clean-architecture/SKILL.md)):
     - Técnicas de refactorización de Martin Fowler y umbrales de métricas (Complejidad Ciclomática $\le 15$, longitud de métodos $\le 45$, parámetros $\le 6$).
     - Herramienta: `scripts/evaluate_refactoring_metrics.py` (cálculo de complejidad ciclomática de McCabe por función).

---

### Hito: Normalización Integral de Componentes UI, Optimización de Memoria (RAM), Renderizado por Lotes y Sanitización XSS en Frontend
- **Fecha**: 2026-08-18
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó la normalización estética de todos los componentes visuales de la aplicación, la poda de duplicidad en CSS, el blindaje estricto de sanitización contra XSS y la optimización de rendimiento y huella de memoria RAM en el navegador.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **Normalización de Componentes (`app.css`)**: Estandarizó el sistema de tarjetas (`.card`, `.node-card`, `.contact-item-card`, `.settings-card`, `.ha-status-card`, `.repeater-card`, `.quick-diag-card`) bajo una escala armónica de radios (`var(--radius-md)` = 10px), paddings y sombras unificadas.
     - **Limpieza y Poda CSS**: Consolidó selectores duplicados de modales (`.modal-card`, `.modal-overlay`), eliminó estilos inline en [`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html) y redujo el peso del stylesheet.
     - **Optimización de Rendimiento DOM (`app.js`)**:
       - Implementó renderizado por lotes mediante `DocumentFragment` en `renderNodesDirectory()`, `renderFilteredLogs()` y `renderAnalytics()`, reduciendo *layout reflows* a una única mutación de pintura instantánea (< 5ms).
       - Aplicó *debouncing* (`debounce(fn, 150)`) en todos los campos de búsqueda en vivo (`nodesSearchInput`, `contactsSearchInput`, `snifferSearch`, `logSearchInput`).
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - **Gestión Estricta de Memoria (RAM Bounded Queues)**:
       - Limitó el ring-buffer de paquetes sniffer (`rawPackets`) a un máximo de 200 tramas y podó los nodos DOM excedentes en tiempo real con `removeChild`.
       - Limitó el buffer de logs del sistema (`systemLogs`) a 300 entradas con poda automática de elementos en el DOM.
       - Acotó el historial por canal y mensaje directo (`channelFeeds`) a un tope de 100 mensajes por conversación para evitar retención indefinida de memoria.
  3. **Agente 5 (Security & Vulnerability Auditor Agent)**:
     - Blindó al 100% las interpolaciones de texto y atributos en la interfaz con `escapeHtml()` en todos los renderizadores de nodos, mensajes, claves públicas, paquetes y logs.
  4. **Agente 0 (Agente Principal / Orchestrator)**:
     - Verificación estática con `node -c src/web/static/js/app.js` (0 errores de sintaxis).
     - Validación con `lint_frontend_standards.py` (100% de cumplimiento en estándares HTML5 semántico, CSS3 y ES6+).
     - Sincronización del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `python scripts/sync_deploy.py`.

---

### Hito: Implementación del Servidor TCP/IP Companion en Puerto 5000 para Apps Oficiales MeshCore
- **Fecha**: 2026-08-18
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó la investigación del protocolo en firmware oficial C++ y SDK Python, diseñó el servidor TCP asíncrono en puerto 5000 y armonizó los adaptadores de radio y el simulador virtual.
- **Contribuciones de Agentes**:
  1. **Agente 1 (Protocol & Firmware Investigator Agent)**:
     - Analizó el firmware [`SerialWifiInterface.cpp`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/reference/meshcore/src/helpers/esp32/SerialWifiInterface.cpp) y el SDK [`tcp_cx.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/reference/meshcore_py/src/meshcore/tcp_cx.py).
     - Formalizó la especificación del framing binario oficial (`0x3C`/`0x3E` + longitud little-endian uint16 + payload) en [`docs/PROTOCOL_SPEC.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/PROTOCOL_SPEC.md).
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - Implementó [`src/tcp_companion_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/tcp_companion_server.py): Servidor `asyncio` no bloqueante con de-framing continuo, soporte multi-cliente y protección DoS (`MAX_FRAME_SIZE = 512`).
     - Añadió variables de configuración en [`config.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/config.py) y [`.env.example`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.env.example) (`TCP_SERVER_ENABLED`, `TCP_SERVER_HOST`, `TCP_SERVER_PORT=5000`).
     - Integró callbacks de tramas crudas (`set_companion_rx_callback` y `send_raw_companion_frame`) en [`src/serial_driver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial_driver.py) y emulación completa en [`src/virtual_mesh_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/virtual_mesh_adapter.py).
     - Integró el ciclo de vida en [`src/bridge_core.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/bridge_core.py) y diagnósticos en [`src/preflight.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/preflight.py).
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - Concilió la arquitectura en [`docs/ARCHITECTURE.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/ARCHITECTURE.md).
     - Ejecutó la sincronización de producción en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `python scripts/sync_deploy.py`.

---

### Hito: Sanitización Integral de Persistencia SQLite, Resolución de Deadlocks, Suite Completa de Pruebas y Deploy
- **Fecha**: 2026-08-18
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó la resolución de deadlocks por concurrencia multihilo en persistencia SQLite, saneamiento de contadores de tráfico RX, robustez de tipos en API REST, ejecución completa de las suites de pruebas (120/120 superadas), auditoría SAST de seguridad y re-sincronización del paquete de despliegue.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - Reemplazó `asyncio.Lock` por sincronización multihilo `threading.Lock` en [`src/store_forward.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/store_forward.py), eliminando por completo los bloqueos en llamadas concurrentes `asyncio.run()` provenientes de múltiples hilos del SO.
     - Eliminó el doble incremento de `rx_count` en [`src/bridge_core.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/bridge_core.py), delegando la autoría única de métricas en `RxEventRouter` ([`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py)).
     - Añadió alias `shutdown()` en `MeshCoreBridge`.
     - Blindó la extracción de métricas numéricas y cálculo de tasa de error en `_route_status` ([`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py)).
  2. **Agente 3 (Protocol QA & Fuzzing Agent)**:
     - Ajustó temporización del Watchdog en [`tests/test_serial_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/tests/test_serial_adapter.py) y mock de métricas en [`tests/test_web_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/tests/test_web_server.py).
     - Ejecutó la suite completa de 120 pruebas unitarias, de concurrencia, estrés, fuzzing e integración con un resultado de **120/120 PASSED (100% de éxito)**.
  3. **Agente 5 (Security & Vulnerability Auditor Agent)**:
     - Ejecutó auditoría estática SAST completa (`run_security_audit.py`): Cero vulnerabilidades encontradas (Bandit SAST limpio, 100% SQL parametrizado, Directory Traversal aislado, XSS escapado).
  4. **Agente 0 (Agente Principal / Orchestrator)**:
     - Verificó con `mypy --strict src/` (0 errores en 22 módulos) y `ruff check` (0 errores).
     - Empaquetó y sincronizó el release en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `python scripts/sync_deploy.py`.

---

### Hito: Sincronización Automática en Tiempo Real y Detección de Estado Offline (TTL)
- **Fecha**: 2026-08-18
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Diseñó el sistema de auto-descubrimiento reactivo en tiempo real para la vista **🌐 Nodos** y la lógica de detección de apagado/offline para nodos de radiofrecuencia LoRa MeshCore.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **Auto-descubrimiento Reactivo**: Reemplazo del botón manual de actualización por un indicador de pulso `🟢 Sincronización en Tiempo Real` (`.live-sync-indicator`). Los nuevos nodos o actualizaciones de telemetría/anuncios se integran dinámicamente vía WebSocket sin refresco manual.
     - **Detección y Visualización Offline**: Incorporación de chips de conectividad (`🟢 En Línea` < 30min, `🟡 Inactivo` 30m-2h, `🔴 Fuera de línea` > 2h) calculados sobre la marca de tiempo `last_seen`. Los nodos apagados o fuera de cobertura se atenúan visualmente (`.node-card-offline`) conservando su telemetría y última posición GPS.
  2. **Agente 0 (Agente Principal / Orchestrator)**:
     - Verificación estática con `node --check`, `ruff check` y `mypy --strict` (0 errores).
     - Sincronización a [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `sync_deploy.py`.

---

### Hito: Rediseño y Separación Clara entre Mensajería (DMs Activos) y Libreta de Contactos
- **Fecha**: 2026-08-18
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó la reestructuración de la interfaz para separar de forma limpia la bandeja de conversaciones activas de la libreta general de contactos del dispositivo.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX Architect Agent)**:
     - **Mensajería (`#tab-chat`)**: En la barra lateral, la sección «Mensajes Directos» ahora muestra **exclusivamente las conversaciones que cuentan con al menos un mensaje enviado o recibido**, evitando saturar la lista de chats con nodos sin interacción.
     - **Libreta de Contactos (`#tab-contacts`)**: Pestaña principal que lista **única y exclusivamente los contactos con rol `CLIENT` (o `CHAT`)**, con tarjetas perfectamente uniformadas (`height: 100%`, flexbox stretch y micro-grid 3 columnas de telemetría sin saltos de línea irregulares):
       - `💬 DM`: Abre inmediatamente la conversación privada en la vista de Mensajería.
       - `📤 QR`: Abre el modal con código QR con renderizado estilizado (ojos redondeados y gradiente cian) y distribución de 2 columnas sin scroll.
       - `🗑️ Eliminar`: Botón compacto y estilizado para borrar el contacto.
       - `🔍 Buscador`: Filtrado en tiempo real por nombre, alias, rol o clave pública.
       - `➕ Agregar Contacto`: Botón directo en la cabecera para añadir nuevos contactos.
     - **Mensajes Directos**: Validación estricta que impide abrir o agregar chats DM con nodos que no sean de tipo `CLIENT`.
     - Eliminada la pestaña redundante «Directorio», dejando una navegación optimizada y jerárquica.
  2. **Agente 0 (Agente Principal / Orchestrator)**:
     - Verificación estática con `node --check`, `ruff check` y `mypy --strict` (0 errores).
     - Sincronización del release en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `sync_deploy.py`.

---
- **Fecha**: 2026-08-18
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó la revisión integral de compatibilidad de tipos, sanitización de datos y optimización de rendimiento entre el backend asíncrono y la interfaz web SPA.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - Enriqueció el enrutador de recepción ([`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py)) para mapear automáticamente roles oficiales MeshCore (`REPEATER`, `ROOM`, `SENSOR`, `CLIENT`) y coordenadas GPS (`latitude`, `longitude`) en el directorio de nodos.
     - Optimizó el gestor de contactos ([`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py)) para normalizar campos de posición y telemetría de forma resiliente ante múltiples formatos de entrada (`gps`, `lat`, `latitude`).
     - Alineó los nodos del adaptador virtual ([`src/virtual_mesh_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/virtual_mesh_adapter.py)) con los 4 roles oficiales del firmware MeshCore.
  2. **Agente 4 (Web UI/UX Architect Agent)**:
     - Mejoró el generador de URIs y códigos QR en [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js) para incluir el parámetro `role` al exportar contactos.
     - Robusteció el parser de importación URI `meshcore://contact?...` para registrar el rol y actualizar el directorio en vivo.
     - Sustituyó llamadas bloqueantes `alert()` por el sistema nativo de notificaciones `showToast()`.
  3. **Agente 5 (Security & Vulnerability Auditor Agent)**:
     - Verificó con SAST/DAST (`security-code-auditor`) la ausencia total de inyecciones SQL, aislamiento estricto de Directory Traversal y sanitización XSS contextual (`escapeHtml`).
  4. **Agente 0 (Agente Principal / Orchestrator)**:
     - Ejecutó análisis estático estricto: `mypy --strict src/` (0 errores en 22 archivos), `ruff check` (0 errores) y `node --check` (0 errores de sintaxis JS).
     - Sincronizó y empaquetó el release en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/).

---
- **Fecha**: 2026-08-18
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Invocó al Agente Investigador para compilar y armonizar la documentación técnica oficial de MeshCore ([docs.meshcore.io](https://docs.meshcore.io/) y [github.com/meshcore-dev/MeshCore](https://github.com/meshcore-dev/MeshCore)) con los fuentes binarios C/C++ y SDKs de referencia.
- **Contribuciones de Agentes**:
  1. **Agente 1 (Protocol & Firmware Investigator Agent)**:
     - Realizó una investigación integral de las fuentes oficiales de MeshCore ([docs.meshcore.io](https://docs.meshcore.io/), [github.com/meshcore-dev](https://github.com/meshcore-dev)).
     - Ejecutó la skill `meshcore_source_inspector` sobre los headers C/C++ (`Packet.h`, `AdvertDataHelpers.h`, `ClientACL.h`, `RoutingPolicy.h`, `RadioLibWrappers.h`) y módulos de Python (`packets.py`, `reader.py`, `contact.py`, `messaging.py`).
     - Redactó la versión 3.0.0 de [`docs/PROTOCOL_SPEC.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/PROTOCOL_SPEC.md), detallando:
       - Framing determinista con Byte Stuffing (`0xAA`, `0x55`, `0x1B`, `0x20`).
       - Algoritmo de verificación CRC-16-CCITT ($0x1021$).
       - Roles oficiales MeshCore (`ADV_TYPE_CHAT=1`, `REPEATER=2`, `ROOM=3`, `SENSOR=4`).
       - Formato binario de la tarjeta de contacto (147 bytes estructurados).
       - Estructura de 8 canales LoRa (Canal 0 abierto, Canales 1-7 AES-128 PSK).
       - Catálogo completo de comandos host (`0x01` a `0x3A`) y notificaciones push (`0x80` a `0x8A`).
       - Especificación de telemetría ambiental CayenneLPP y matrices de tópicos MQTT / n8n.
     - Actualizó [`src/protocol_types.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/protocol_types.py) con nuevos modelos de hardware reconocidos (`HardwareModel`).
  2. **Agente 0 (Agente Principal / Orchestrator)**:
     - Realizó verificación estática con `mypy --strict src/` (0 errores) y `ruff check`.
     - Sincronizó los artefactos y documentación en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vía `sync_deploy.py`.

---
- **Fecha**: 2026-08-18
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó la comprobación formal de la especificación de tipos MeshCore y la integración del borrado interactivo en UI y hardware.
- **Contribuciones de Agentes**:
  1. **Agente 1 (Protocol & Firmware Investigator Agent)**:
     - Verificó en el firmware oficial (`AdvertDataHelpers.h`) la definición estricta de roles/tipos de anuncio: `ADV_TYPE_CHAT = 1` (Chat/Companion), `ADV_TYPE_REPEATER = 2` (Repetidor/Router), `ADV_TYPE_ROOM = 3` (Servidor de Sala) y `ADV_TYPE_SENSOR = 4` (Sensor de Telemetría).
     - Documentó `FirmwareAdvertType` en [`src/protocol_types.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/protocol_types.py).
  2. **Agente 4 (Web UI/UX Architect Agent)**:
     - Removió los botones redundantes de sincronización manual (`btnSyncChannels`, `btnSyncContacts`), ya que la sincronización es 100% automática.
     - Añadió botones de eliminación directa `🗑️` en canales secundarios (1-7), mensajes directos (DMs) y tarjetas del directorio/contactos.
     - Implementó métodos `deleteChannel(index)` y `deleteContact(pubkey)` en [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js) con confirmación y retroalimentación mediante toasts.
     - Actualizó el selector de tipos de nodo en `#createContactModal` con los roles oficiales de MeshCore.
  3. **Agente 0 (Agente Principal)**:
     - Comprobó estática estricta con `mypy --strict src/` (0 errores) y `ruff check`.
     - Dejó en ejecución permanente la simulación multi-canal y multi-contacto en el puerto 8080.
     - Sincronizó paquete en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/).

---

### Hito Anterior: Auto-Importación en Arranque y Sincronización Continua Bidireccional con Heltec
- **Fecha**: 2026-08-18
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó el arranque asíncrono no bloqueante y la difusión en tiempo real de canales y contactos por WebSockets.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Bridge Architect Agent)**:
     - Implementó `_auto_bootstrap_heltec_state()` en `MeshCoreBridge.start()` ([`src/bridge_core.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/bridge_core.py)) para consultar y precargar automáticamente canales (`get_channels`), libreta de contactos (`sync_all_contacts`) y parámetros de radio/hardware (`fetch_device_config`) del transceptor Heltec USB al iniciar el script.
     - Añadió `remove_contact(pubkey)` en `BaseSerialAdapter` y `MeshcoreSDKAdapter` ([`src/serial_driver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial_driver.py)).
     - Implementó `fetch_device_config()` en `AdminCommandHandler` ([`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py)).
     - Añadió difusión de eventos WebSocket (`channels_updated`, `contacts_updated`) en `WebAPIRouter` ([`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py)) al crear o eliminar canales/contactos.
  2. **Agente 4 (Web UI/UX Architect Agent)**:
     - Añadió receptores en tiempo real para `channels_updated` y `contacts_updated` en `handleIncomingLiveEvent` ([`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js)), asegurando que la interfaz refleje inmediatamente cualquier cambio ocurrido en el hardware o desde otros clientes.
  3. **Agente 0 (Agente Principal)**:
     - Comprobación estática estricta con `mypy --strict src/` (0 errores) y `ruff check`.
     - Sincronización del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/).

---

### Hito Actual: Suite Completa de Administración de Repetidores, Parser de Telemetría Real y Deduplicación Inteligente de Nodos
- **Fecha**: 2026-08-19
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó la resolución integral del problema de duplicación de clientes, el parser de telemetría de repetidores, y la implementación de todas las opciones de administración remota de MeshCore en backend y frontend.
- **Contribuciones de Agentes**:
  1. **Agente 1 & 2 (Investigador de Protocolo & Arquitecto de Bridge)**:
     - Diseñó e implementó `_find_existing_key()` y motor de deduplicación canónica en `NodeRegistry` ([`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py)), eliminando duplicados causados por coincidencia de prefijos hex vs claves de 64 caracteres.
     - Implementó `parse_repeater_telemetry_or_response()` en [`src/repeater_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/repeater_manager.py) capaz de extraer structured metrics (Battery %/mV, Solar V, RTC clock, Uptime, Airtime ms, RSSI, SNR, Noise floor dBm, Packets sent/recv/dup/err/queue, Lat/Lon/Alt, Owner Info, Firmware/Board) a partir de respuestas CLI de texto de MeshCore.
     - Enriqueció `build_repeater_command_payload()` con los 15 comandos de administración de MeshCore (owner, advert, advert intervals, pos, sync clock, ACL mode, admin/guest passwords, identity key, radio regions/freq, neighbours, repeat settings, telemetry, reboot, version, board).
     - Integró el parser en el despachador de eventos RF ([`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py)) para actualización en vivo vía MQTT y WebSocket.
  2. **Agente 4 (Web UI/UX Architect Agent)**:
     - Rediseñó y expandió `#repeaterAdminModal` ([`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html)) con 7 subpestañas: Telemetría Extendida (8 tarjetas métricas), Configuración RF, Propietario & Posición, Seguridad & Control de Acceso (ACL), Malla & Vecinos, Terminal RF con Guía de Ayuda Interactiva (`help`), y Acciones Rápidas.
     - Añadió cajón interactivo de ayuda de comandos (`#terminalHelpDrawer`) con inserción de comando a un clic.
     - Añadió deduplicación inteligente del lado del cliente en `renderNodesDirectory()` ([`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js)).
     - Conectó actualización en caliente del modal de administración ante eventos de telemetría entrantes.
  3. **Agente 5 (Auditor de Seguridad)**:
     - Corrigió BUG-01 (Thread safety en MQTT con `asyncio.run_coroutine_threadsafe`).
     - Corrigió BUG-02 (Cierre seguro e independiente de subsistemas en `bridge_core.py`).
     - Corrigió BUG-03 (Log de error ante RuntimeErrors en `mqtt_dispatcher.py`).
     - Corrigió BUG-04 (Sanitización y entrecomillado en `set_channel` en `serial_driver.py`).
     - Corrigió BUG-06 (Serialización con `asyncio.Lock` en transacciones SQLite de `store_forward.py`).
     - Corrigió BUG-07 (Consumo de memoria O(1) con `collections.deque` en `diagnostics.py`).
  4. **Agente 0 (Agente Principal)**:
     - Verificación estática estricta con `ruff check` (0 errores) y `mypy --strict src/` (0 errores en 22 módulos).
     - Comprobación de sintaxis JS con `node --check src/web/static/js/app.js` (0 errores).
     - Sincronización completa del paquete `/deploy/` ejecutando `python scripts/sync_deploy.py`.

---


- **Fecha**: 2026-08-18
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó el diseño de modales, sincronización serial Heltec y generador QR offline.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Bridge Architect Agent)**:
     - Eliminó canales de prueba ficticios en `WebAPIRouter.__init__` (solo Canal 0 por defecto).
     - Implementó `set_channel`, `add_contact`, y `sync_all_contacts` en `MeshcoreSDKAdapter` ([`src/serial_driver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial_driver.py)).
     - Creó endpoints `POST /api/channels/sync`, `DELETE /api/channels`, `POST /api/contacts/sync` y `DELETE /api/contacts` en [`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py).
     - Añadió soporte de campo `role` en `NodeContactInfo` y `NodeContactUpdate` ([`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py)).
  2. **Agente 4 (Web UI/UX Architect Agent)**:
     - Creó módulo generador de Códigos QR offline en Vanilla JS puro ([`src/web/static/js/qrcode.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/qrcode.js)).
     - Diseñó modales emergentes: `#createChannelModal`, `#createContactModal`, `#qrShareModal` e `#importModal` en [`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html).
     - Añadió generador aleatorio de claves AES-128 (PSK) y soporte para importar por URI `meshcore://...` o JSON.
     - Implementó reglas CSS `@media (max-width: 900px)` para evitar deformación visual en tablets y celulares, con panel drawer deslizante.
  3. **Agente 0 (Agente Principal)**:
     - Verificó integridad estática con `mypy --strict` (0 errores) y `ruff check`.
     - Sincronizó paquete de distribución en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) sin ejecutar pruebas automáticas (respetando orden de usuario).

---

### Hito Anterior: Rediseño de Mensajería, Optimización UX y Sincronización de Canales
- **Fecha**: 2026-08-18
- **Estado**: ✅ COMPLETADO
- **Agente Principal (Lead Orchestrator)**: Coordinó el desglose de tareas entre Web UI y Backend Serial.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX Architect)**:
     - Reubicó los selectores de Canales LoRa y Mensajes Directos (DMs) dentro de la vista de Mensajería (`tab-chat`) en un layout integrado de dos columnas (`chat-channels-panel` y `chat-conversation-panel`).
     - Eliminó el mensaje de bienvenida estático (`chat-welcome-card`) del feed.
     - Renombró el botón de transmisión a `"Enviar 📤"`.
     - Removió el botón `"Trace Route"` y su lógica asociada.
     - Corrigió los subtítulos de canal para eliminar `"Hop limit: 3"` y reemplazarlos por descripciones contextuales (`🔓 Abierto` / `🔒 Cifrado`).
  2. **Agente 2 (Bridge Architect Agent)**:
     - Implementó `get_channels()` en `BaseSerialAdapter` y `MeshcoreSDKAdapter` ([`src/serial_driver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial_driver.py)).
     - Actualizó `WebAPIRouter._route_channels` ([`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py)) para sincronizar los canales reales del nodo USB conectado.
  3. **Agente 0 (Agente Principal)**:
     - Concilió la compatibilidad entre el frontend SPA y el backend REST/WebSocket.
     - Sincronizó el paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/).

---

## 📐 Matriz de Contratos e Interfaces Activas

| Subsistema / Contrato | Endpoint / Canal | Formato / Esquema | Responsable | Estado |
|---|---|---|---|---|
| **Canales REST** | `GET /api/channels` | `[{ index, name, psk, is_public }]` | Agente 2 / Agente 4 | Sincronizado |
| **Envío Mensajes** | `POST /api/tx` | `{ to, text, channel_index, request_id }` | Agente 2 | Activo |
| **Logs del Sistema** | `GET /api/system/logs` | `{ status, data: [...], counters, current_level }` | Agente 2 | Activo |
| **Reporte IA** | `GET /api/diagnostics/report.md` | `{ status: "ok", markdown: "..." }` | Agente 2 / Agente 4 | Activo |
| **Descarga Logs** | `GET /api/logs/download` | `{ status: "ok", raw_logs: "..." }` | Agente 2 | Activo |
| **MQTT Rx Broker** | `meshcore/rx/all`, `meshcore/rx/ch_<N>` | JSON con `sender`, `text`, `channel_idx`, `is_outgoing: false` | Agente 2 | Activo |
| **MQTT Tx Broker** | `meshcore/tx` | JSON con `to`, `text`, `channel_idx` | Agente 2 | Activo |

### [TASK-2026-08-19-03] Implementación de 5 Características Avanzadas de MeshCore
- **Fecha y Hora**: 2026-08-19 18:04
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect)
- **Objetivo**: Integrar 1) Presupuesto de Airtime y Duty Cycle Compliance (1h/24h), 2) Heatmap de Cobertura RF y Matriz de Ruido, 3) Intercambio Automático de Tarjetas de Contacto (Contact Discovery), 4) Confirmaciones Criptográficas E2E (Delivery Receipts con trip_time y doble check ✓✓), y 5) Traceroute Multi-Salto Visual con desglose de saltos, RTT y SNR.
- **Archivos Modificados / Creados**:
  - `src/rate_limiter.py`: Añadida clase `AirtimeTracker` y estructura `AirtimeRecord` con cálculo de ventanas deslizantes (1h/24h) y métricas de Duty Cycle %.
  - `src/contact_manager.py`: Añadidos campos `auto_discovered`, `discovery_time`, `verified_identity`, `is_favorite` y métodos `discover_node()`, `list_discovered()`, `accept_discovered_contact()`.
  - `src/store_forward.py`: Creada tabla SQLite `message_receipts` con transacciones WAL para registrar mensajes salientes y confirmar entregas con `trip_time_ms`.
  - `src/rx_router.py`: Detección en tiempo real de eventos `ACK`, balizas desconocidas (Contact Discovery) y tramas de traza multi-salto (`trace_data`).
  - `src/admin_handler.py`: Implementado manejador de acción `traceroute` (`CMD_SEND_TRACE_PATH = 36`) con desglose de saltos, RTT y SNR.
  - `src/web/api_router.py`: Nuevos endpoints `GET /api/airtime/stats`, `GET /api/rf/heatmap`, `GET /api/rf/noise`, `GET /api/contacts/discovered`, `POST /api/contacts/accept`, `POST /api/traceroute`.
  - `src/web/static/index.html`: Badge de Airtime en header, botón `🔥 Heatmap RF` en selector de capas Leaflet, banner de Contact Discovery, y modal de Traceroute Visual (`#tracerouteModal`).
  - `src/web/static/js/app.js`: Monitoreo en vivo de Airtime/Duty Cycle, renderizado de capa Heatmap sobre Leaflet, banner reactivo de Contact Discovery, recibos de entrega en chat (✓✓ con latencia) y grafo interactivo de Traceroute.
  - `src/web/static/css/app.css`: Estilos visuales para todos los nuevos componentes, badges, gráficas y animaciones de pulso.
- **Contratos / Interfaces Modificadas**:
  - `GET /api/airtime/stats` -> `{ hourly_used_ms, hourly_budget_ms, hourly_duty_cycle_pct, is_throttled }`
  - `GET /api/rf/heatmap` -> `{ points: [{ lat, lon, rssi, snr, weight, name, noise_floor }] }`
  - `GET /api/rf/noise` -> `{ matrix: [{ pubkey, name, noise_floor_dbm, snr, rssi, channel, freq }] }`
  - `GET /api/contacts/discovered` -> `{ discovered: [...], count }`
  - `POST /api/contacts/accept` -> `{ public_key }`
  - `POST /api/traceroute` -> `{ target_node, path }`
  - Eventos WebSocket: `contact_discovered`, `message_delivered`, `trace_data`.
### [TASK-2026-08-19-04] Corrección de Superposición y Minimizado de Lista de Nodos en Mapa
- **Fecha y Hora**: 2026-08-19 18:07
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect)
- **Objetivo**: Corregir superposición espacial entre el selector de capas cartográficas (`.map-layer-switcher`) y la lista flotante de nodos (`.map-overlay-info`), y dotar a la lista de nodos de capacidad interactiva de colapso y minimización con persistencia en `localStorage`.
- **Archivos Modificados / Creados**:
  - `src/web/static/index.html`: Agregado encabezado interactivo `#mapOverlayHeader` con botón `#btnToggleMapNodes` (`−`/`＋`) y soporte de accesibilidad `aria-expanded`.
  - `src/web/static/css/app.css`: Reubicado `.map-layer-switcher` a `left: 56px; top: 14px;` (junto al zoom control), agregados estilos `.map-overlay-header`, `.btn-toggle-overlay` y estado `.minimized`, y soporte responsivo móvil (`<= 768px`).
  - `src/web/static/js/app.js`: Implementado método `initMapOverlayToggle()` con listener para alternar clases, animaciones y persistencia en `localStorage.getItem("meshcore_map_nodes_minimized")`.
- **Contratos / Interfaces Modificadas**:
  - Estado local persistido: `meshcore_map_nodes_minimized` ("true" / "false").
### [TASK-2026-08-19-05] Corrección de Errores de Inicialización en SQLite y collections
- **Fecha y Hora**: 2026-08-19 18:08
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect)
- **Objetivo**: Corregir error de inicialización en SQLite `sqlite3.ProgrammingError: You can only execute one statement at a time` y `NameError: name 'collections' is not defined` en `AirtimeTracker`.
- **Archivos Modificados / Creados**:
  - `src/rate_limiter.py`: Añadido `import collections` a las importaciones del módulo.
  - `src/store_forward.py`: Reemplazado `conn.execute()` por `conn.executescript()` en el método `_init_db()`.
- **Contratos / Interfaces Modificadas**: Ninguno (corrección de estabilidad y robustez interna).
### [TASK-2026-08-19-06] Depuración y Filtrado de Contactos, Exclusión de Nodo Local y Métricas RF Reales
- **Fecha y Hora**: 2026-08-19 18:20
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 2 (Bridge Architect)
- **Objetivo**: Eliminar subtítulo obsoleto de memoria flash Heltec en pestaña Contactos, filtrar estrictamente repetidores (`R1-Lee`) para que solo aparezcan estaciones cliente, excluir la estación base local (`Node_34c0c7`) de los contactos remotos, sanear métricas RF evitando valores por defecto ficticios (`-80 dBm/10 dB/0 saltos`) y pulir estados vacíos de la interfaz.
- **Archivos Modificados / Creados**:
  - `src/web/static/index.html`: Eliminado subtítulo obsoleto y mejorado placeholder de búsqueda.
  - `src/web/static/js/app.js`: Guardado de `localNodePubkey`, exclusión de `isLocal` y repetidores en `contactsGrid`, formateo estricto de mediciones reales (`snrVal`, `rssiVal`, `hopsVal`, `batVal`) y manejo elegante de estados vacíos.
  - `src/contact_manager.py`: Valores por defecto de `last_rssi`, `last_snr`, `hops` establecidos a `None` para no simular métricas no medidas.
  - `src/serial_driver.py`: Inferencia de rol en `sync_all_contacts()` basada en `type`, `adv_type` y prefijos de nombre (`R1-`, `R-`, etc.).
- **Contratos / Interfaces Modificadas**: Ninguno (saneamiento de datos y lógica de presentación).
### [TASK-2026-08-19-07] Deduplicación y Normalización Canónica de Claves para Mensajes Directos (DM)
- **Fecha y Hora**: 2026-08-19 18:28
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 2 (Bridge Architect)
- **Objetivo**: Corregir duplicación de clientes en la barra lateral de mensajes directos (DM) provocada por discrepancias entre prefijos de clave pública (`8d5accef1946` de 12 caracteres recibidos en eventos de radio) y claves completas (`8d5accef1946bc...` de 64 caracteres registradas en la libreta).
- **Archivos Modificados / Creados**:
  - `src/contact_manager.py`: Agregado método `get_canonical_key()` en `NodeRegistry` para resolver prefijos a claves canónicas conocidas.
  - `src/rx_router.py`: Normalización de `sender` a la clave canónica antes de despachar eventos MQTT y WebSocket.
  - `src/web/static/js/app.js`: Implementado método `resolveCanonicalPubkey()`, unificación de feeds `dm_${canonicalPk}`, deduplicación estricta de elementos en `#dmListUi` y sincronización bidireccional de conversaciones directas.
- **Contratos / Interfaces Modificadas**: Ninguno (normalización de identificadores y resolución canónica interna).
### [TASK-2026-08-19-08] Validación y Supresión de Falsos Positivos en Contact Discovery
- **Fecha y Hora**: 2026-08-19 18:33
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 2 (Bridge Architect)
- **Objetivo**: Evitar que el banner de "Nuevos Nodos Descubiertos en el Aire" se muestre si los nodos capturados ya están registrados en la libreta de contactos, o si corresponden a repetidores, infraestructura o la estación base local.
- **Archivos Modificados / Creados**:
  - `src/contact_manager.py`: En `discover_node()` y `list_discovered()`, exclusión de repetidores/sensores y preservación de `auto_discovered = False` si el nodo ya existe en la libreta de contactos.
  - `src/web/static/js/app.js`: En `fetchDiscoveredContacts()`, filtrado estricto contra `knownNodes`, repetidores y nodo local, ocultando el banner si el conteo de clientes verdaderamente nuevos es 0.
- **Contratos / Interfaces Modificadas**: Ninguno (depuración y validación de estado de descubrimiento).
### [TASK-2026-08-19-09] Remaquetación de Subpestañas en Ajustes, Carga Integral de Telemetría y Sistema de Delimitador/Badges de Mensajes No Leídos
- **Fecha y Hora**: 2026-08-19 18:44
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 2 (Bridge Architect)
- **Objetivo**: Remaquetar la barra de subpestañas de Ajustes en una cuadrícula CSS responsiva sin scrollbar horizontal y con scroll vertical fluido; consolidar la carga de todos los datos del nodo local y telemetría de hardware; e implementar un sistema de badges de mensajes no leídos por canal/DM con delimitador visual ("⚡ Mensajes Nuevos") en el feed de chat.
- **Archivos Modificados / Creados**:
  - `src/web/static/css/app.css`: Reemplazado `.local-settings-subtabs` por CSS Grid adaptativo (`repeat(auto-fit, minmax(170px, 1fr))`) sin `overflow-x`; ajustado scroll vertical de `.settings-view-container`; añadidos estilos para `.nav-badge-count`, `.ch-unread-badge` (con animación de pulso) y `.chat-unread-divider`.
  - `src/web/static/index.html`: Añadido span `#globalChatUnreadBadge` en el botón principal de Mensajería.
  - `src/web/static/js/app.js`: Implementado rastreo de `unreadCounts` y `lastReadTimestamps`; actualización reactiva de badges en canales, DMs y menú global; inserción del delimitador `chat-unread-divider` al ingresar a chats con mensajes no leídos; y enriquecido `fetchLocalNodeConfig()` con datos completos de telemetría y puerto serie.
  - `src/admin_handler.py`: Consolidación completa de parámetros de hardware, GPS y radio en `get_local_config()`.
- **Contratos / Interfaces Modificadas**: Ninguno (enriquecimiento de campos de configuración y mejoras de experiencia de usuario en frontend).
- **Estado**: COMPLETADO

### [TASK-2026-08-19-10] Flujo Estricto de Autenticación, Gating y Gestión Persistente de Contraseñas en Repetidores LoRa
- **Fecha y Hora**: 2026-08-19 18:50
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 5 (Security Auditor), Agente 2 (Bridge Architect)
- **Objetivo**: Implementar un flujo de seguridad estricto para la administración de repetidores MeshCore remotos. Bloqueo total de parámetros y pestañas mediante pantalla de gating `#repeaterAuthGate` hasta autenticación válida; auto-login y persistencia de contraseñas por repetidor en `localStorage` (`meshcore_repeater_passwords`); invalidación inmediata de clave, bloqueo de UI y toast de error si la contraseña es incorrecta o fue modificada en el repetidor.
- **Archivos Modificados / Creados**:
  - `src/web/static/index.html`: Estructura HTML de `#repeaterAuthGate` con formulario de contraseña/PIN, botón de visibilidad y contenedor `#repeaterAdminUnlockedContent` con botón de cierre de sesión `#btnRepeaterLogout`.
  - `src/web/static/css/app.css`: Estilos de seguridad para `.repeater-admin-modal-card.locked`, `.repeater-admin-modal-card.unlocked`, `.repeater-auth-gate`, `.auth-gate-card`, `.auth-gate-shield` y chips de autenticación.
  - `src/web/static/js/app.js`: Implementación de `getStoredRepeaterPassword()`, `setStoredRepeaterPassword()`, `clearStoredRepeaterPassword()`, `getRepeaterPassword()`, `authenticateRepeater()`, `lockRepeaterAdminView()`, `unlockRepeaterAdminView()`, `handleRepeaterAuthError()`, auto-autenticación en `openRepeaterAdminModal()` y captura reactiva de fallos de credenciales en `handleIncomingLiveEvent()`.
  - `src/repeater_manager.py`: Detección e inclusión de `auth_status` ("success" / "failed") y `auth_error` en `parse_repeater_telemetry_or_response()`.
  - `src/admin_handler.py`: Manejo dedicado de la acción `login` con enmascaramiento de contraseña en los logs de comando.
- **Contratos / Interfaces Modificadas**: Ninguno (robustecimiento de autenticación RF y experiencia SPA).
- **Estado**: COMPLETADO

### [TASK-2026-08-19-11] Saneamiento de Telemetría Nula y Carga Integral de Parámetros de Repetidores LoRa
- **Fecha y Hora**: 2026-08-19 18:58
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 2 (Bridge Architect)
- **Objetivo**: Corregir la representación de valores nulos en el Centro de Control RF de repetidores (eliminando textos literales "null ms", "null dBm", "null TX / null RX", "Duplicados: null"), enriquecer el parser de respuestas del firmware con extracción exhaustiva de parámetros de radio (frecuencia, potencia TX, SF, BW, CR, repetición, hops, beacon), propietario y posición fija, y automatizar la solicitud de telemetría completa y configuración al autenticar o actualizar remotamente.
- **Archivos Modificados / Creados**:
  - `src/web/static/js/app.js`: Saneamiento de comprobaciones en `populateRepeaterModalData` usando `val != null` y valores de reserva adecuados (`--`); sincronización automática multiconsulta (`stats-core`, `stats-radio`, `pos`, `owner`) en `authenticateRepeater`, `openRepeaterAdminModal` y `btnRefreshRepeaterTelem`; actualización reactiva en vivo en `handleIncomingLiveEvent` para eventos directos y de telemetría.
  - `src/repeater_manager.py`: Ampliación exhaustiva de expresiones regulares en `parse_repeater_telemetry_or_response()` para soportar todos los formatos de telemetría de repetidores de MeshCore (frecuencia, potencia, SF, BW, CR, modo repetidor, hops, beacon, posición fija, nombre/información de propietario, variantes de voltaje y airtime en segundos o milisegundos).
  - `src/contact_manager.py`: Incorporación de campos `coding_rate` y `fixed_position` en `NodeContactInfo` y `NodeContactUpdate`.
  - `src/rx_router.py`: Mapeo completo de todos los atributos de telemetría y radio extraídos hacia `NodeContactUpdate` en `_handle_mesh_direct_msg` y `_handle_mesh_telemetry_msg`.
- **Contratos / Interfaces Modificadas**: Enriquecimiento de atributos en `NodeContactInfo.to_dict()` (`coding_rate`, `fixed_position`).
- **Estado**: COMPLETADO

### [TASK-2026-08-19-13] Supresión de DMs Espurios de Comandos y Tratamiento Estricto del Nodo Local
- **Fecha y Hora**: 2026-08-19 19:15
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect), Agente 5 (Security Auditor)
- **Objetivo**: Corregir el despacho de comandos de administración remota (`cmd login ...`, `cmd ping`, `cmd trace ...`) como mensajes de texto de chat directo (DM) hacia clientes remotos; validar el tipo de nodo objetivo para restringir comandos de administración exclusivamente a repetidores/routers de infraestructura; migrar el traceroute a la llamada nativa por radio del SDK (`mc.commands.send_trace`); e identificar y maquetar la estación base local como nodo propio en la vista de Directorio (sin botones de DM, ping o ruta hacia sí mismo, y sin simulación espuria de mediciones de señal RF sobre sí mismo).
- **Archivos Modificados / Creados**:
  - `src/contact_manager.py`: Añadido soporte de `is_local` en `NodeContactInfo`, `NodeContactUpdate` y `NodeRegistry` (`set_local_pubkey`, `is_local_key`); el nodo local se registra con rol `LOCAL`, `hops=0` y sin métricas de señal RF recibida; exclusión de nodos locales en `list_discovered()`.
  - `src/rx_router.py`: Detección de transmisor local para no asignarle métricas RF de recepción sobre sí mismo ni emitir eventos espurios de nuevo contacto descubierto.
  - `src/admin_handler.py`: Protección del nodo local contra comandos remotos (`traceroute`, `ping_zero`, `login`); en `traceroute`, invocación del comando nativo de radio `mc.commands.send_trace` sin transmitir mensajes de texto de chat a los clientes; validación de repetidor antes de enviar `ping_zero` o `cmd login`; supresión de `cmd login ` con contraseña vacía.
  - `src/bridge_core.py`: Registro automático de la clave pública del nodo local en `NodeRegistry` al sincronizar la configuración de hardware Heltec.
  - `src/web/api_router.py`: Inclusión de `local_node_pubkey` y `local_node_name` en `/api/status`; validación de tipo y propagación de errores HTTP 400 en `/api/repeater/remote/login`, `/api/repeater/remote/config`, `/api/repeater/remote/action` y `/api/repeater/ping_zero`.
  - `src/web/static/js/app.js`: Identificación de la tarjeta local (`isLocal`) en el Directorio Unificado con avatar `🏠`, rol `LOCAL (Estación Base)`, panel de parámetros de radio (frecuencia, potencia, SF/BW, puerto) y acceso directo a Ajustes; eliminación del botón `Ping 0` en tarjetas de clientes estándar; protección en `openDmConversation`, `openTracerouteModal` y `pingZero` para impedir ejecuciones hacia el nodo local; actualización reactiva de `localNodePubkey` desde `/api/status`.
  - `src/web/static/css/app.css`: Estilos visuales para `.node-card.role-local-card`, `.node-card-avatar.avatar-local`, `.node-role-badge.role-local` y badges por rol.
- **Contratos / Interfaces Modificadas**: Inclusión de `local_node_pubkey` y `local_node_name` en `GET /api/status`; campo `is_local: bool` en `NodeContactInfo.to_dict()`.
- **Estado**: COMPLETADO

---

## 📝 Plantilla de Registro para Nuevas Tareas

Cada vez que un agente comience o finalice una tarea, agregará una entrada en la siguiente estructura:

```markdown
### [ID de Tarea] [Nombre Descriptivo de la Tarea]
- **Fecha y Hora**: YYYY-MM-DD HH:MM
- **Agente Responsable**: [Agente 1 / Agente 2 / Agente 4 / Agente 5]
- **Objetivo**: [Descripción concisa del requerimiento]
- **Archivos Modificados / Creados**:
  - `src/...`
  - `src/web/...`
- **Contratos / Interfaces Modificadas**:
  - [Detalle de cambios en API REST, WebSockets, esquemas MQTT o tipos]
- **Acciones Requeridas por el Agente Principal**:
  - [Notas de compatibilidad cruzada para armonizar otros subsistemas]
- **Estado**: [EN PROGRESO / COMPLETADO]
```
