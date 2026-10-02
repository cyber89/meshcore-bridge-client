# ADR 0001: Exclusión Estricta de Dispositivos Repetidores de la Libreta de Contactos y Mensajería de Chat

- **Estado**: Aceptado
- **Fecha**: 2026-09-12
- **Autores**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect)
- **Contexto**: `CONTEXT.md`, `AGENTS.md` (Sección 1.1)

---

## Contexto y Problema

En las redes de malla LoRa de MeshCore, coexisten múltiples tipos de nodos clasificados mediante `FirmwareAdvertType`.
Los nodos con rol `REPEATER` (`FirmwareAdvertType.REPEATER = 2`) son dispositivos de infraestructura de telecomunicaciones típicamente instalados en puntos elevados (mástiles, cerros, azoteas) cuya única función de radio es recibir paquetes LoRa y retransmitirlos para extender el alcance de la red.

Anteriormente existía la ambigüedad o el riesgo de que los repetidores aparecieran mezclados con usuarios humanos en la libreta de contactos (`#tab-contacts`) de la interfaz web, o que un usuario o automatización MQTT intentara enviarles mensajes directos (DM) o mensajes de canal.

## Factores de Decisión

1. **Separación de Mensajería y Administración**: El repetidor no ofrece un buzón ni interfaz de chat de usuario. Puede procesar comandos administrativos transportados como texto cifrado; la prohibición se aplica al chat de usuario, no a esas operaciones explícitas de gestión.
2. **Confusión de Experiencia de Usuario (UX)**: Un operador humano no debe ver repetidores de red como si fueran personas o contactos con los que puede "conversar".
3. **Seguridad y Control**: La interacción utiliza los comandos administrativos y permisos del firmware: login, texto CLI administrativo cifrado, estado, telemetría y trazado. Los nombres de acciones del bridge no deben confundirse con opcodes Companion; estos se consultan en `docs/PROTOCOL_SPEC.md` y `reference/meshcore_py/src/meshcore/packets.py`.

## Decisión

1. **Aislamiento en Registro**: `NodeRegistry.list_client_contacts()` filtrará permanentemente los nodos, excluyendo todo nodo cuyo rol sea `REPEATER` o `ROUTER`.
2. **Aislamiento en Frontend**: La pestaña Contactos (`#tab-contacts`) jamás listará repetidores. Los repetidores residen exclusivamente en la cuadrícula unificada de Nodos (`#unifiedNodesGridUi`) y en la vista de Analítica/Topología.
3. **Bloqueo en Controladores y Chat**:
   - En el backend (`src/web/controllers/tx_controller.py`), cualquier intento de enviar un mensaje de chat (DM) a un nodo repetidor es rechazado con error HTTP 400 Bad Request.
   - En el frontend (`chat.js`), la interfaz bloquea e inhabilita el inicio de conversaciones directas con repetidores.
4. **Interacción Restringida a Gestión de Red**: La interacción con repetidores se canaliza únicamente a través de `RepeaterManager` mediante acciones administrativas explícitas: `🎛️ Administrar`, `🎯 Ping (Hop 0)`, `🗺️ Traceroute` y solicitudes de telemetría.

## Consecuencias

- **Positivas**:
  - Eliminación total de tráfico de chat inútil dirigido a repetidores, ahorrando airtime en la malla.
  - Claridad absoluta en la interfaz de usuario: la libreta de contactos solo contiene clientes reales.
  - Cumplimiento inmutable de la regla SSoT de MeshCore.
- **Negativas / Compensaciones**:
  - Para interactuar con un repetidor se debe usar la vista Nodos o la consola administrativa dedicada, no el chat.
