# FastAPI: WebSocket, SPA y cartografía preparatorios de fase 4

> Snapshot histórico de preparación. El checkout posterior selecciona ASGI y retiró el servidor nativo (`933ccce`). Véanse la [auditoría actual](../audits/2026-10-09-layer-audit.md) y la [fase 6 rectificada](PHASE_6_REPORT.md). Las puertas de ejecución continúan pendientes.

Fecha: 2026-10-09. Base documental: fase 3 publicada en `8d5bbdf` y checkout
con cambios anteriores conservados. Estado: **adaptadores preparados y revisados
estáticamente para el candidato inactivo**. La selección del core permanece en
`MeshCoreWebServer`; `application_contract_ready=False` no se eleva por disponer
de rutas o de un listener. Las puertas de aceptación y adopción siguen pendientes.

## Coordinación y propiedad

El líder coordina especialistas de WebSocket, archivos/cartografía y revisión
de contratos/seguridad, e integra fábrica, protocolos y documentación. Se
aplican las skills de Python, concurrencia, contratos, seguridad y gobernanza
documental. La instrucción del usuario de continuar sin suites mantiene suspendida
la QA ejecutable. Los especialistas no publican commits ni cambian el frontend,
datos operativos, dependencias, referencias oficiales o selección del servidor.

| Componente | Propiedad y responsabilidad |
| --- | --- |
| [asgi_ws_hub.py](../../src/web/asgi_ws_hub.py) | Especialista WS: clientes, historial, métricas pasivas, tareas y cierre del hub |
| [asgi_assets.py](../../src/web/asgi_assets.py) | Especialista de archivos: estáticos/SPA, caché, gzip y lectura de tiles prestados |
| [asgi_server.py](../../src/web/asgi_server.py) | Líder: registro en la fábrica opcional, lifespan y presupuesto común de apagado |
| [asgi_websocket.py](../../src/web/asgi_websocket.py) | Líder: seam de Uvicorn SansIO, idle RFC, presión de envío y aborto de transporte |
| [asgi_http.py](../../src/web/asgi_http.py) | Seam heredado de fase 1: transferencia del upgrade y bytes coalescidos, sin cambios en esta etapa |
| [asgi_security.py](../../src/web/asgi_security.py) | Perímetro existente: Origin, credenciales, cupo reservado y cabeceras |
| [WEB_CONTRACT_BASELINE.md](WEB_CONTRACT_BASELINE.md) | Contrato previo y diferencias que exigen verificación |
| [PHASE_3_REPORT.md](PHASE_3_REPORT.md) | Registro REST y límites heredados de la fase anterior |

El router y `ApiContext`, bridge, buffers, colas, radio, MQTT y
`router.map_tile_service` se **prestan**, sin reconstrucción. El hub posee sus
peers, locks y tareas web; el adaptador de archivos posee únicamente su caché y
lock de hilo. Ninguno cierra el servicio cartográfico ni recursos del bridge.
El propietario de composición debe cerrar mapas después del transporte cuando
se autorice la adopción; prestar el servicio no transfiere esa obligación.

La fábrica opcional recibe `shutdown_budget_s` del propietario y un directorio
estático opcional. Arranca el hub dentro del lifespan y detiene sus tareas con
el mismo deadline del servidor; el hook de aborto pertenece al protocolo de
cada conexión. Registrar componentes no inicia un segundo servicio del bridge.

## WebSocket y cliente existente

La SPA sigue abriendo `/ws` en el mismo host, usando ws/wss y query `api_key`
desde las claves existentes de localStorage. No se renombra ningún campo ni
se requiere cambiar JS/CSS/HTML. El candidato conserva la política raw de
autenticación y Origin del perímetro, el orden Origin → cupo → clave y la
reserva de 32 conexiones iniciada en fase 1. Esta reserva corrige el chequeo
nativo susceptible de carrera durante el handshake; no se añade un límite nuevo.

Se registra `WebSocketRoute('/{path:path}', hub.endpoint)` para scopes WS de
cualquier target, conservando la amplitud de rutas de upgrade del nativo; `/ws`
es la ruta del cliente, no una restricción nueva. La validación del handshake
estándar sigue perteneciendo al backend. En un scope WS, el perímetro no
reproduce el parsing JSON del cuerpo HTTP previo al upgrade que hacía el servidor
manual: ese detalle del ingreso no se declara equivalente.

El hub acepta únicamente después de los controles del perímetro. Envía primero
`event_type=ws_connected` y luego `type=event=metrics_update`, ambos mediante
`json.dumps(..., default=str)`. El peer pasa a `ready=True` al completar esos
envíos iniciales bajo su lock. Los broadcasts seleccionan sólo peers listos:
un evento recibido durante el inicio puede quedar en historial sin entregarse
a ese peer. No se introduce una cola, replay, ACK de entrega o garantía de
reconstrucción de eventos perdidos. Los clientes no listos tampoco disparan
el broadcast periódico de métricas.

El catálogo de eventos permanece abierto. Se conservan discriminadores y
contenedores de productores, sin `response_model`, unión cerrada de DTO ni
normalización global de `type`, `event_type` o `event`. Los mensajes binarios,
JSON inválido/no objeto y tipos entrantes desconocidos se ignoran. El único
mensaje con efecto de aplicación es `{"type":"ping"}` y recibe
`{"type":"pong","timestamp":...}` con epoch entero en segundos; el timestamp
entrante de JS no se refleja. No se añade TX/chat/admin por WebSocket.

`broadcast_event` registra el evento **una sola vez** en el router antes de
seleccionar conexiones, incluso sin clientes. El servidor delegado no debe
repetir ese registro. Welcome y métricas iniciales se envían directamente y
no se agregan de nuevo al historial. Las métricas periódicas conservan el timer
`WS_METRICS_INTERVAL_SEC`, default 5 s, y los campos y defaults nativos,
incluido `radio_port` sólo en el estado inicial. Leen contadores, estado local,
cola y estadísticas de airtime; no solicitan telemetría o paquetes por radio.

Las tareas de envío se retienen y se consumen sus resultados. Cada peer tiene
un lock para evitar escrituras de aplicación simultáneas. El broadcast sigue
siendo secuencial y usa el presupuesto existente de 2 s por destinatario,
incluida espera del lock. Un timeout elimina el peer, cancela su tarea y
solicita aborto del transporte; no se reintenta el evento. `stop` y `force_stop`
cancelan exclusivamente tareas propias y comparten el deadline absoluto del
servidor. Tareas que resistan cancelación permanecen retenidas y bloquean un
reinicio prematuro. La cancelación del caller se propaga.

El cierre del peer solicita el frame de cierre y después aborta su transporte,
incluso si el envío ASGI terminó, antes de liberar la reserva perimetral. Así
no queda deliberadamente esperando el timer de cierre de 10 s del backend.
El frame es best effort: abortar puede descartar bytes aún buffered. El nativo
también termina el writer sin esperar confirmación de cierre; esa diferencia
de flush y códigos exige comprobación por socket. El cupo limita reservas de
aplicación WS, no todas las conexiones TCP previas o rechazadas del listener.

El presupuesto es por peer, no global: la latencia agregada puede crecer con
el número de clientes lentos y mantiene esperando al productor que awaita el
broadcast. No se ha implementado `gather`, fan-out concurrente, cola por peer
o deadline global. Cualquier mejora futura debe decidir explícitamente su
semántica de orden, presión y límites y comprobar su efecto en los productores;
no se acredita una mejora de latencia por este port.

## Backend, idle y diferencias de transporte

Uvicorn 0.54.0 con websockets 16.1.1 gestiona handshake y control RFC 6455. Su
semántica debe separarse del lector manual nativo. Un `send` ASGI no es un
`StreamWriter.drain()` ni prueba de recepción del cliente. La integración del
protocolo prepara espera de presión de escritura con el presupuesto heredado
de 2 s; el timeout no acredita que el sistema operativo haya transmitido todos
los bytes. Welcome y Pong JSON conservan ausencia de timeout local; sus tareas
pertenecen al hub y el propietario las cancela al cerrar. No se afirma que el
timeout de broadcasts proteja cualquier envío o recepción de la conexión.

El backend admite fragmentación válida y aplica el límite de 1 MiB al mensaje
reensamblado. El nativo exige FIN, rechaza continuaciones y limita cada frame
a 1 MiB. La cola entrante de SansIO es no acotada: pausar el transporte después
de encolar no demuestra memoria total limitada, pues un callback puede entregar
varios mensajes. No se decidió una capacidad o política de descarte nueva.
Códigos de cierre, control frames, UTF-8 inválido, clave/versión del
handshake y longitud total no se presentan como equivalentes. El handshake
estándar exige condiciones que el dispatcher nativo no verificaba. Desactivar
compresión WS y los keepalive automáticos de Uvicorn evita introducirlos
implícitamente; no demuestra por sí solo paridad con el keepalive anterior.

La preparación del protocolo conserva el idle configurado por
`WS_IDLE_TIMEOUT_SEC`, default 30 s, y envía un **Ping RFC vacío** con escritura
acotada al presupuesto existente de 2 s. No se expulsa por ausencia de Pong
ni se crea un intervalo RF. La observación de actividad del candidato se basa
en chunks del transporte, frente a la espera entre frames del lector manual:
un cliente que gotea un frame parcial puede producir otro comportamiento.
Los timeouts nativos de lectura parcial —10 s por longitud, máscara y payload—
no están portados como deadlines equivalentes del parser SansIO. Deben medirse
y resolverse antes de adopción, sin inventar otro umbral.
El candidato lee el valor idle al crear cada conexión; el lector nativo lo
relee por frame. Cambiar `os.environ` durante una conexión tiene por tanto
alcance distinto. El intervalo de métricas se lee al iniciar su loop en ambos.

Los hooks de protocolo son específicos de las versiones evaluadas y deben
revisarse al actualizar Uvicorn/websockets. El logger privado conserva la
protección de query/credenciales y omite valores de excepción. El upgrade debe
entregar también cualquier cola de bytes que haya llegado junto a las
cabeceras al nuevo protocolo WS. La lectura de fuente de esa transferencia
no sustituye su comprobación por socket.

## Estáticos, SPA y cartografía

Se prepara un `BaseRoute` de tiles y después un catchall HTTP no API en el
router raíz, tras los lotes REST. El fallback REST ya excluye
`/api/map/tiles/`. Los assets no capturan `/api/` ni scopes WebSocket. Se usa
el target raw, se elimina query y se conserva la selección nativa del archivo:
las rutas de navegación y otras inexistentes sin sufijo sirven `index.html`;
un archivo ausente con sufijo devuelve 404 texto. La falta de index conserva
el HTML de inicialización 200. Los estáticos siguen admitiendo todos los
métodos nativos; OPTIONS se resuelve antes en el perímetro.

El worker aplica la guarda nativa de traversal con doble decodificación sólo
para rechazo, sin habilitar nombres percent-decoded nuevos. Comprueba
pertenencia canónica y symlinks contra la raíz, incluido el index del fallback:
esta última comprobación refuerza una brecha anterior. Un filesystem adversarial
todavía puede cambiar entre resolve/stat/read; no se certifica eliminación de
TOCTOU ni se sustituye la confianza en el directorio estático administrado.

Resolución, stat, lectura y gzip se ejecutan mediante `asyncio.to_thread`, con
lock privado para el cache. La clave sigue siendo path/mtime, y el cache RAM
heredado sigue sin límite de tamaño ni expulsión. No hay medición de memoria,
latencia o throughput. Cancelar la coroutine que espera `to_thread` no detiene
un worker ya iniciado; lectura o consulta MBTiles puede seguir en vuelo. El
apagado de tareas ASGI no acredita drenaje de esos workers ni permite cerrar
prematuramente el servicio de mapas prestado.

Se conserva ETag SHA256(raw) truncado a 16 hex, compartido por raw/gzip, sus
coincidencias strong/weak/valor incluido y 304 vacío con MIME, Vary y longitud
0. Gzip nivel 6 sólo para texto de más de 256 bytes, si reduce tamaño, usando
la selección nativa de q-values y substring literal `gzip`. HTML conserva
`no-cache, no-store, must-revalidate`; otros archivos `public, max-age=300`.
Los MIME estáticos mantienen incluso el charset añadido a binarios. HEAD
conserva longitud de representación seleccionada y el perímetro suprime todos
los cuerpos: extender esa supresión a errores corrige inconsistencias nativas.

`/docs`, `/redoc` y `/openapi.json` quedan reservadas con 404, incluidas variantes
con slash final. Evitar el fallback SPA 200 para las dos primeras es una decisión
preparatoria explícita; no se habilita documentación por ese registro. Fase 5
debe montar documentación autenticada y revisar sus rutas auxiliares.

GET `/api/map/tiles/{z}/{x}/{y}.ext` sigue siendo público y binario. Se acepta
al menos tres segmentos, se interpreta y antes del primer punto, y se ignoran
extensión solicitada y segmentos adicionales. Zoom 0..22 y coordenadas dentro
de `2**z`; entrada inválida o contenido ausente devuelve 404 vacío `image/png`.
Los métodos distintos de GET, incluido HEAD, conservan 405 JSON. Éxito requiere
200 y bytes no vacíos, mantiene MIME real y `public, max-age=86400`, sin ETag,
charset ni compresión HTTP adicional. `MapTileService` conserva búsqueda XYZ,
MBTiles TMS/XYZ, SQLite readonly y su lock existente. Los bytes PBF con magic
gzip siguen sin `Content-Encoding: gzip`, discrepancia previa pendiente de
decisión; no se recompimen accidentalmente ni se fija PNG para todo éxito.

La declaración binaria completa el catálogo funcional previsto de 141
operaciones REST sobre 109 patrones, incluidos alias: las 140 operaciones JSON
de fase 3 más GET tiles. Son conteos de contratos preparados, no evidencia de
matching ejecutado ni un conteo de los targets admitidos por el catchall WS/SPA.

## Impacto en malla

1. **Airtime:** no se añade envío de radio. Tiles y assets leen archivos;
   métricas leen memoria. Ping RFC y heartbeat JSON usan exclusivamente WS.
2. **Feedback/reintentos:** el historial se registra una vez y se conserva la
   entrega de eventos existentes. No hay publicación MQTT nueva, reintento de
   broadcast, TX WS ni scheduler de consultas. Los roles LOCAL/REPEATER y sus
   restricciones continúan en el dispatcher y los servicios prestados.
3. **Guardado/timers:** no se reconstruyen gestores, configuración o cooldowns
   de radio. Los timers web ya existentes no se convierten en timers de malla;
   sus valores provienen de la configuración nativa, sin fijar otros límites.

## Evidencia estática y aceptación pendiente

La revisión permitida comprende lectura de fuentes nativas/candidatas y wheels
evaluados, AST con gramática Python 3.10, símbolos, referencias y diff. No se
ejecutan pytest/cobertura, mypy, Ruff, navegador, imports/construcción del
candidato, handlers, servicios, broker o radio. No se ha certificado matching,
socket, handshake, entrega de eventos, cierre, rendimiento o seguridad completa.

El [registro estático](PHASE_4_ADAPTER_REGISTRY.json) conserva fuentes y hashes
del checkout de esta etapa, símbolos con líneas, conteos declarativos y puertas
pendientes. Las referencias de fases anteriores mantienen sus snapshots históricos;
este registro no transforma preparación de código en aceptación operativa.

La comprobación final del líder parseó 14 fuentes Python con gramática 3.10,
cotejó 15 hashes y las firmas de tres clases en wheels locales, y comprobó
158 enlaces locales en siete documentos sin destinos ausentes. El AST conserva
90 declaraciones canónicas JSON; los archivos de catálogo/router/adaptador
REST coinciden con el snapshot de fase 3, que acredita los conteos de alias.
Sólo hay una llamada de registro de historial entre hub y servidor delegado.
Las claves de métricas coinciden estructuralmente: 22 periódicas y 23 iniciales;
constantes de bienvenida coinciden. Estos controles no ejecutaron funciones.
El registro explicita 16 grupos de aceptación pendientes.

Antes de aceptar: autorizar y verificar REST/WS/tiles/assets en una estación
virtual aislada; cubrir welcome/initial y ready gate, historial sin duplicados,
consumidores JS, auth/Origin/cupo concurrente, control/fragmentación/idle/parcial,
clientes lentos, cancelación y reinicio; ETag/gzip/HEAD/fallback/traversal/symlink,
MBTiles temporales TMS/XYZ/PBF y ownership de workers/maps. Además permanecen
las puertas de instalación/lifecycle y fases previas. Documentación autenticada,
perfiles medidos, rollback y cambio de servidor por defecto pertenecen a fases
5–6; el candidato continúa inactivo.
