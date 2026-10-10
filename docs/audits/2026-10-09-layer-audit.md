# Reunión técnica y auditoría por capas — 2026-10-09

Estado: revisión de fuentes e integración de correcciones. FastAPI es el transporte
web seleccionado; aceptación operativa pendiente. El usuario ordenó continuar sin
ejecutar suites. No se arrancaron servicios ni se usaron radio, broker o datos de
una estación operativa.

## Contexto, reunión y plan

El líder coordinó tres especialistas simultáneos, reutilizados en tandas:
backend/concurrencia, seguridad/documentación y FastAPI/instaladores. Se aplicaron
las skills `async-concurrency-engineering`, `python-patterns-typing`,
`security-code-auditor`, `api-design-testing`, `contract-openapi-sync`,
`installer-release-maintenance`, `project-reference-audit`, `domain-adr-keeper`,
`systematic-debugging` y `verification-before-completion`. QA aportó criterios y
regresiones pendientes; no se delegó una ejecución que el usuario suspendió.

La revisión comenzó sobre `fcaf89b4df7def3371ad9a54376717d9bbba1998`. Durante la
integración otro actor publicó `a7c4c2b`, incorporando las primeras correcciones
de este equipo junto con su ADR 0012. Se volvió a leer el checkout y se preservaron
sus cambios. El informe describe ambos cambios ya incorporados y la integración
posterior. Otro commit concurrente, `acd1fa3`, incorporó la segunda tanda y un
informe inicial. La revisión final volvió a comprobar esos archivos. No se
atribuye al equipo todo el contenido de esos commits. `.gitignore`
y otros artefactos concurrentes quedan fuera del conjunto propio de publicación.

Orden acordado: (1) fuentes oficiales y dominio; (2) serial/RX/TX y servicios;
(3) composición ASGI/REST/WS; (4) seguridad y SPA; (5) dependencias e instalación;
(6) conciliación documental, eliminación justificada y revisión cruzada.
Cada especialista tuvo archivos propios; el líder integró contratos y evidencias.

## Resultado por capa

| Capa | Evidencia y resultado | Corrección o límite |
| --- | --- | --- |
| Protocolo y dominio | [protocol_types.py](../../src/protocol_types.py), firmware/SDK en `reference/` y [CONTEXT](../../CONTEXT.md) | Se mantienen roles oficiales e invariantes LOCAL/REPEATER. Retirado `RUN_CLI_COMMAND=66`, sin consumidores ni definición oficial encontrada. |
| Serial y mensajería | [sdk_adapter.py](../../src/serial/sdk_adapter.py), [bridge_core.py](../../src/bridge_core.py), framing y referencias oficiales | La sospecha inicial de bypass TCP se descartó: `_raw_chat_permitted` ya bloquea chat LOCAL/REPEATER. Companion/raw y compatibilidad consumida se conservan. |
| Servicios y persistencia | [services_manager.py](../../src/services_manager.py), [services_controller.py](../../src/web/controllers/services_controller.py) | Guard compartido para lifecycle, recarga y presets. Escrituras sobre snapshot privado, retenidas y protegidas contra cancelación del solicitante; siguiente mutación espera al escritor anterior. Referencias MQTT en los contextos reales `_ctx`. |
| Fallos de recarga | Mismas fuentes de servicios | Un fallo de bind TCP se propaga; no registra éxito. Recargar varios componentes continúa siendo una operación que puede quedar parcialmente aplicada; no hay rollback global nuevo. |
| Composición web | [asgi_server.py](../../src/web/asgi_server.py), [asgi_routes.py](../../src/web/asgi_routes.py), [api_router.py](../../src/web/api_router.py) | Core selecciona ASGI; no import del servidor HTTP retirado en producción, scripts o pruebas mantenidas. Reutilizar dispatcher/controladores conserva el dominio y sus efectos. |
| REST y OpenAPI | [catálogo REST](../../src/web/asgi_route_catalog.py), [OpenAPI](../../src/web/asgi_openapi.py), [anotaciones](../../src/web/asgi_openapi_catalog.py) | 90 operaciones JSON en 69 rutas canónicas; 39 alias generan 50 operaciones. Una operación de teselas completa 91 operaciones/70 rutas canónicas. Títulos del esquema ya describen el transporte actual. |
| WebSocket y recursos | [hub](../../src/web/asgi_ws_hub.py), servidor y router | Tareas de notificación retenidas, resultados observados, admisión detenida y cancelación al cierre. Diagnósticos de fallo no vuelven a disparar broadcast. Core observa fallo web mediante callback sin reinicio automático. |
| Mapas y cancelación | Servidor ASGI y [MapTileService](../../src/web/map_tile_service.py) | Propiedad explícita: router prestado no se cierra por defecto; composición core cede propiedad. Cierre/reapertura de mapas fuera del loop, workers retenidos y ordenados; reinicio rechazado mientras queda trabajo anterior. |
| Frontera de seguridad | [access_policy.py](../../src/web/access_policy.py), middleware, controladores y [services_config.py](../../src/services_config.py) | Presets propios y agregados usan proyección sin secretos. Fallos revisados omiten valores de excepción en respuesta/log y ACK MQTT. Se conservan códigos, metadatos y exportaciones autenticadas intencionales. |
| SPA | [map.js](../../src/web/static/js/modules/map.js) y consumidores REST/WS | Se escapan seis interpolaciones HTML de métricas remotas. Se conserva frontend Vanilla. Sintaxis comprobada; navegador y explotación no ejecutados. |
| Instalación | [checker](../../scripts/check_runtime_dependencies.py), manifiestos e instaladores raíz | Web predeterminado y seis pins exactos; probes explícitos `--profile web`, perfil desconocido falla cerrado. Core es perfil de comprobación; `WEB_ENABLED` decide construcción. |
| Documentación | [índice](../README.md), [plan](../../PROYECTO.md), [ADR 0011](../adr/0011-staged-asgi-migration.md), manuales y fase 6 | Firmas y rutas reales, diagramas Mermaid ASGI y snapshots históricos identificados. Retiradas cifras RSS, instalación garantizada y rollback atómico global sin evidencia. |

Los endpoints mantienen validación y coerciones en los controladores. DTO con
`Any` y extras son metadatos OpenAPI; no se llama a validación Pydantic para alterar
requests ni se filtran respuestas mediante modelos estrictos. `/api/logs` mantiene
su 404 deliberado. OpenAPI no enumera mensajes WS ni prueba sus contratos.

`/docs` y `/redoc` sirven un visor propio offline de solo lectura. No son bundles
Swagger/ReDoc. El visor solicita el esquema manualmente con cabecera de API key
y no ejecuta operaciones ni introduce timers RF. La política Origin heredada
admite direcciones privadas LAN; no se presenta como Same-Origin estricto.

## Limpieza con evidencia

Se retiraron `config.WEB_SERVER_BACKEND`, `CompatibilityBodyDTO.to_legacy_body`
y `CommandType.RUN_CLI_COMMAND`: las búsquedas de consumidores versionados no
encontraron uso en producción, pruebas mantenidas o scripts. La mención documental
del helper DTO se conserva como historia y se identifica como retirada.
También se retiró el flag sin consumidores `application_contract_ready=True`:
una constante no acredita aceptación operativa.

Se conservaron `CLI_REPLY` (sentinel usado por privacidad), exports y aliases
seriales/raw, `static_dir`, `server.sockets`, `active_websockets`,
`SecurityTrafficInspector.extract_client_ip` y `_route_channels`: tienen consumidores.
Los controladores no son basura: ASGI los utiliza. No se eliminaron caches,
capturas o archivos concurrentes por una búsqueda sin prueba de propiedad.

## Verificación y pendientes

| Comprobación | Estado y alcance |
| --- | --- |
| AST de Python con gramática 3.10 | 315 archivos versionados (80 src, 28 scripts, 95 tests, 3 raíz y 109 skills) en la inspección inicial; cero errores. La repetición final incluye 317 archivos (una regresión nueva y un archivo tools adicional), también sin errores; sin imports de aplicación. No acredita tipos ni compatibilidad de dependencias en ejecución. |
| Catálogos, alias y anotaciones | 90 anotaciones casan con el catálogo y 190 referencias (82 únicas) resuelven a archivos/símbolos. Búsqueda léxica SPA: 74 ocurrencias/46 rutas, sin destino ausente; no acredita método ni payload. No generación real de OpenAPI ni ejecución de operaciones. |
| Pins y manifiestos | Seis pins conciliados y metadata de wheels inspeccionada. Resolución binaria histórica separada de funcionamiento en destino. |
| JavaScript | `node --check` de los módulos afectados; no navegador. |
| PowerShell | ParseFile estático del instalador. |
| Bash | `bash -n` no pudo iniciarse por restricción MSYS `NtCreateDirectoryObject 0xC0000022`; no se declara sintaxis comprobada. |
| Documentos y diff | Enlaces locales y whitespace comprobados. Hashes/fuentes en [registro](2026-10-09-layer-audit.json). |
| pytest y cobertura | No ejecutados por instrucción del usuario. Tres escenarios nuevos en [test_asgi_resource_ownership.py](../../tests/test_asgi_resource_ownership.py), sin ejecutar; no equivalen a resultados. |
| mypy y Ruff | No ejecutados. AST no los sustituye. |
| Navegador, fuzzing, headless e instalación | No ejecutados. |
| HTTP/WS, sockets, maps, cancelación y recursos reales | Pendientes de validación aislada autorizada. No certificación de interoperabilidad, seguridad completa, RSS ni tiempo de arranque. |

El plazo web existente limita la espera de cierre; no fuerza la terminación de
threads y no garantiza que el apagado completo del bridge dure 1,5 segundos.
Un fallo de persistencia o una recarga parcial no tienen rollback transaccional
nuevo. Un `kill` del proceso tampoco queda cubierto por retener tareas asyncio.

## Impacto LoRa

1. Airtime: estas correcciones no agregan envíos ni consultas de radio; conservan
   acciones y políticas existentes. El análisis es de código, no una medición RF.
2. Spam/feedback: se conservan deduplicación, guarda local, límites y cooldowns;
   los logs de fallo de notificaciones usan `skip_broadcast` para no retroalimentarse.
3. Guardado/timers: no se añaden ni se cambian intervalos. Se mantienen timestamps
   persistidos de seguridad; ordenar escrituras no programa consultas ni reinicios.

La revisión estática entrega correcciones revisables. Las puertas de ejecución
permanecen explícitas y suspendidas; publicar el código no las convierte en aprobadas.
