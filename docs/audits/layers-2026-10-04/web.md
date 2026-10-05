# Auditoría por capas: Web, contratos y privacidad — 2026-10-04

Revisión base: `c9b2d3c` (checkout de la tarea). Auditoría de sólo lectura de producción;
se añadieron únicamente reproducciones y este informe. Skills aplicadas:
`contract-openapi-sync`, `security-code-auditor`, `html-css-modern-js` y
`web-browser-inspection`. No se conectó a radios físicas, MQTT operativo, `.env`
ni a una estación existente en el puerto 8080.

## Alcance y método

Capas recorridas: SPA → `fetch` / EventBus → HTTP / autenticación → router →
controllers → adaptador virtual, y RX SDK → PacketBuffer → REST / WS → Sniffer.
Se examinaron estado confirmado frente a borradores, cancelación lógica de
respuestas, persistencia IndexedDB, clasificación LOCAL/REPEATER, secretos,
resolución de rutas y parsers. El inventario JSON distingue inspección dirigida
de inventario estático; no afirma revisión manual de cada línea de cada fichero.

Las reproducciones importan módulos JS reales en Chromium; los escenarios de
estado usan DOM y respuestas controladas dentro del navegador de la estación
virtual propia. La reproducción de privacidad atraviesa `bridge.on_mesh_event`,
el router RX, el búfer real y las exportaciones reales. Sólo las respuestas de
autenticación y recarga de mapas se comprueban además mediante sockets HTTP.
Los escenarios no miden carga real, tiempos en SBC ni interoperabilidad RF.

Comando ejecutado:

```powershell
.venv/Scripts/python.exe -m pytest tests/audit_layer_web_2026_10_04.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/layers-2026-10-04/web-final-tmp --junitxml tests/artifacts/layers-2026-10-04/web-reproductions.xml
```

Resultado: **13 reproducciones aprobadas** (11 defectos, dos casos de potencia,
un control positivo de roles). Estas expectativas describen los defectos
vigentes; aprobarlas demuestra su reproducción, **no que la aplicación esté
corregida**. El archivo no lleva prefijo `test_`, por lo que no se recoge en la
suite mantenida normal. Un primer intento falló al crear el directorio padre
del `basetemp`; se creó. Chromium produjo `spawn EPERM` bajo sandbox y la
ejecución elevada fue autorizada por el entorno. Son incidencias del harness,
no defectos del producto. Ruff del harness: correcto.

## Problemas confirmados

### WEB-01 — P1: respuestas CLI con secretos llegan al Sniffer y exportaciones

- Fuente: `src/rx_router.py:315` / `:320` / `:335`; `src/packet_buffer.py:128`,
  `:147`; `src/web/http_server.py:587`–`:616`.
- Pasos: registrar un repetidor virtual; inyectar `CONTACT_MSG_RECV`, `txt_type=1`,
  texto `af|synthetic-audit-private-credential`; hacer que el waiter de administración
  lo reconozca como respuesta sensible; esperar el despacho; consultar el búfer,
  WS `rf_packet` y JSON/CSV/PCAP; configurar clave API y consultar `/api/packets`
  sin cabecera ni query de autenticación.
- Esperado: la respuesta privada llega al waiter; ninguna copia pública
  contiene el secreto, incluidos texto, payload y representación hexadecimal.
  Las lecturas de capturas sensibles necesitan una política de autorización explícita.
- Observado: el evento semántico `repeater_response` está redactado, pero captura,
  WS RF, JSON, CSV y PCAP contienen el secreto. GET `/api/packets` devuelve 200
  sin clave aunque `BRIDGE_API_KEY` está configurada. La copia estructurada
  elimina claves llamadas `password`, pero no un secreto alojado en `text`.
  PacketBuffer reconstruye además bytes crudos a partir del texto cuando no hay
  bytes de radio disponibles, convirtiendo la fuga también en `raw_hex` / PCAP.
- Causa: la captura pública ocurre antes del procesamiento contextual del comando;
  se hace `deepcopy` antes de redactar la respuesta semántica. La lista de lecturas
  protegidas omite capturas y exportaciones de paquetes.
- Corrección propuesta: separar entrega privada y copia pública antes del primer
  sink; clasificar CLI/sensibilidad por nodo y contexto sin consumir el waiter dos
  veces; redactar o excluir texto, payload y bytes de CLI sensibles. Definir un
  almacén de captura cruda privilegiado si es necesario, con autenticación y
  retención explícitas; proteger GET capturas/export. Probar el recorrido completo,
  no sólo `_handle_mesh_msg_common`.
- Evidencia: `web-packet-secret.json`; reproducción
  `test_sensitive_cli_leaks_through_packet_capture`.
- Contradicción documental: `docs/AGENT_ACTIVITY_REPORT.md:2144` declara
  `/api/packets` como lectura protegida; el código actual no la protege. No afecta
  a la corrección anterior del evento semántico: descubre un sink previo distinto.

### WEB-02 — P2: una clave API válida con símbolos impide conectar WebSocket

- Fuente: `src/web/static/js/core/websocket.js:25`; `src/web/http_server.py:695`–`:700`.
- Pasos: establecer una clave sintética con `+`, `%` y `&`; usar el valor codificado
  con URL encoding, como hace la SPA, en REST y en upgrade WS.
- Esperado: autenticación equivalente en ambos transportes.
- Observado: REST 200, WS 401. La SPA reintentaría periódicamente sin poder conectar.
- Causa: REST usa `parse_qs`; WS separa strings y compara el valor todavía codificado.
- Corrección: compartir extracción de credenciales por `urllib.parse.parse_qs`,
  conservar `hmac.compare_digest`; añadir caracteres reservados y Unicode al contrato.
- Evidencia: `web-ws-key.json`; `test_ws_encoded_api_key_rejected`.

### WEB-03 — P2: recarga de mapas por GET elude la protección de mutaciones

- Fuente: `src/web/api_router.py:757`; `src/web/http_server.py:585`–`:616`.
- Pasos: configurar clave API, solicitar GET y POST `/api/map/reload` sin clave;
  observar la invocación de `reload_mbtiles` mediante un doble aislado.
- Esperado: una operación de reindexación tiene la misma autorización cualquiera
  que sea su alias y método admitido; GET no modifica estado.
- Observado: GET 200 e invoca recarga; POST 401 y no invoca recarga.
- Impacto: un visitante puede solicitar trabajo de reindexación sin permiso;
  su coste real depende del volumen de archivos. No se hizo ataque de carga.
- Corrección: dejar GET como lectura y usar sólo POST para recargar; si se conserva
  compatibilidad temporal, proteger también GET y alias `/api/map/refresh`.
- Evidencia: `web-map-auth.json`; `test_map_reload_get_bypasses_write_auth`.

### WEB-04 — P2: rutas inexistentes de canales ejecutan escrituras

- Fuente: `src/web/api_router.py:362`; `src/web/controllers/channels_controller.py:102`–`:120`.
- Pasos: POST `/api/channels/does-not-exist` con índice 6 válido y nombre de auditoría.
- Esperado: 404 y cero órdenes al dispositivo.
- Observado: 201, una llamada `set_channel`, canal creado y persistido en archivo temporal.
- Causa: el router usa `startswith`; el controlador sólo distingue dos subrutas,
  luego deriva por método sin validar que la ruta sea `/api/channels`.
- Corrección: tabla explícita ruta/método; devolver 404 para subrutas desconocidas,
  405 sólo para recursos existentes. Aplicar el mismo examen a `/api/contacts`.
- Evidencia: `web-unknown-route.json`; `test_unknown_channel_route_performs_mutation`.

### WEB-05 — P2: un rechazo de envío de chat se oculta y borra el borrador

- Fuente: `src/web/static/js/modules/chat.js:1397`, `:1434`, `:1450`–`:1494`.
- Pasos: escribir texto; devolver HTTP 503 / `Radio disconnected` desde fetch controlado.
- Esperado: aviso visible, estado fallido y conservación/recuperación del texto;
  no aparentar que el mensaje sigue en una cola que el backend rechazó.
- Observado: textarea vacío, mensaje `queued` en memoria y persistencia, cero toasts.
- Causa: sólo hay rama de éxito; la entrada se limpia antes de conocer el resultado.
  El catch de fallo de red sólo escribe `console.warn`.
- Corrección: tratar HTTP, JSON de error y excepción de red; conservar request_id,
  marcar failed y persistirlo, ofrecer recuperación del borrador sin reenvío automático
  ni duplicados. Si el usuario ya escribió otro texto, no sobrescribirlo.
- Evidencia: `web-chat-failure.json`; `test_chat_rejected_http_stays_queued`.

### WEB-06 — P2: historial tardío contamina la conversación activa

- Fuente: `src/web/static/js/modules/chat.js:1084`–`:1127`.
- Pasos: comenzar carga de historial canal 0 y demorarla; cambiar al canal 1 y
  terminar su carga; resolver la primera petición.
- Esperado: canal 1 conserva únicamente su conversación.
- Observado: el encabezado/estado activo continúa en canal 1 y el feed incorpora
  también `OLD CHANNEL`. La misma carrera aplica a DMs y cambios de idioma.
- Causa: el `feedKey` se captura antes del await; después se modifica el DOM
  compartido sin verificar que el usuario continúe en esa conversación.
- Corrección: generación de render y comparación de feed actual después de await;
  conservar el resultado viejo en caché, pero no renderizarlo. Cubrir también
  `clearCurrentChat` frente a historial todavía pendiente.
- Evidencia: `web-chat-race.json`; `test_chat_old_history_overwrites_new_conversation`.

### WEB-07 — P2: la persistencia conserva `queued` tras un envío confirmado

- Fuente: `src/web/static/js/modules/chat.js:1444`, `:1462`;
  `src/web/static/js/core/storage.js:61`–`:73`, `:84`.
- Pasos: enviar a fetch controlado que devuelve status ok y expected_ack;
  leer IndexedDB real después del guardado y de la respuesta.
- Esperado: estado `sent` en memoria y persistencia mientras no llega ACK.
- Observado: memoria `sent`; IndexedDB `queued`, aunque el expected_ack se actualiza.
  Tras una recarga, el indicador vuelve a «En cola» para un mensaje transmitido.
- Causa: saveMessage copia el estado previo a la respuesta y la rama exitosa no
  invoca updateMessageStatus. El método ya existe y puede reutilizarse.
- Corrección: persistir `sent` de forma ordenada tras creación del registro;
  no degradar un mensaje que un ACK concurrente ya convirtió en delivered.
- Evidencia: `web-chat-persist-status.json`; `test_storage_successful_tx_saved_as_queued`.

### WEB-08 — P2: snapshot vacío de nodos deja el directorio anterior

- Fuente: `src/web/static/js/modules/nodes.js:189`–`:216`.
- Pasos: iniciar con un nodo conocido; GET devuelve status ok, data [], total_count 0.
- Esperado: renderizar snapshot vacío y retirar tarjetas/estado conocido anterior.
- Observado: cero renderCalls y un nodo antiguo en knownNodes.
- Causa: se llama al render sólo cuando `allNodes.length > 0`, confundiendo un
  resultado vacío válido con un fallo de lectura.
- Corrección: distinguir consulta completa exitosa de error/paginación parcial;
  reconciliar un snapshot vacío válido. No borrar el directorio si el servidor falla.
- Evidencia: `web-nodes-empty.json`; `test_node_snapshot_empty_is_not_rendered`.

### WEB-09 — P2: la potencia remota observada se sustituye por límites supuestos

- Fuente: `src/web/static/js/core/utils.js:202`–`:222`;
  `src/web/static/js/modules/repeater.js:1313`–`:1324`.
- Pasos: poblar un nodo remoto sin identificación de placa, con tx_power 27 y -9.
- Esperado: mostrar el valor observado y mantener su precisión; no inventar capacidad.
- Observado: resumen 27 dBm / slider 22 dBm; resumen -9 dBm / slider 2 dBm.
- Causa: heurísticas frontend suponen min 2 / max 22 en hardware desconocido y
  hacen clamp incluso de valores recibidos del dispositivo. La API remota
  corregida valida rango de protocolo y máximo observado, sin asumir ese máximo.
- Corrección: separar valor recibido y capacidad; dar prioridad a límites confirmados;
  no modificar lecturas para encajar en un slider. Para capacidad desconocida,
  usar una edición que represente el dominio del protocolo y explique la incertidumbre.
  Revisar también límites mínimos inferidos por nombre de placa.
- Evidencia: `web-tx-power-27.json`, `web-tx-power--9.json`;
  `test_remote_power_observation_clamped` (2 casos).

### WEB-10 — P2: al recargar el Sniffer se omiten las capturas más recientes

- Fuente: `src/web/static/js/modules/sniffer.js:285`–`:296`;
  `src/packet_buffer.py:170`–`:184`.
- Pasos: registrar 250 capturas; consultar la URL literal usada al iniciar la SPA:
  `/api/packets?limit=200`.
- Esperado para una vista «en vivo, recientes primero»: recuperar los últimos 200.
- Observado: respuesta packet 0…199; los 50 últimos no están en el snapshot,
  aunque el total es 250. Invertir la lista en JS cambia el orden, no recupera los omitidos.
- Causa: paginación del backend comienza por los más antiguos; cliente no usa
  offset ni orden/tail. No es incorrecto paginar ascendente: lo incorrecto es el
  contrato entre esa paginación y el listado inicial de «más recientes».
- Corrección: parámetro documentado order/tail o solicitar offset correspondiente
  con snapshot/cursor consistente; evitar paginar arbitrariamente mientras entran paquetes.
- Evidencia: `web-sniffer-oldest.json`; `test_reload_sniffer_uses_oldest_200`.

### WEB-11 — P2: snapshot HTTP del Sniffer pisa eventos recién recibidos

- Fuente: `src/web/static/js/modules/sniffer.js:292`, `:301`–`:307`; patrón similar
  `fetchSystemLogs` asigna todo el array en `:617`.
- Pasos: demorar GET inicial; recibir RF packet 2 vía onRfPacketReceived; resolver
  GET con snapshot anterior que sólo contiene packet 1.
- Esperado: conservar ambos sin duplicados.
- Observado: rfPackets termina sólo con packet 1; desaparece packet 2.
- Causa: asignación reemplaza array mutado por stream mientras la petición estaba pendiente.
- Corrección: reconciliar por packet_id/sesión y preservar eventos posteriores
  al snapshot; análogo para logs con identificador/generación. Verificar clear y
  reconnect: no resucitar datos borrados desde respuestas obsoletas.
- Evidencia: `web-sniffer-race.json`; `test_sniffer_pending_snapshot_drops_live_packet`.

## Control positivo y falsos positivos descartados

`ContactsController._contact_validation` consulta el rol existente del registro,
no sólo el rol enviado por el cliente. POST con clave de repetidor existente y
rol omitido devuelve 400 `repeater_contact_forbidden`, cero llamadas SDK y rol
REPEATER conservado. Reproducción `test_contact_infrastructure_guard` y
`web-role-control.json`. La hipótesis inicial de reclasificación se descartó.

La corrección anterior del evento semántico CLI mantiene redacción: WEB-01
demuestra otra ruta que lo precede. Tampoco se afirma fuga general de query API
en logs de acceso: `SecurityTrafficInspector.log_http_access` elimina query y
`log_suspicious_traffic` redacta credenciales conocidas. HTTP valida tamaño,
transfer-encoding y JSON objeto; estáticos comprueban pertenencia canónica;
WS rechaza máscara ausente, RSV, tramas de control inválidas y payload excesivo.
Estos controles se identificaron en lectura; no equivalen a un pentest completo.

La candidata discrepancia traceroute se descartó tras seguir
`AdminHandler._handle_traceroute` hasta `TracerouteExecutor.execute`: el executor
sí retorna `total_hops`, `total_rtt_ms` y `hops_breakdown`
(`src/admin/traceroute_executor.py:119`–`:121`), consumidos por MapModule.
El log del controller usa `hop_count` como fallback y puede mostrar 0; eso no
demuestra que la respuesta REST o la gráfica carezcan de los campos correctos.

## Código en desuso, duplicación y optimización

Se buscó cada nombre en `src`, `tests`, `scripts` y `docs`, examinando también
dispatchers. La ausencia léxica se interpreta según contexto; no se borró código.

| Símbolo | Evidencia de llamadas | Clasificación / acción propuesta |
|---|---|---|
| `api_router._safe_int` (`:83`) | Sólo su definición con ese símbolo en api_router; se usa `_parse_bounded_int` para las rutas actuales. Existen homónimos en otros módulos. | Candidato privado a eliminación; comprobar imports externos y compatibilidad antes de retirarlo. |
| `SystemController.get_logs` (`:78`) | Sólo llamadas de tests/test_rest_controllers; HTTP usa LogsController.route_logs. | Duplicación de lógica, método sin tráfico productivo conocido. Reorientar tests al camino efectivo o declarar API interna si se conserva. |
| `LogsController._handle_diagnostics_report` (`:115`) | Llamada desde su route_logs; pero WebAPIRouter capta ambas rutas report en `_dispatch_system` antes de llegar a LogsController. | Rama de compatibilidad interna, inalcanzable por HTTP actual; unificar renderer y rutas. No es una función sin ningún caller. |
| `SnifferModule.toggleSnifferPause` (`:324`) | Sólo definición; bindings usan setSnifferCapture. Ya identificado en auditoría 2026-10-03. | Wrapper sin consumidor interno conocido; no declarar basura sin decisión de compatibilidad. |
| `EventBus.once` y constantes RADIO_STATUS_CHANGE / NODE_DISCOVERED / CHAT_MESSAGE_RECV / FEED_CHANGED / SETTINGS_SAVED / SYSTEM_LOG_RECV | Sin consumidores productivos léxicos en SPA actual. | API pública reservada/legada; inventariar y decidir si mantener; no confundir nombres SDK homónimos con consumo de esas constantes. |

Costes estáticos que merecen medición, sin afirmar que se haya demostrado un
cuello de botella: `MeshCoreStorage.getMessagesByFeed` hace getAll y slice en JS
(lee todo el historial del feed); actualizaciones de ACK/status recorren cursor
completo en vez de índice por msg_id; getDmConversations hace getAll sobre toda
la base. El límite MAX_FEED_MESSAGES protege RAM, pero no impone retención a
IndexedDB. Bajo historial prolongado crecen trabajo y espacio: medir con una base
virtual representativa, añadir índices y política de retención elegida por usuario.

`SnifferModule.onRfPacketReceived` reconstruye hasta 200 filas visibles por evento;
filtro y reverse se repiten. Las tarjetas de nodos y los módulos grandes combinan
consulta, clasificación, DOM, eventos y persistencia. La optimización propuesta
es por responsabilidad/riesgo medido: conciliación de snapshots/stream primero,
índices y actualización DOM incremental después. Fragmentar archivos sólo por
tamaño no resuelve esas carreras. No se modificaron clases ni métodos en esta auditoría.

## Riesgos y contradicciones pendientes de reproducción específica

1. La búsqueda/listado de logs parsea `search` sin URL decoding en
   LogsController, a diferencia del parser general de query del router. Probar
   búsquedas REST con tildes, espacios y `+`; los filtros en pantalla actualmente
   operan sobre array local, por lo que no se demuestra un fallo de ese input UI.
2. `getHardwarePowerLimits` usa substrings muy amplios (`PA`, `PLUS`, `V1`, `V2`)
   para inferir placas. WEB-09 confirma el caso desconocido; no se comprobó cada
   placa/modelo ni se atribuyen capacidades sólo por etiqueta.
3. Sniffer «Captura OFF» sólo pausa render automático; onRfPacketReceived continúa
   almacenando, contador y export siguen creciendo. Definir si el requisito es
   detener captura del servidor o pausar la vista; no añadir una API de apagado
   global sin considerar otros clientes conectados.
4. Rechazo total de WS fragmentado, permitido por RFC 6455: el parser exige FIN y
   rechaza opcode continuación. Clientes actuales de SPA mandan frames cortos;
   probar otro cliente real antes de afirmar impacto de interoperabilidad.
5. Se permiten orígenes LAN completos aun cuando BRIDGE_ALLOWED_ORIGINS está
   fijado; la clave API sigue siendo la barrera de mutaciones cuando está configurada.
   Modo sin clave permite mutaciones por diseño. Evaluar amenazas/red despliegue,
   sin inventar vulnerabilidad crítica sin escenario y sin cambiar esa política aquí.
6. Algunas interpolaciones de métricas en MapModule traceroute/popup no escapan
   SNR/RSSI/RTT, mientras otros módulos sí escapan. Validación numérica de datos
   de entrada debe acompañar textContent/escape; no se ha demostrado un XSS
   explotable desde radio oficial con esos campos tipados.
7. Chart engine anuncia WCAG AA en comentario global. Inspección DOM y CSS no
   certifica WCAG completo: requieren teclado, lector de pantalla, contraste,
   zoom y escenarios de datos. CSS de ambas variantes usa tokens y overrides;
   no se reabrieron los fallos visuales ya corregidos de logs/diálogos.

## Orden sugerido de corrección y aceptación

1. WEB-01 antes de nuevos despliegues: privatizar CLI sensible y cubrir todos
   los sinks. Aceptación: secreto ausente en WS, REST, JSON/CSV/PCAP/hex, con
   waiter todavía funcional y políticas de auth verificadas.
2. WEB-03/04/02: tabla de rutas/autorización por operación y extractor único de
   credenciales. Aceptación: recursos desconocidos jamás transmiten/escriben;
   aliases no eluden autorización; claves válidas conectan ambos transportes.
3. WEB-05/06/07: máquina de estados de chat y persistencia ordenada. Aceptación:
   HTTP fallo visible/draft recuperable, no duplicar/reintentar RF por su cuenta,
   ACK concurrente no degradado y conversación correcta tras respuestas invertidas.
4. WEB-08/10/11: snapshots completos y streams conciliados por identidad/generación;
   preservar vacíos válidos, últimas capturas, eventos nuevos y clear explícito.
5. WEB-09: representar capacidad real/unknown y valores observados sin clamp.
6. Unificar helpers duplicados sólo después de cerrar contratos; medir historial,
   DOM y clientes lentos con datos virtuales. No prometer que «todas las clases
   son óptimas» a partir de lint o inspección estática.

Después de las correcciones, convertir las reproducciones en regresiones del
comportamiento esperado en archivos `test_`, ejecutar suite mantenida y navegador,
tipado/lint/documentación. Las acciones aquí simuladas no autorizan tráfico RF
real ni nuevos timers, límites de airtime o políticas de retención unilaterales.
