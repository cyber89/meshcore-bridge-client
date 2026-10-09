# Futuro de MeshCore Bridge: evaluación y plan condicionado de FastAPI

**Estado:** preparación autorizada e iniciada por fases; adopción de producción pendiente de paridad y verificación.

**Fecha de revisión:** 2026-10-09; revisión inicial 2026-10-08.

**Versión declarada implementada:** 3.0.0; 3.1.0 era una versión objetivo de la guía inicial, no una release aprobada.

**Base inspeccionada:** HEAD `558385ad77afb8e691252c037dacb76e730b51db` y el árbol de trabajo existente. Había modificaciones ajenas sin commit: los hallazgos describen ese checkout, no sólo el commit.

**Alcance inicial:** reunión técnica de los roles 0 a 7 y del rol 8 propuesto; revisión documental publicada en `457903d`. **Continuación autorizada:** catálogos y dependencias de fase 0, infraestructura de fase 1 publicada en `e8a7030`, seguridad perimetral publicada en `9eead69`, DTO/errores de fase 2 publicados en `42f7104` y registro REST de fase 3 preparado el 2026-10-09. Los candidatos se descargaron para inspección, sin instalarlos en el entorno del bridge. El usuario indicó «Continúa sin ejecutar suites»; no se arrancan servicios, radio o workflows.

## 1. Dictamen y autoridad

La recomendación técnica es **FastAPI modular con Uvicorn embebido**, manteniendo una instancia del bridge y su event loop. Puede mejorar la declaración de contratos REST, la validación y el mantenimiento del transporte HTTP/WebSocket. Su adopción queda condicionada a cerrar la fase 0 y demostrar paridad, ciclo de vida y viabilidad en las plataformas seleccionadas.

La revisión documental inicial no aprobaba la migración. El usuario autorizó después comenzar las fases; esta autorización permite su preparación, manteniendo las condiciones de adopción. El plan inicial contenía interfaces incompletas, rutas inexistentes, límites de protocolo incorrectos y cifras sin medición. Esta revisión los corrige y registra las decisiones abiertas.

[AGENTS.md](AGENTS.md) fija las reglas operativas; [CONTEXT.md](CONTEXT.md) define el dominio; el [índice documental](docs/README.md) distingue guías vigentes e históricas. Firmware/SDK oficiales determinan el protocolo; el código actual determina las capacidades implementadas. Este documento propone el futuro y no sustituye esas fuentes.

### 1.1 Acta de la reunión técnica

Se emplearon las tres plazas de subagentes disponibles en tandas, con ocho revisores especializados. El principal integra las conclusiones y es el único editor. Las opiniones son asesoramiento técnico, no aprobación del propietario.

| Rol participante | Aporte | Condición o reserva principal |
|---|---|---|
| 0. Orquestación y arquitectura | Integración y revisión secuencial | Separar transporte, cambios funcionales y pruebas autorizadas |
| 1. Protocolo y firmware | Límites binarios, identidad y roles | Bytes UTF-8; sin máximo universal de siete saltos; preservar Companion |
| 2. Backend Python | Dirección modular viable | Contrato completo, estado único, arranque confirmado y apagado compatible |
| 3. QA | Plan de verificación futuro | HTTP en memoria no cubre Uvicorn, WS ni todo el lifespan; suites pendientes |
| 4. Frontend | Migración con paridad | Conservar rutas, errores, heartbeat, historiales, mapas y caché |
| 5. Seguridad | Viable con políticas explícitas | Auth, Origin, límites, secretos y documentación protegida no son automáticos |
| 6. Documentación | Propuesta trazable | Retirar garantías sin evidencia y registrar ADR con estado correcto |
| 7. Instalación y publicación | Viable con resolución comprobada | Backend WS de producción, checker, wheels transitivos y rollback |
| 8. Integración FastAPI/OpenAPI, rol propuesto | Arbitraje ASGI | Adaptador e interfaz mínimos; incorporación formal del rol pendiente |

Se resolvieron tres tensiones: reutilizar controladores frente a reescribirlos todos; preservar contratos frente a imponer validación estricta global; y mantener un propietario del bridge frente a moverlo al lifespan ASGI. Se recomienda reutilizar lógica actual, validar por operación y conservar el propietario del proceso. Seguridad adicional, semántica TX nueva y extracción de estado headless deben quedar como decisiones identificables.

### 1.2 Correcciones de la guía inicial

| Afirmación inicial | Comprobación y corrección |
|---|---|
| 1.229 + 815 líneas, todas de transporte | Conteo físico actual: 1.228 + 814 = 2.042. El router también contiene estado, servicios e historiales |
| 11 controladores REST | Hay diez controladores concretos instanciados, más `BaseController` |
| 42 rutas activas | Conteo no acreditado; inventariar operaciones método/ruta, alias y variantes |
| RSS de 35–90 MB y ahorro neto de 1.700 líneas | Sin mediciones reproducibles; se retiran como garantías |
| SPA en menos de 100 ms y pruebas instantáneas | Sin plataforma/carga/evidencia; medir antes de prometer |
| Pila actual sin extensiones C/Rust | Cuatro dependencias directas no describen transitivas; el SDK de referencia declara `pycryptodome` |
| `uvicorn.Config(..., install_signal_handlers=False)` | No es un parámetro de Config en la fuente 0.30.0 consultada; integración específica de versión |
| Tres métodos idénticos, incluido `broadcast_ws` | Método público actual: `broadcast_event`; hay consumidores de `.router.channels` |
| 160 caracteres y hops 0..7 | Límites por bytes UTF-8 y por campo/operación, sin máximo universal de siete saltos |
| 429 para cualquier cutoff, con Retry-After | Cambia política TX; no inventar un plazo de reapertura |
| Responder sólo request_id al encolar | TX actual espera resultado; admisión asíncrona sería una función nueva |
| Calendario de 21 días desde el 9 de octubre | Sin compromiso sustentado; sustituido por puertas de aceptación |

Evidencia: [servidor](src/web/http_server.py), [router](src/web/api_router.py), [manifiesto](pyproject.toml), [dependencias directas](requirements.txt) y [SDK de referencia](reference/meshcore_py/pyproject.toml). Los conteos físicos no son mediciones de complejidad ni ahorro futuro.

## 2. Alternativas y futuro recomendado

| Alternativa | Beneficio | Coste y límite | Dictamen |
|---|---|---|---|
| A. Mantener asyncio.start_server | Menor cambio inmediato, sin nuevo framework | Mantener parsing/framing WS, validación y documentación propios | Baseline y alternativa válida si fase 0 desaconseja migrar |
| B. FastAPI + Pydantic + Uvicorn | Contratos REST declarativos y generación OpenAPI | Dependencias y adaptación; recursos pendientes de medir | Base funcional recomendada |
| C. Starlette + Uvicorn | ASGI con menos dependencia de Pydantic | Esquemas/validación requieren trabajo adicional | Alternativa si cambian objetivos o viabilidad binaria |
| D. B con estado compartido y frontera web desacoplada | Evolución REST y opción headless con imports diferidos | Resolver acoplamientos y perfil de instalación | Arquitectura objetivo, sin fallback silencioso |

D es una forma de integrar B, no otro framework. Headless es una configuración deliberada. Si se solicita web y falla el bind o faltan dependencias, comunicar el error y aplicar la política de arranque acordada. Durante la transición puede conservarse A para rollback explícito, sin doble propiedad de radio ni dos listeners en el mismo puerto.

FastAPI genera OpenAPI a partir de rutas/modelos: describe lo modelado y no certifica paridad con SPA/n8n ni enumera los eventos WS. [Referencia FastAPI](https://fastapi.tiangolo.com/reference/fastapi/). Starlette también ofrece generación sencilla por docstrings; carece de la misma integración tipada de FastAPI. Por ello C no se descarta de forma absoluta. [Schemas de Starlette](https://starlette.dev/schemas/).

La primera entrega futura sustituye transporte y conserva contratos. Después podrían ampliarse ejemplos para integraciones, reducir validaciones duplicadas y mejorar diagnósticos. Una API TX pendiente/confirmado/fallido, nuevas políticas de seguridad o procesos separados serían propuestas posteriores. No se añaden ahora React/Vue/Tailwind, una base de datos nueva, Redis, un broker interno o nuevos schedulers.

## 3. Invariantes de la arquitectura objetivo

1. Python 3.10 sigue siendo el mínimo. No introducir TaskGroup, asyncio.timeout, typing.Self o except* sin cambiar explícitamente el contrato o declarar backport.
2. FastAPI/Starlette/Pydantic permanecen en la frontera web. Los DTO no sustituyen dataclasses/enums del dominio ni [protocol_types.py](src/protocol_types.py).
3. Clasificación oficial: NONE/CHAT → CLIENT; REPEATER → REPEATER; ROOM → ROOM; SENSOR → SENSOR. LOCAL es identidad del host, no opcode de advert. No inferir roles por nombre.
4. REPEATER/LOCAL se excluyen de contactos y chat; nunca dirigir mensajería a la clave local. Administración de repetidores conserva su vía propia.
5. Una instancia de MeshCoreBridge, un contexto y un propietario de radio/MQTT/colas/timers. Uvicorn embebido con un worker y sin reload del proceso.
6. Mantener SPA Vanilla JS/CSS, MQTT/n8n, ACKs, persistencia JSON y MBTiles.
7. Sustituir únicamente el framing **WebSocket** propio. Companion permanece en el SDK; raw AA/55/ESC/CRC es un formato propio en memoria, no el protocolo RF oficial.

### 3.1 Checklist de impacto RF

| Pregunta obligatoria | Respuesta y condición |
|---|---|
| ¿Cuánto airtime agrega? | El transporte por sí mismo agrega cero paquetes RF. Cada acción conserva la operación actual; abrir docs, esquema, vistas o WS no inicia consultas de radio |
| ¿Puede causar spam o feedback? | Mantener identidad local, deduplicación, cola, prioridades, cooldowns y reintentos. Timeout HTTP no autoriza reenviar: la orden puede haber sido admitida/transmitida |
| ¿Guardar configuración rearma seguridad? | Reutilizar servicios y timestamps persistidos; no recrear RepeaterManager por request/reinicio web. Mantener repeater_cooldowns.json e historial de airtime |

No se proponen intervalos ni umbrales nuevos. Los valores existentes citados abajo son evidencia, no decisiones nuevas. Cambios futuros de radio, notificaciones, reintentos, timers o límites requieren el acuerdo previsto en AGENTS.md. Pings WS y métricas web locales no deben convertirse en consultas LoRa.

## 4. Plan secuencial: una etapa antes de la siguiente

Las fases se entregan secuencialmente. El usuario autorizó comenzar y continuar **sin ejecutar suites**. La lectura estática no declara superadas las puertas operativas. Fase 5 consolida QA; las verificaciones de ejecución permanecen pendientes mientras no estén autorizadas. La preparación del siguiente seam puede avanzar sin activar el candidato ni retirar la recuperación.

| Etapa | Estado actual | Evidencia / pendiente |
|---|---|---|
| 0 | Preparación documental y binaria entregada | [Informe](docs/fastapi/PHASE_0_REPORT.md); seis cierres con wheels, catálogos y snapshot. Recursos e interoperabilidad sin medir |
| 1 | Infraestructura y seguridad ASGI preparadas; aceptación operativa pendiente | [Informe](docs/fastapi/PHASE_1_REPORT.md) y [seguridad](docs/fastapi/PHASE_1_SECURITY_REPORT.md); servidor actual predeterminado. Lifecycle y paridad en ejecución sin verificar |
| 2 | DTO y errores del framework preparados; aceptación pendiente | [Informe](docs/fastapi/PHASE_2_REPORT.md), [inventario](docs/fastapi/PHASE_2_REQUEST_INVENTORY.json) y [ejemplos sanitizados](docs/fastapi/PHASE_2_COMPATIBILITY_CASES.json); sin validación en ejecución |
| 3 | Seis lotes REST JSON preparados en el candidato inactivo | [Informe](docs/fastapi/PHASE_3_REPORT.md) y [registro estático](docs/fastapi/PHASE_3_ROUTE_REGISTRY.json); 90 operaciones canónicas + 50 de alias, dispatcher compartido, redacción selectiva. Contratos/efectos en ejecución pendientes |
| 4 | WS, SPA/assets y tiles preparados en el candidato inactivo | [Informe](docs/fastapi/PHASE_4_REPORT.md) y [registro estático](docs/fastapi/PHASE_4_ADAPTER_REGISTRY.json); lifecycle compartido, diferencias de transporte explícitas. Aceptación operativa pendiente |
| 5–6 | Pendientes | OpenAPI, QA autorizado, instaladores, adopción y retiro |

[ADR 0011](docs/adr/0011-staged-asgi-migration.md) registra la preparación autorizada y sus condiciones de adopción. No se convierte una comprobación pendiente en aprobada por no ejecutar suites.

### Fase 0. Preparación y decisión de viabilidad

**Responsables:** 0, 1, 2, 4, 5, 6, 7 y 8 propuesto. **Objetivo:** especificación revisable antes de añadir dependencias.

#### 0.1 Plataformas y dependencias

- Acordar Python/implementación, arquitectura, bits, ABI, libc/glibc o musl y sistema operativo. armv7l/aarch64/x86_64 por sí solos no identifican el destino completo.
- Seleccionar conjunto compatible con Python 3.10; no adoptar latest sin comprobar Requires-Python y transitivas.
- Auditar artefactos binarios de toda la resolución, incluido pydantic-core y SDK. Registrar versiones, origen, tags y hashes. Una futura comprobación con pip download --only-binary=:all: y parámetros del destino acredita resolución, no funcionamiento en SBC. [pip download](https://pip.pypa.io/en/stable/cli/pip_download/).
- Determinar fuente canónica de dependencias directas y derivación de manifests/constraints. Los rangos >= anteriores no eran pins; no fijar Starlette/AnyIO/pydantic-core ignorando las restricciones de sus padres.
- Decidir instalación común o extra/perfil web. No cargar paquetes en headless y no instalarlos son objetivos distintos; el segundo exige perfiles/instaladores.

**Entrega:** matriz de plataformas/resolución y decisiones visibles. **Puerta:** destinos soportados y conjunto candidato reproducible; no anunciar compatibles plataformas sin comprobar.

#### 0.2 Congelación de contratos externos

Crear catálogo por **método + ruta/plantilla**, alias, auth, query/body, precedencia, defaults/coerciones, respuesta/status/headers y efectos RF. Incluir descargas, mapas, rutas dinámicas, métodos rechazados y consumidores SPA/n8n. ROUTE_ALIASES sólo cubre parte del inventario.

En handle_request hoy se elimina barra final, se aplica alias y se fusiona query dando prioridad al body; query repetida puede convertirse en lista. No introducir redirects 307 ni otra precedencia sin decisión. Registrar cuerpo ausente/vacío/nulo, tipos inesperados, campos desconocidos y 404/405.

Congelar WS por dirección, discriminador y campos; separar nombres del bus JavaScript de mensajes wire. La lista inicial rx_packet/tx_packet/admin_response no acredita esos contratos.

**Entrega:** catálogo y ejemplos sanitizados por familia. **Puerta:** consumidores/operaciones conocidos tienen correspondencia y propietario; resolver omisiones antes de migrarlos.

#### 0.3 Contratos internos y estado único

La interfaz actual usa start(), stop() y broadcast_event(event); broadcast_ws es callback de ApiContext. Además:

- [bridge_core.py](src/bridge_core.py), [rx_router.py](src/rx_router.py) y [system_handler.py](src/routers/system_handler.py) acceden a .router.channels.
- broadcast_event registra eventos antes de comprobar clientes y alimenta historiales aun sin conexiones.
- El router construye buffers, ApiContext, controladores, canales, mapas y tareas. No basta con borrar su dispatcher.

Inventariar consumidores, incluidos ejecutores administrativos, y separar estado de transporte. Una BaseWebServer o Protocol ligera puede representar el seam; elegir la opción mínima. Mantener inicialmente adaptador compatible y después reemplazar .router.channels por servicio compartido. No ampliar la interfaz para ocultar responsabilidades distintas.

Depends(get_api_context) recuperará la instancia existente; no reconstruirá servicios/locks/buffers por request. Definir qué estado vive también en headless; no inventar historiales persistentes que hoy no existen.

#### 0.4 Headless, recursos y aprobación

En la base de fase 0, WEB_ENABLED=False devuelve None en la fábrica, pero los exports y el core importan el servidor anticipadamente. La preparación de fase 1 difiere esos imports y añade un contrato sin ASGI. Comprobar después, en ejecución, ausencia de imports transitivos FastAPI/Starlette/Pydantic/Uvicorn en headless.

Medir baseline/candidato con igual equipo, Python, carga, datos y perfil: RSS/CPU, arranque, event-loop lag, REST, entrega WS, assets y tamaño de distribución. Acordar presupuestos antes de convertirlos en límites; todavía no se midieron.

**Puerta conjunta:** catálogo, ownership, plataformas, perfil, backend WS y presupuestos revisados; aprobación del usuario. La preparación fue autorizada; los presupuestos de recursos quedaron sin fijar («no importa»), las mediciones y la aceptación operativa siguen pendientes. Conservar A hasta demostrar la adopción.

### Fase 1. Infraestructura ASGI y ciclo de vida

**Responsables:** 2, 5, 7 y 8. **Objetivo:** servidor que respete al propietario del bridge.

#### 1.1 Dependencias y fábrica

Declarar FastAPI/Uvicorn/Pydantic según perfil y **backend WebSocket de producción explícito**, websockets o wsproto. Uvicorn mínimo no lo incluye; websockets está hoy sólo en dev. No asumir necesario uvicorn[standard]. [Instalación Uvicorn](https://uvicorn.dev/installation/).

La fábrica recibe fachada/contexto existente, no crea otra radio/bridge/MQTT/scheduler. Usar loop activo, workers=1 y reload=False; no uvicorn.run()/asyncio.run() dentro del loop. Lifespan administra recursos web, no el bridge entero. [Lifespan FastAPI](https://fastapi.tiangolo.com/advanced/events/).

#### 1.2 Arranque, señales y parada

- Supervisar tarea Server.serve(); start espera listener listo o fallo. Sólo create_task cambia el contrato actual. Propagar bind ocupado, fallo lifespan y terminación posterior al propietario.
- En Uvicorn 0.54.0 seleccionado, serve usa capture_signals; la subclase localizada deja señales al bridge y conserva serve público. Bind/lifespan pueden lanzar SystemExit: convertirlo dentro de la tarea supervisada en fallo de arranque, conservando cancelación. La [inspección del wheel](docs/fastapi/DEPENDENCY_DECISIONS.md) registra fuentes y obligaciones; la observación inicial de 0.30.0 se conserva como antecedente, no como versión elegida.
- Parada idempotente, segura ante cancelación: cesar admisión, cerrar conexiones/tareas, solicitar salida, esperar/cancelar según presupuesto y liberar mapas. Consumir excepciones; no cancelar tareas ajenas.
- Conciliar presupuesto: core actual permite 1,5 s por subsistema y 5 s globales por señal. Timeout web nuevo de 2 s contradice ese orden. Diseñar/acordar presupuesto conjunto, sin imponer otro número.
- Conservar paso seguro de callbacks Paho desde threads al loop mediante mecanismo actual.

**Puerta:** bajo QA autorizado, bind fallido, rollback de arranque, señales, cancelación, parada repetida y cierre de recursos/tareas. Sin evidencia no retirar servidor anterior.

#### 1.3 Seguridad perimetral

Trasladar inspector, distinguiendo heurísticas de controles. Preservar política por ruta/método. Comparación actual: hmac.compare_digest sobre bytes UTF-8. REST/WS aceptan X-Api-Key prioritario o un único query api_key si falta; **Bearer no está implementado**. Sin BRIDGE_API_KEY se omite auth actualmente. Cambiarlo requiere decisión aparte.

Mantener mutaciones API, prefijos administrativos/TX/radio y lecturas sensibles protegidas; algunos GET son públicos. CORS no sustituye auth ni rechazo Origin WS. Política actual incluye mismo host y determinados orígenes locales/privados, no sólo allowlist estricta; endurecerla mostrando impacto.

| Control observado | Tratamiento ASGI |
|---|---|
| Cabeceras 65.536 bytes; lectura 10 s | Control equivalente en protocolo/servidor; middleware posterior al parsing no resuelve todo |
| JSON 1 MiB; lectura 10 s | Limitar bytes antes de acumular/validar, incluidos bodies segmentados |
| WS 32 conexiones, frame máximo 1 MiB | Conservar cupo; distinguir frame actual y mensaje ASGI/backend |
| WS_IDLE_TIMEOUT_SEC; drenaje WS 2 s | Diseñar equivalencia idle/envío/limpieza; no asumir defaults |
| IP peer, proxy headers ignorados | proxy_headers=False para paridad o decisión de confianza explícita |
| nosniff, DENY, Referrer-Policy, CSP | Trasladar; CSP actual permite inline/externos, no es garantía estricta |

Uvicorn tiene controles dependientes del backend y tamaño WS por defecto distinto al actual. h11_max_incomplete_event_size no sustituye límite total del body. [Configuración Uvicorn](https://uvicorn.dev/settings/).

Retirar X-XSS-Protection: 1; mode=block como requisito añadido sin fundamento en paridad. No exponer credenciales, query completa, cuerpos de validación o traceback. Conservar redacción de configuración/servicios/canales/admin; DTO de respuesta no reemplaza esas reglas. Exportación sensible de canales requiere auth y tratamiento propio, sin ejemplos con secretos.

### Fase 2. DTO y errores compatibles

**Responsables:** 1, 2, 5 y 8. **Objetivo:** declarar contrato observado sin imponer otro por accidente.

Preparación entregada el 2026-10-09: DTO permisivos por familia/operación,
inventario de 90 operaciones JSON/69 rutas y errores seguros del framework
registrados en la fábrica inactiva. La [fase 2](docs/fastapi/PHASE_2_REPORT.md)
explica presencia/coerción/extras, límites de seguridad y aceptación pendiente.
Los handlers no redactan respuestas que el router ya convierte en errores;
la continuación de fase 3 incorpora una política selectiva y correcciones
compartidas, con límites de redacción documentados.

#### 2.1 Modelos por operación

Esquemas web por familia, convirtiendo a servicios/controladores existentes. No imponer strict=True ni rechazo global de extras: documentar coerciones, incluidas cadenas query. La política debe elegirse por operación. [Modo estricto Pydantic](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/).

- Contactos: clave completa 32 bytes/64 hex. TX acepta variantes de destino; no regex global de clave completa a target. Resolver identidad/ambigüedad antes de rol/localidad.
- DM: máximo actual 160 **bytes UTF-8**, sin NUL; canal descuenta nombre local y ': '. max_length=160 cuenta caracteres y no basta. Conservar protección del adaptador. [sdk_adapter.py](src/serial/sdk_adapter.py), [BaseChatMesh.h](reference/meshcore/src/helpers/BaseChatMesh.h), [BaseChatMesh.cpp](reference/meshcore/src/helpers/BaseChatMesh.cpp).
- No hops 0..7 universal: autoadd max_hops 0..64; raw propio hop_limit 0..15; ruta RF con buffer de 64 bytes y modos de hash. Bytes/saltos/TTL no son equivalentes. [config_controller.py](src/web/controllers/config_controller.py), [protocol_types.py](src/protocol_types.py), [MeshCore.h](reference/meshcore/src/MeshCore.h), [Packet.h](reference/meshcore/src/Packet.h).
- `/api/packets`: `limit` por defecto 100, rango 1..500; `offset` por defecto 0, rango 0..100000; `order` asc/desc y filtros. Retirar el ejemplo con valores 50/1000. Firmas Python: parámetros requeridos antes de defaults o sólo por palabra clave.
- Respuestas: wrappers/campos actuales, incluidos partial/applied/config/action/dispatched_commands/target_node. No activar response_model incompleto que los filtre.

#### 2.2 Problem Details y status

Helper actual: type/title/status/detail/error/message/timestamp. Conservar esos campos; instance sería adición. RFC vigente 9457 reemplaza 7807; la actualización normativa no obliga a romper extensiones. [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html), [helper](src/web/controllers/base.py).

Cubrir validación, JSON malformado, `HTTPException` de Starlette, 404/405, middleware y negocio. Elegir status por catálogo; no convertir todo a 422. Si se adopta `application/problem+json`, comprobar consumidores y registrar cambio de content type. [Errores FastAPI](https://fastapi.tiangolo.com/tutorial/handling-errors/).

No todo error actual sigue ese formato: auth REST devuelve {error:Unauthorized}; tiles pueden responder vacío. Preservar excepciones o aprobar normalización separada. Redactar 500 sin str(exception) al cliente es corrección explícita, no garantía actual. No incluir valores secretos de validación.

**Puerta:** contratos/fixtures sanitizados de coerción, errores/respuestas y comprobaciones futuras autorizadas sin pérdida de campos. OpenAPI válido no demuestra paridad.

### Fase 3. Migración gradual de rutas

**Responsables:** 2, 4, 5 y 8; 1 supervisa dominio y 6 trazabilidad. **Objetivo:** APIRouter en lotes, reutilizando inicialmente diez controladores y locks/servicios.

Preparación del 2026-10-09: los seis lotes JSON se registran en la fábrica
candidata mediante APIRouter y un adaptador al dispatcher existente. Se conserva
body/target original, alias y fallback de métodos/slashes; los DTO son metadata,
sin reserialización de entrada. La [fase 3](docs/fastapi/PHASE_3_REPORT.md)
registra 140 operaciones JSON, redacción explícita de errores y puertas pendientes.
El servidor predeterminado sólo cambia textos del catch global `500` y errores
de enteros para no reflejar excepciones/valores; sus códigos y validación siguen.
Tiles, WS/SPA y adopción no están implementados por este registro.

Tabla de **cobertura comprobada**, no catálogo exhaustivo de la subfase 0.2. Migrar todos los métodos/variantes inventariados, evitando rutas nuevas por parecido de nombre.

| Lote | Cobertura necesaria | Fuente |
|---|---|---|
| 3.1 Sistema | status, health/diagnostics, preflight, report/report.md, export; GET/DELETE /api/system/logs; GET/POST /api/system/logs/level | Router y System/LogsController |
| 3.2 Red | nodes, lqi, analytics/variantes/reset, RF heatmap/noise, airtime | Router y NodesController |
| 3.3 Contactos/canales | CRUD, sync, import/export, share, discovered/accept, eliminación individual; channels/sync/export | Contacts/ChannelsController |
| 3.4 Historial/mapas | packets/export/borrado; messages/recent/messages/telemetry/logs/download/raw; GET map/status, POST map/reload y alias | Router, Packets/LogsController, MapTileService |
| 3.5 Servicios | GET/POST /api/services/config y presets; DELETE presets/{id}; POST mqtt-external/test | ServicesController y router |
| 3.6 Radio/admin | tx, config/node y variantes, ping/traceroute, admin/repeater/remotos | Tx/Config/RepeaterController y ejecutores |

Retirar rutas inventadas /api/logs/system, /api/logs/clear, /api/services y /api/services/reload. Markdown/historiales pueden estar envueltos en JSON; no convertirlos automáticamente a raw.

#### 3.7 Dominio y TX

Contactos REPEATER/LOCAL se rechazan actualmente con 400; creación usa 201 y actualización 200. No convertir rechazo a 403 dentro de paridad. Cubrir import/sync/accept/share/envío, además de listado/creación. Regla en dominio/adaptador, no sólo DTO.

Discrepancia previa: creación admite ROOM/SENSOR, list_client_contacts devuelve CLIENT. Resolver expresamente sin inferir nueva política de FastAPI. [ContactsController](src/web/controllers/contacts_controller.py), [NodeRegistry](src/contact_manager.py).

`POST /api/tx` usa `submit`, espera el future hasta 30 s y retorna 200 con `status`/`data`; timeout 408, rechazo de admisión 429 e indisponibilidad 503. `request_id` correlaciona, no sustituye resultado. 202/pending necesita propuesta propia, confirmación posterior y SPA/n8n. No equiparar éxito de comando y ACK remoto sin respetar semántica actual.

No añadir rechazo 429 general al cutoff: hay descarte selectivo por prioridad y controles específicos. No hay reapertura garantizada para inventar `Retry-After`. Preservar [TxRateLimiter](src/rate_limiter.py) y [ADR 0010](docs/adr/0010-duty-cycle-configurable-budget.md).

Chat TX mantiene cola; admin/config mantienen fachadas, serialización y controles propios. No afirmar que todo comando SDK pasa actualmente por TxRateLimiter ni forzar esa refactorización aquí. Conservar RepeaterManager e intervalos por categoría: min_cmd_interval_s, min_telemetry_interval_s, min_ping_interval_s, min_traceroute_interval_s, min_neighbours_interval_s y persistencia existente.

**Puerta por lote:** consumidores/auth/métodos/payloads/errores/efectos revisados y comprobación autorizada antes de continuar. Recuperación sin cambiar formato de datos y con servidor previo disponible.

### Fase 4. WebSocket, SPA y mapas

**Responsables:** 2, 4, 5 y 8. **Objetivo:** transporte nativo con contrato/recursos equivalentes.

#### 4.1 Handshake y mensajes

Mantener `/ws` usado por la SPA y el upgrade en cualquier ruta que admite el servidor actual. El candidato registra un catchall WS; auth/Origin/cupo se aplican antes de `accept`. Actualmente se responde 401 por clave incorrecta y 429 por cupo. Starlette `close` antes de `accept` normalmente responde 403; paridad requiere comprobar soporte de denial response de la combinación elegida. [WS Starlette](https://starlette.dev/websockets/).

Primero event_type=ws_connected, message/timestamp; después metrics_update con event/type. Conservar RX/TX/cola/radio/serial/uptime y airtime/alertas completos. Frontend interpreta type || event_type || event.

Inventariar emisiones reales: rf_packet, system_log, metrics_update, duty_cycle_alert, airtime_cutoff_change, contact_updated/discovered, repeater_response/telemetry, contacts_updated, channels_updated, self_info, clock_synced, metrics_reset, entre otras. RX_PACKET es nombre interno EventBus, no necesariamente wire rx_packet. [websocket.js](src/web/static/js/core/websocket.js), servidor, RX/controladores son evidencia.

El navegador envía JSON `type=ping` cada 15 s; el servidor responde JSON `type=pong`. Conservar formatos/unidades. Ping RFC del backend no sustituye heartbeat JSON. Mantener idle y `WS_METRICS_INTERVAL_SEC` sin duplicar tareas.

#### 4.2 Difusión y estado

Conservar broadcast_event o adaptar todos los consumidores. Registrar evento una vez antes de difundir, incluso sin clientes; mantener buffers/retención/contadores.

El servidor actual difunde secuencialmente con `writer.drain()` limitado a 2 s por cliente; el candidato conserva esa secuencia y ese presupuesto mediante tareas retenidas, lock y envío ASGI. La latencia agregada puede crecer con clientes lentos. El envío ASGI espera flow control antes del write; eso no demuestra equivalencia con el drain posterior. Una difusión concurrente mediante `gather(return_exceptions=True)` sería una decisión futura; por sí sola tampoco acota clientes lentos. Si se crea cola, acordar capacidad/descarte. Cada tarea tiene propietario y se cancela/espera al cerrar.

#### 4.3 Estáticos y mapas

Montar estáticos tras API/WS/docs. StaticFiles(html=True) no demuestra fallback actual: /chat,/map,/nodes,/contacts,/settings,/telemetry,/logs,/analytics y ciertas rutas sin extensión sirven index. Assets inexistentes con extensión y API desconocida no deben convertirse en HTML de éxito.

Los estáticos actuales aceptan todos los métodos que alcanzan el dispatcher; OPTIONS se resuelve antes y HEAD suprime representación. Conservar esa amplitud, MIME, traversal/pertenencia al root, ETag/304, gzip/Vary, HTML sin caché y caché de assets. Diseñar equivalencia, no asumirla por StaticFiles. Las teselas sólo aceptan GET, incluido rechazo 405 para HEAD.

Conservar XYZ/MBTiles, TMS/XYZ, PNG/JPG/JPEG/WebP/PBF, MIME, status/reload. Tiles ya usan `asyncio.to_thread`; mantener locks/cierre/coordenadas/headers. No limitar router a `.png`. [MapTileService](src/web/map_tile_service.py) y `_serve_map_tile` acreditan comportamiento actual.

**Puerta:** bajo autorización, SPA/WS virtuales, desconexión/clientes lentos, historial sin clientes, mapas/offline. No afirmar carga en 100 ms sin medición comparable.

**Preparación entregada el 2026-10-09:** [fase 4](docs/fastapi/PHASE_4_REPORT.md).
El hub presta el bridge/router y los mapas; el lifespan inicia sólo métricas web pasivas.
El plazo de apagado procede del propietario y no se renueva entre hub/Uvicorn/lifespan.
Ping RFC vacío conserva `WS_IDLE_TIMEOUT_SEC` (30 s por defecto) sin exigir pong;
el reset por chunks, fragmentación aceptada por SansIO y falta de deadline nativo
de 10 s para tramas parciales son diferencias pendientes. Las rutas de docs
devuelven 404 explícito hasta fase 5. No se activó el candidato ni se ejecutaron suites.

### Fase 5. OpenAPI, documentación offline y verificación

**Responsables:** 3, 4, 5, 6 y 8. **Objetivo:** demostrar migración y ofrecer integración sin exponer secretos.

#### 5.1 Documentación utilizable

Declarar auth/responses/ejemplos sanitizados/aliases según catálogo; documentar WS aparte. Decidir valor de ReDoc: offline exige su bundle además de JS/CSS Swagger. Registrar versiones/licencias/origen, evitar CDN. [Assets locales FastAPI](https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/).

Con clave, proteger /docs,/redoc,/openapi.json. Diseñar navegación y carga del esquema con credencial; navegación normal no añade X-Api-Key. No persistir secretos en URL ni inventar sesión sin diseño. Docs desactivables es opción a acordar. Cargar docs no envía RF; operaciones interactivas de mutación muestran efecto real.

#### 5.2 Matriz de evidencia futura

| Área | Comprobación autorizada | Límite |
|---|---|---|
| REST | AsyncClient + ASGITransport; contratos/auth/errores/modelos; datos temporales | HTTP aplicación, no listener/protocolo completo |
| Lifespan/ownership | Startup/shutdown explícitos, fallos/idempotencia/recursos | ASGITransport no dispara lifespan |
| Uvicorn/WS | Loopback propio, puerto SO; handshake/Origin/auth/cupo/límites/heartbeat/backpressure | No usar estación operativa |
| SPA/assets/mapas | Navegador virtual; fallback/HEAD/cache/gzip/MIME/MBTiles/offline | Regex URLs no verifica comportamiento |
| Radio/servicios | Adaptadores virtuales; cola/ACKs/roles/timers/cooldowns/mocks MQTT | No certifica radio física |
| Instalación/headless | Perfiles/checker/imports/resolución/rollback staging | Wheels no certifican ejecución SBC |
| Calidad | pytest/cobertura, mypy strict, Ruff y navegador separados | Ausencia/skips/fallos explícitos |
| Recursos | Baseline/candidato con plataforma/carga/versiones | Sin presupuestos acordados no hay aprobación numérica |

ASGITransport no activa lifespan ni prueba WS, streaming TCP/backpressure o integración Uvicorn. Gestionar lifespan explícitamente; httpx y gestor opcional asgi-lifespan pertenecen a dev. [HTTPX](https://www.python-httpx.org/advanced/transports/), [Async Tests FastAPI](https://fastapi.tiangolo.com/advanced/async-tests/).

Conservar regresiones actuales. test_web_server.py llama directamente al router, no es por sí solo suite de sockets. Adaptar fixtures de conftest que acceden a server.sockets, tile_service y router.channels_ctrl sin rebajar expectativas. Mantener test_web_official_compatibility, remaining_web_regressions/races, security_audit y http_cache_contract; helpers privados retirados necesitan cobertura observable equivalente.

[verify_api_parity.py](.agents/skills/contract-openapi-sync/scripts/verify_api_parity.py) compara parcialmente literales/prefijos y depende del router actual; adaptarlo al retirar archivo. No demuestra métodos/schemas/WS ni el 100% del contrato. Combinar catálogo/OpenAPI y pruebas observables.

Conservar Python 3.10 y versiones soportadas; CI actual con 3.10/3.12. Datos temporales/limpieza garantizada, sin `.env` ni nodos/canales/airtime operativos. [TESTING.md](docs/TESTING.md) define suite; autorizaciones históricas no activan suites aquí.

**Puerta:** resultados actuales por área, pendientes/skips/riesgos revisados. Ejecución futura por petición explícita. Esta reunión no ejecutó ninguna suite.

### Fase 6. Adopción, retiro y publicación

**Responsables:** 0, 2, 6, 7 y 8. **Objetivo:** release recuperable y documentación de lo implementado.

#### 6.1 Instaladores y checker

Actualizar manifests/perfil, [check_runtime_dependencies.py](scripts/check_runtime_dependencies.py), instaladores raíz y guías. Checker sólo verifica cuatro paquetes y Windows lo usa para decidir instalación: añadir requirements sin checker puede omitir FastAPI. Verificar imports/versiones/backend WS por perfil y coherencia de resolución.

Mantener entrypoint meshcore_bridge.py y Uvicorn embebido; no CLI multiproceso/reload. Verificaciones operativas en instalación aislada autorizada.

#### 6.2 Rollback y retiro

Reutilizar staging de [install.sh](install.sh) y [staged_update.py](scripts/staged_update.py), incluyendo manifests/constraints nuevos en componentes. Conservar configuración/datos/mapas/logs según mecanismo actual; sin cambio de formatos. Registrar recuperación y evitar doble propiedad de radio.

Retirar http_server/dispatcher/controladores sólo tras reubicar responsabilidades, revisar consumidores y preservar regresiones. No borrar lógica por contar líneas. Medir reducción neta, incluyendo adaptadores/modelos/tareas. No afirmar transacción atómica del árbol o recuperación ante pérdida eléctrica sin evidencia.

Gate de servicio incluye HTTP/WS/parada además de systemctl is-active. Push no demuestra instalación o funcionamiento de una estación.

#### 6.3 Decisiones y documentación

Tras aprobación arquitectónica, crear ADR con estado/alcance apropiados **antes de implementar**, después registrar evolución. 0011 es siguiente número disponible ahora; comprobar al crearlo. No crear ADR aceptado en esta reunión.

Actualizar arquitectura/manuales/CONTEXT cuando proceda, despliegue/pruebas/índice/diagramas al implementar; las guías actuales no presentan FastAPI como existente. Conservar ADR históricos y registrar conciliaciones.

Publicar sólo archivos/hunks propios conforme AGENTS, verificando rama/remoto/índice, sin force push. Publicación de esta revisión documental distinta de release FastAPI.

**Puerta:** paridad/recursos acreditados, rollback comprobado, perfiles/servicio actualizados, documentación sincronizada y aceptación de release según alcance autorizado.

## 5. Riesgos y decisiones pendientes

| Riesgo | Consecuencia | Condición |
|---|---|---|
| Workers/reload/bridge en lifespan | Radio/MQTT/timers duplicados | Un propietario y contexto recibido |
| Start sin readiness/stop mal presupuestado | Listeners fallidos/recursos pendientes | Fallos propagados y presupuesto conjunto |
| API señales de otra versión | Fallo de arranque o señales capturadas | Adaptador específico y evidencia lifecycle |
| Wheels transitivos/backend WS ausente | Instalación/WS fallidos | Resolución por plataforma/perfil |
| DTO restrictivo o incompleto | Rechazo de clientes/pérdida de campos | Contratos de coerción/respuesta/redacción |
| Descartar estado/recrear servicios | Historial/canales/cooldowns perdidos | Contexto único, extracción antes de retirar |
| Defaults ASGI/auth/Origin distintos | Acceso/handshake/límites alterados | Matriz seguridad y transporte |
| TX/cutoff/reintentos nuevos | Incompatibilidad/transmisiones duplicadas | Rediseño separado y checklist RF |
| Sólo HTTP en memoria | Regresiones WS/SPA/despliegue ocultas | Memoria más transporte virtual real |

Pendientes: plataformas, instalación común/extra web, backend/versiones/constraints, presupuestos de recursos/apagado, docs autenticadas/ReDoc y discrepancias previas. No se fijan valores nuevos ni se presentan como consenso aprobado.

La propuesta a aprobar es una migración gradual de presentación con FastAPI modular y contratos preservados, condicionada por estas puertas. El futuro gana una API declarada e infraestructura mantenida externamente; radio, dominio y operación ligera siguen requiriendo diseño y evidencia propios.

## 6. Evidencia y límites de la revisión

Las ubicaciones siguientes permiten reproducir los hallazgos principales por lectura. Los números de línea corresponden al checkout inspeccionado y pueden cambiar después.

| Hallazgo | Ubicación de evidencia local |
|---|---|
| Roles de advert oficiales | [AdvertDataHelpers.h](reference/meshcore/src/helpers/AdvertDataHelpers.h), líneas 7–11; [protocol_types.py](src/protocol_types.py), 115–122 |
| Imports headless y fábrica | [bridge_core.py](src/bridge_core.py), 45 y 364–372; [exports web](src/web/__init__.py), 7–8 |
| Estado y diez controladores | [api_router.py](src/web/api_router.py), 119–152 |
| Contrato interno de canales | [bridge_core.py](src/bridge_core.py), 745; [rx_router.py](src/rx_router.py), 419–420; [system_handler.py](src/routers/system_handler.py), 63–64 |
| Historial anterior a difusión | [http_server.py](src/web/http_server.py), 206–209 |
| Auth HTTP/WS y clave prioritaria | [http_server.py](src/web/http_server.py), 586–667 y 714–739 |
| Logs y servicios reales | [api_router.py](src/web/api_router.py), 395–443 y 746–775 |
| Límites por bytes DM/canal | [sdk_adapter.py](src/serial/sdk_adapter.py), 1044–1050 y 1101–1104 |
| TX espera resultado | [tx_controller.py](src/web/controllers/tx_controller.py), 65–134 |
| Presupuesto de parada | [bridge_core.py](src/bridge_core.py), 684–696 y 1126 |
| Checker e instalación Windows | [check_runtime_dependencies.py](scripts/check_runtime_dependencies.py), 11–16; [install.ps1](install.ps1), 66–75 |

- Lectura de guía/AGENTS/CONTEXT/índice/arquitectura/ADRs/manifests, instaladores/checker, core/web/controladores/consumidores JS y fuentes oficiales citadas.
- Al cerrar: comprobaciones de estructura, conteos, enlaces y diff documental. Acreditan el artefacto y referencias locales, no ejecución ASGI ni equivalencia funcional.
- No pytest/Playwright/fuzzing/mypy/Ruff ni instalación de paquetes. No servicios/hardware. QA participó planificando.
- No matriz completa de wheels/pins ni mediciones RSS/CPU/latencia/ahorro neto. Fuentes web no sustituyen resolución/verificación del candidato futuro.
- Citas de código describen el checkout inspeccionado; upstream evoluciona. Uvicorn 0.30.0 se usa para refutar el ejemplo inicial, no para recomendar hoy esa versión.
