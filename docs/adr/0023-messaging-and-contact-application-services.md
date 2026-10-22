# ADR 0023: Extracción de Servicios de Aplicación para Mensajería y Contactos (`MessageService` y `ContactService`)

- **Estado**: Aceptado
- **Fecha**: 2026-10-21
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: Fase F3.2 del Plan de Evolución `nuevo.md`, `src/application/messaging.py`, `src/application/contacts.py`, `src/web/controllers/tx_controller.py`, `src/web/controllers/history_controller.py`, `src/web/controllers/contacts_controller.py`, `src/mqtt_dispatcher.py`, `src/bridge_core.py`

---

## Contexto y Problema

En las versiones previas de MeshCore Bridge, la lógica de validación, persistencia, sincronización con radio y formato de mensajería y libreta de contactos se encontraba fuertemente acoplada a los controladores web REST (`TxController`, `HistoryController`, `ContactsController`):

1. **Acoplamiento con la Capa Web**: Las validaciones de nombres de firmware (31 bytes UTF-8), claves públicas de nodos (32 bytes / 64 caracteres hex), comprobación de reglas inmutables (exclusión de repetidores y estación local) y parseo de payloads URI/tags estaban implementadas como métodos privados dentro de controladores web. Si la estación operaba en modo headless (`WEB_ENABLED=false`) o procesaba comandos entrantes desde MQTT o integraciones LAN (n8n), estas reglas debían duplicarse o quedaban desprotegidas.
2. **Duplicación de Validaciones y Lógica TX**: Tanto `TxController` como `MqttInboundDispatcher` validaban parámetros de transmisión (longitud de texto, límites de airtime, formato de destinatario `broadcast` vs clave pública DM, e índice de canal) de manera independiente, arriesgando divergencias de comportamiento.
3. **Consistencia Transaccional con Hardware**: La manipulación de contactos (alta, baja, sincronización, importación) requería asegurar que un rechazo del transceptor físico LoRa (`add_contact`, `remove_contact`) preservara intacto el registro local (`NodeRegistry`) y la persistencia SQLite, evitando inconsistencias entre la radio física y el bridge.

## Factores de Decisión

1. **Monolito Modular e Independencia Headless**: Toda la lógica de dominio de mensajería y contactos debe residir en `src/application/`, completamente desacoplada de frameworks HTTP (cero importaciones de FastAPI, Starlette o Paho).
2. **Invariantes Inmutables de Red LoRa (Reglas 1.1 y 1.2 de AGENTS.md y CONTEXT.md)**:
   - Los nodos repetidores (`REPEATER` / `ROUTER`) **nunca** deben incluirse en la libreta de contactos ni ser objetivo de mensajería de chat (broadcast o directa).
   - La estación base local (`LOCAL`) **nunca** debe agregarse a contactos ni ser destinataria de mensajes a su propia clave pública.
3. **Gestión de Errores Estandarizada**: Retornar objetos inmutables tipados (`MessageSendResult`, `ContactOperationResult`, `ValidationResult`) con códigos de estado, mensajes descriptivos y códigos de error normalizados (`error_code`).

## Decisión

Se decide extraer la lógica de mensajería y libreta de contactos a dos servicios de aplicación independientes en `src/application/`:

### 1. `MessageService` (`src/application/messaging.py`)
- **Validación de Transmisiones (`validate_tx_request`)**:
  - Valida textos de mensaje (1 a 240 caracteres legibles, excluyendo secuencias maliciosas o vacías).
  - Normaliza y valida destinatarios: `broadcast` o clave pública válida de 64 caracteres hex.
  - Verifica las Reglas 1.1 y 1.2: bloquea intentos de chat dirigidos a repetidores o a la clave pública local.
  - Valida que el canal solicitado (0 a 7) esté habilitado en la estación.
- **Ejecución y Encolado (`submit_chat`)**:
  - Admite solicitudes evaluando el limitador de tasa (`TxRateLimiter`) y medidor de airtime.
  - Registra paquetes y gestiona la cola de prioridad (`TxPriority.HIGH` para DMs, `TxPriority.NORMAL` para canales).
- **Historial e Importación (`get_history`, `get_conversations`, `get_recent_messages`, `import_messages`)**:
  - Consulta y exporta mensajes directamente desde la base de datos persistente SQLite (`StationDatabase`).

### 2. `ContactService` (`src/application/contacts.py`)
- **Validación y Reglas de Infraestructura (`validate_contact`)**:
  - Valida formato de clave pública (64 caracteres hex) y compatibilidad de nombre con el firmware (hasta 31 bytes en UTF-8 sin caracteres de control `< 0x20` ni `0x7F`).
  - Aplica estrictamente las Reglas 1.1 y 1.2 (rechaza `REPEATER`, `ROUTER` y `LOCAL`).
- **Sincronización Bidireccional con Radio**:
  - `create_or_update_contact`: Ejecuta la mutación física en hardware (`ser.add_contact`); si el transceptor confirma la operación, actualiza `NodeRegistry` y persiste atómicamente en disco. Si el hardware rechaza la operación, el registro local permanece inalterado.
  - `delete_contact`: Elimina del hardware (`ser.remove_contact`) y, tras confirmación, del registro local.
  - `sync_from_radio`: Importa todos los contactos almacenados en el transceptor oficial filtrando repetidores y nodo local.
  - `share_contact` y `export_contact`: Genera URIs oficiales canónicas `meshcore://contact/add?...` y tags `<pubkey:type:name>`.
  - `import_contact_payload`: Parsea e importa por lotes desde URIs, tags, JSON o volcados binarios/hex, rechazando cargas correspondientes a canales (`channel_payload_in_contacts`).

### 3. Refactorización de Adaptadores Web y MQTT
- `TxController`, `HistoryController` y `ContactsController` se transforman en adaptadores HTTP delgados que delegan directamente en `MessageService` y `ContactService`, traduciendo los resultados tipados a respuestas RFC 7807 (`problem_details`) y emitiendo eventos WebSocket (`contacts_updated`) cuando corresponde.
- `MqttInboundDispatcher` utiliza `MessageService.validate_tx_request` de forma previa a la reserva en el libro contable de comandos (`CommandLedgerPolicy`) y al encolado de transmisión.

## Consecuencias

- **Positivas**:
  - Desacoplamiento total: la mensajería y la libreta de contactos funcionan con paridad absoluta tanto en modo web como en modo headless o CLI.
  - Gobernanza unificada de las invariantes de red LoRa: ninguna ruta (REST, WebSocket, MQTT, auto-bootstrap) puede eludir la exclusión de repetidores o de la estación local.
  - Cobertura de pruebas simplificada: las pruebas unitarias pueden ejercitar `MessageService` y `ContactService` directamente sin levantar entornos HTTP o servidores WS.
- **Negativas / Compensaciones**:
  - Aumenta levemente la cantidad de clases y capas de indirección, requiriendo inyección adecuada de dependencias en el constructor de `MeshCoreBridge`.
