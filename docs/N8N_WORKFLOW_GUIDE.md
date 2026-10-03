# Guía del workflow n8n de MeshCore Bridge

Describe el export [n8n_workflow_meshcore.json](../n8n_workflow_meshcore.json) revisado el 2026-09-29. El JSON exportado es la fuente de configuración del workflow; esta guía no certifica una instancia activa ni resultados actuales de pruebas. Véase el [índice documental](README.md).

## 1. Flujo y nodos reales

El export contiene 14 nodos. RX entra por MQTT, se desempaqueta/normaliza, se marca la duplicación, se filtran duplicados mediante un nodo IF y se enruta por `event_type`. Un publicador común utiliza `$json.topic` o el fallback `meshcore/tx`. La rama meteorológica comienza en un Schedule Trigger independiente.

| ID | Nombre en el export | Función |
| --- | --- | --- |
| 1 | `MQTT Trigger (MeshCore RX)` | Se suscribe a `meshcore/rx/all`. |
| 2 | `Deduplicar y Validar` | Desempaqueta `message`/`data`, normaliza, descarta origen local y prefijos de bot, marca duplicados. |
| 3 | `¿Es Mensaje Nuevo?` | Permite continuar cuando `is_duplicate` es false. |
| 4 | `Enrutar por Tipo` | Enruta `public`, `channel`, `direct`, `telemetry`, `node_advert`, `rf_log` y `repeater_response`; este último usa la rama DM/Admin. |
| 5 | `Procesar Canal Público` | Comandos de tiempo, ayuda, ping textual, clima y eco de fallback en canal 0. |
| 6 | `Procesar Canal Secundario` | Eco en el índice del canal recibido. |
| 7 | `Procesar DMs y Admin` | `/status`, `/admin` y eco DM; comandos admin requieren whitelist. |
| 8 | `Procesar Telemetría CayenneLPP` | Normaliza campos y calcula flags de alerta. |
| 9 | `Procesar Anuncio de Nodos` | Prepara `node_discovered`, preservando el rol recibido. |
| 10 | `Procesar Sniffer RF` | Prepara datos de diagnóstico RF. |
| 11 | `Publicar a MQTT (TX / Admin)` | Publica el objeto JSON al tópico dinámico indicado. |
| 12 | `Schedule Trigger (Cada 6h - 00:00, 06:00, 12:00, 18:00)` | Programa la rama meteorológica. |
| 13 | `Consultar Clima (Lehigh Acres, FL)` | Consulta Open-Meteo para 26.6254, -81.6248, con parámetro `timezone=America/New_York`. |
| 14 | `Formatear Reporte Estado y Clima` | Produce broadcast en canal 0 con métricas meteorológicas. |

El Schedule Trigger usa `0 0,6,12,18 * * *`: cuatro ejecuciones al día. El export no fija una zona horaria de workflow; la zona de ejecución depende de la configuración de n8n. El comentario de código dice UTC, pero el parámetro de zona de Open-Meteo y el formateo del texto no establecen la zona del scheduler. Configurar y verificar la zona de n8n antes de activar esta rama. La referencia antigua a intervalos de 30 minutos no corresponde al export actual.

## 2. Contratos MQTT

El bridge publica el stream normalizado en `meshcore/rx/all`; los tópicos específicos incluyen `meshcore/rx/public`, `meshcore/rx/channel/ch_<idx>`, `meshcore/rx/direct/<sender_id>`, `meshcore/rx/telemetry`, `meshcore/rx/nodes` y `meshcore/rx/log`. Un evento advert puede tener tipo `node_advert` sin que exista un tópico literal `meshcore/rx/advert`.

Un TX de chat tiene este formato, con aliases dobles conservados por el workflow:

```json
{
  "topic": "meshcore/tx",
  "request_id": "n8n_example",
  "target": "broadcast",
  "to": "broadcast",
  "channel_index": 0,
  "channel_idx": 0,
  "text": "Mensaje"
}
```

Administración local usa `meshcore/admin/cmd`, con `action` y parámetros. Para repetidores se publica en `meshcore/admin/repeater/<id>/cmd`:

```json
{
  "topic": "meshcore/admin/repeater/<id>/cmd",
  "request_id": "n8n_admin_example",
  "action": "ping_zero",
  "target_node": "<id>"
}
```

El bridge publica resultados TX en `meshcore/tx/status` y resultados administrativos en sus tópicos de estado. `sent` no equivale a entrega universal a receptores. Las credenciales MQTT y permisos de publicación dependen del broker; la API key HTTP del bridge no protege MQTT.

## 3. Comportamiento de los handlers

El canal público implementa `/time`, `/date`, `/datetime`, `/ping`, `/clima`, `/weather` y `/help`; otros textos reciben `[Eco Pub]`. `/ping` devuelve texto desde n8n y no realiza `ping_zero` administrativo. `/clima` informa de la programación, no dispara una consulta de clima en ese handler. `/status` se implementa en DM, aunque aparece en la ayuda pública.

El handler DM admite `/status`, `/admin ping <id>`, `/admin trace <id>`, `/admin repeater <id> <cmd>` y comandos locales `get_config`/`config`, `list_nodes`/`nodes`, `set_name`, `set_power` y `reboot`. Una operación admin puede producir tanto el comando como una respuesta textual al cliente. Los handlers de chat bloquean roles `REPEATER` y `ROUTER`; nunca se debe enviar chat al repetidor ni a la propia clave local.

La telemetría devuelve `telemetry_processed` y marca `is_alert` para batería `<20`, temperatura `>45°C` o duty cycle `>0.8%`. Son umbrales existentes del ejemplo; calcular el flag no equivale a publicar una alarma RF o a persistir métricas en una base de datos. Cualquier conexión nueva de esa salida requiere diseñar el destino y revisar impacto.

## 4. Deduplicación, identidad y límites actuales

`$getWorkflowStaticData('global').messageCache` guarda firmas de tipo, remitente, canal y texto. La ventana de deduplicación textual es 30 segundos y la limpieza elimina entradas mayores de 60 segundos. No es un rate limiter general para todos los comandos ni limita por sí solo el eco de mensajes distintos.

El normalizador descarta `is_outgoing`, `is_local`, rol `LOCAL`, remitente literal `local` y prefijos de respuesta de bot. Esa guarda no compara por sí sola cualquier clave pública entrante con la clave local configurada: depende de los campos normalizados que entregue el bridge.

La clasificación canónica procede de `FirmwareAdvertType` (0/1 CLIENT, 2 REPEATER, 3 ROOM, 4 SENSOR) y `is_repeater`, descartando cualquier inferencia heurística basada en nombres de nodo.

`ADMIN_WHITELIST` restringe la autorización exclusivamente a claves públicas / IDs de nodo canónicos (`senderId`), sin evaluar nombres de nodo para prevenir suplantación de identidad.

Los textos de clima y comandos respetan el presupuesto de canal (< 120 bytes de payload) para garantizar compatibilidad con el límite MTU oficial del transceptor incluso con nombres de estación configurados. `/time` formatea la hora UTC canónica mediante `toISOString()`.

## 5. Importación y cambios

Importar el JSON en n8n y configurar credenciales del broker, prefijo de tópicos, whitelist, ubicación y zona del Schedule Trigger. Guardar y activar sólo las ramas deseadas. Importar el archivo no actualiza automáticamente una instancia ya activa; los cambios deben trasladarse al workflow de esa instancia.

Antes de alterar respuestas automáticas, umbrales o periodicidad, aplicar [AGENTS.md](../AGENTS.md): estimar paquetes/airtime, revisar bucles y origen propio, estudiar persistencia del último disparo y acordar límites con el usuario. La programación cada seis horas describe el ejemplo existente, no autoriza nuevos timers ni su activación durante mantenimiento del repositorio.

Las suites del parser/workflow son comprobaciones disponibles bajo demanda. Esta guía se basa en inspección del export y no afirma que se hayan ejecutado pruebas o que una instancia externa esté conectada.
