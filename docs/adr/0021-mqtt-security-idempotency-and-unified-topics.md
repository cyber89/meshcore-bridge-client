# ADR 0021: Seguridad MQTT, Idempotencia de Órdenes y Resolvedor Unificado de Tópicos

- **Estado**: Aceptado
- **Fecha**: 2026-10-21
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: Fase F1 del Plan de Evolución `nuevo.md`, `src/mqtt_client.py`, `src/external_mqtt_client.py`, `src/mqtt_dispatcher.py`, `src/station_database.py`, `src/application/command_policy.py`

---

## Contexto y Problema

La auditoría de arquitectura en `nuevo.md` identificó tres riesgos operacionales críticos en la integración MQTT:
1. **Exposición del Broker en Instalación (H1)**: El script instalador configuraba Mosquitto escuchando en `0.0.0.0:1883` con `allow_anonymous true`, permitiendo a cualquier nodo en la red local emitir transmisiones LoRa sin autenticación.
2. **Pérdida de Metadata y Reejecución por Mensajes Retenidos (H2)**: Las funciones `_on_message` en `MeshCoreMqttClient` y `ExternalMqttClient` descartaban las banderas `msg.retain` y `msg.dup`. Si un cliente publicaba una orden de transmisión (`.../tx`) con el flag `retain=True`, cada reinicio o reconexión del bridge volvía a recibir el mensaje y transmitía nuevamente el paquete por RF, violando las restricciones de airtime.
3. **Falta de Idempotencia de Aplicación (H2)**: Workflows en n8n que reintentaban ante timeouts de red producían transmisiones duplicadas por radio.
4. **Dispersión y Desalineación de Tópicos (H3)**: Módulos como `src/rx_router.py`, `src/bridge_core.py` y `src/admin/*` publicaban eventos usando constantes globales fijas (`config.TOPIC_*`), de modo que un cambio de `TOPIC_PREFIX` en tiempo de ejecución rompía la correlación entre órdenes y confirmaciones.

## Factores de Decisión

1. **Seguridad de Red en Entornos Domésticos y LAN**: La estación suele convivir con clientes n8n en el host o en la misma red local. El broker Mosquitto debe exigir credenciales obligatorias (`allow_anonymous false`) y listas de control de acceso (ACL).
2. **Protección del Espectro LoRa frente a Ráfagas**: Prohibir categóricamente que mensajes MQTT marcados con `retain=True` puedan activar transmisiones de radio o comandos administrativos.
3. **Idempotencia sin Alterar Workflows Legados**: Brindar una migración fluida: permitir que integraciones antiguas sin `command_id` sigan funcionando (con advertencias estructuradas), mientras que integraciones modernas con `command_id` obtengan deduplicación estricta y detección de conflictos.
4. **Prevención de Fugas de Memoria y Timers**: Mantener la regla inmutable contra timers en memoria para limpieza de datos; la poda del ledger debe ser determinista e insert-triggered con un tope de 10 000 filas.

## Decisión

1. **Endurecimiento de Mosquitto e Instaladores (`F1.1`)**:
   - `install.sh` e `install.ps1` configuran Mosquitto con bind explícito en la red y autenticación obligatoria (`allow_anonymous false`), generando o solicitando usuario/contraseña dedicados para el bridge y para integraciones externas (n8n).
   - Retiro de `Wants=mosquitto.service` y `After=mosquitto.service` del servicio systemd principal `meshcore-bridge.service` para desacoplar el ciclo de vida del bridge de la presencia local de un broker.
2. **Rechazo Estricto de Mensajes Retenidos (`F1.2`)**:
   - El adaptador MQTT inspecciona `msg.retain`. Si el mensaje está dirigido a tópicos de acción (`/tx`, `/send`, `/admin/*`) y `msg.retain == True`, se descarta inmediatamente emitiendo un log de advertencia, sin encolar ninguna tarea en `MqttDispatcher` ni enviar paquetes a la radio.
3. **Ledger Transaccional de Comandos e Idempotencia (`F1.2`)**:
   - Se crea en SQLite la tabla `command_ledger`:
     ```sql
     CREATE TABLE IF NOT EXISTS command_ledger (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         station_id TEXT NOT NULL,
         integration_scope TEXT NOT NULL,
         command_id TEXT NOT NULL,
         fingerprint TEXT NOT NULL,
         status TEXT NOT NULL, -- 'admitted', 'dispatching', 'completed', 'failed', 'uncertain'
         result_payload TEXT,
         created_at REAL NOT NULL,
         updated_at REAL NOT NULL,
         UNIQUE (station_id, integration_scope, command_id)
     );
     CREATE INDEX IF NOT EXISTS idx_command_ledger_lookup 
         ON command_ledger (station_id, integration_scope, command_id);
     ```
   - **Regla de Poda Determinista**: Al insertar, si la cantidad de filas supera 10 000, se eliminan las más antiguas sin necesidad de timers en segundo plano.
   - **Modo Legado**: Órdenes sin `command_id` se procesan normalmente con garantías limitadas y registro en log.
   - **Mapeo de Estados**: Si una orden con el mismo `command_id` y misma huella ya está en progreso o completada, se retorna el estado previo sin re-transmitir. Si la huella no coincide, se rechaza por conflicto.
4. **Resolvedor Unificado de Tópicos (`MqttTopics`, `F1.3`)**:
   - Se implementa `MqttTopics` en `src/integrations/mqtt/topics.py` como autoridad única para construir tópicos según el prefijo configurado.
   - `rx_router`, `bridge_core`, `system_handler` y `admin_handlers` derivan sus tópicos a través del resolvedor de la estación en lugar de constantes estáticas globales.

## Consecuencias

- **Positivas**:
  - Inmunidad total contra bucles de ráfagas provocados por mensajes MQTT retenidos.
  - Idempotencia comprobable para automatizaciones n8n y Home Assistant.
  - Coherencia completa de tópicos ante cambios de configuración dinámica.
- **Negativas / Compensaciones**:
  - Los clientes n8n en la LAN deben configurar credenciales de usuario/contraseña para conectar con el broker.
