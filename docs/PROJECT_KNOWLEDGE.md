# Conocimiento y verificación del proyecto

Mapa de implementación conciliado el 2026-10-09 y decisión de runtime actualizada el 2026-10-10; procedencia e inventario conservan
su revisión histórica del 2026-09-30. Este documento reúne el mapa de información,
la procedencia de las referencias y las divergencias comprobadas. No constituye
una certificación de interoperabilidad, seguridad, rendimiento o funcionamiento
del checkout completo. La revisión incluye cambios locales anteriores que siguen
sin publicarse en aquella revisión; el inventario identifica su propio HEAD como base
y sus hashes no representan automáticamente el checkout actual.

## Autoridad y navegación

| Información | Fuente y alcance |
| --- | --- |
| Reglas de trabajo y delegación | [AGENTS.md](../AGENTS.md); las órdenes del usuario prevalecen. |
| Dominio, roles y exclusiones | [CONTEXT.md](../CONTEXT.md); CLIENT, REPEATER, ROOM, SENSOR y LOCAL. |
| Instalación y capacidades | [README](../README.md), [despliegue](DEPLOYMENT_GUIDE.md), instaladores raíz. |
| Protocolo | [especificación](PROTOCOL_SPEC.md); contrastar con firmware y SDK oficiales fijados abajo. |
| Implementación | [arquitectura](ARCHITECTURE.md), [explicación](CODE_EXPLANATION.md) y código actual de `src/`. |
| MQTT/n8n | [guía](N8N_WORKFLOW_GUIDE.md), [export JSON](../n8n_workflow_meshcore.json), `mqtt_dispatcher.py` y routers RX. |
| Configuración | [config.py](../config.py) y [.env.example](../.env.example); el ejemplo puede diferir del default. No leer ni publicar `.env` activo para inventariar. |
| Decisiones | [ADRs](adr/); conservar su historia y distinguir propuesta, decisión e implementación. |
| QA y Pruebas | [guía de pruebas](TESTING.md), [inventario de pruebas](TEST_INVENTORY.md). |
| Mapas | [guía MBTiles](../data/maps/README.md), `map_tile_service.py`; SQLite se usa para cartografía. |
| Diagramas | [arquitectura](diagrams/meshcore_architecture.html), [pipeline](diagrams/meshcore_packet_pipeline.html), [secuencia](diagrams/meshcore_rx_tx_sequence.html); JSON fuente y recibos visuales tienen su propia fecha. |
| Inventario reproducible | [PROJECT_INVENTORY.json](PROJECT_INVENTORY.json): documentos con hash, archivos fuente, skills, entradas raíz y referencias con revisión/procedencia. |

Los cuatro análisis especializados son [firmware](reference_analysis/01_FIRMWARE_C_CPP.md),
[SDK](reference_analysis/02_PYTHON_SDK.md), [CLI/repetidores](reference_analysis/03_CLI_AND_REPEATER_MANAGEMENT.md)
y [integración para agentes](reference_analysis/04_INTEGRATION_GUIDE_FOR_AGENTS.md).
Son documentación derivada, subordinada a los serializadores y parsers oficiales.

Las decisiones numeradas son: [contactos](adr/0001-strict-repeater-contact-exclusion.md),
[airtime](adr/0002-lora-airtime-guardrails.md), [resiliencia serie](adr/0003-asyncio-serial-resilience.md),
[alertas/persistencia airtime](adr/0004-airtime-duty-cycle-alerting-and-persistence.md),
[JSON](adr/0005-json-atomic-persistence-over-sqlite.md),
[proxy TCP](adr/0006-tcp-companion-server-proxy.md),
[beacon/telemetría](adr/0007-decoupling-local-beacon-telemetry.md)
y [reloj RTC](adr/0008-automatic-rtc-clock-synchronization.md). Las decisiones
posteriores incluyen [capas Companion](adr/0009-official-companion-protocol-layers.md),
[duty cycle configurable](adr/0010-duty-cycle-configurable-budget.md) y
[migración ASGI](adr/0011-staged-asgi-migration.md),
[Bootstrap](adr/0012-bootstrap-5-frontend-architecture.md) y
[baseline Python 3.14.8](adr/0015-python-3-14-8-baseline.md). Los [ADR 0013](adr/0013-python-3-14-modernization.md)
y [ADR 0014](adr/0014-python-3-15-baseline.md) se conservan como decisiones históricas sustituidas.

## Mapa de implementación

| Subsistema | Archivos principales | Contrato comprobado por lectura |
| --- | --- | --- |
| Arranque/composición | `meshcore_bridge.py`, `src/__main__.py`, `src/bridge_core.py`, `src/preflight.py` | Compone serie, MQTT, web, workers y registros; importar/arrancar puede leer configuración o consultar servicios. |
| Serie | `src/serial/sdk_adapter.py`, `serial_base.py`, `watchdog.py`, `raw_framing.py` | Companion lo gestiona el SDK. El raw propio es parser en memoria, sin transporte UART físico. |
| Protocolo | `src/protocol_types.py`, `sensor_decoder.py` | Enums oficiales y tipos del bridge; CayenneLPP tiene endian por campo, no LE universal. |
| RX | `src/rx_router.py`, `src/routers/`, `event_utils.py`, `deduplicator.py` | Normalización, clasificación y publicación; deduplicación vive en RAM. |
| TX/airtime | `src/rate_limiter.py`, `packet_buffer.py`, `target_resolver.py` | Cola/prioridades/pacing y estimación de airtime; `sent` no acredita entrega remota. |
| Nodos/contactos | `src/contact_manager.py`, `lqi_engine.py` | Registro JSON y caché; LQI calcula RSSI/SNR/saltos con EMA/decaimiento. Las invariantes excluyen repetidor y nodo local de chat/contactos. |
| Administración | `src/admin_handler.py`, `admin/`, `repeater_manager.py` | Operaciones SDK y comandos remotos bajo demanda; cualquier cambio RF requiere checklist y límites acordados. |
| MQTT | `src/mqtt_client.py`, `mqtt_dispatcher.py`, `health_reporter.py` | Paho y adaptador asyncio; sin cola MQTT durable en disco. Salud MQTT no publica RAM/CPU del OS. |
| TCP Companion | `src/tcp_companion_server.py` | Proxy Companion con controles de conexión; no equivale a una segunda radio física. |
| REST/WebSocket | `src/web/asgi_server.py`, `asgi_routes.py`, `asgi_ws_hub.py`, `api_router.py`, `controllers/` | ASGI es el backend seleccionado por el core; REST conserva dispatcher/controladores, WS usa el hub. Servidor HTTP nativo retirado, sin fallback. |
| Contrato/documentación API | `src/web/asgi_docs.py`, `asgi_openapi.py`, `request_models.py`, `docs_ui/` | Visor propio de consulta `/docs` y alias `/redoc`; esquema `/openapi.json`. DTO abiertos para documentación, sin validación de solicitudes en ejecución; sin paquetes Swagger UI/ReDoc. |
| SPA | `src/web/static/`, `src/web/static/index.html` | HTML, Vanilla CSS/JS, WebSocket y almacenamiento IndexedDB del navegador. |
| Persistencia/cartografía | registros/canales/airtime JSON, `src/web/map_tile_service.py` | JSON atómico, buffers RAM y lectura SQLite MBTiles; no backend SQLite de chat/nodos. |
| QA | `tests/`, `pyproject.toml`, `scripts/run_quality_checks.py` | Suites sólo por petición explícita; temporal, virtual y loopback. No ejecutar scripts históricos por su nombre. |

Runtime acordado: CPython >=3.14.8; versión del proyecto 3.0.0. El cambio de baseline
se comprueba en manifiestos, checker, instaladores y CI, y no acredita ejecución por sí solo.
Dependencias directas fijadas para esta actualización: Paho MQTT 2.1.0, MeshCore SDK 2.3.15,
pyserial 3.5 y python-dotenv 1.2.4. La pila web añade FastAPI 0.143.0, Uvicorn 0.54.0,
Pydantic 2.14.0, websockets 17.2, Starlette 1.7.0 y h11 0.16.0.
El checker distingue `web` y `core` (headless). Esto describe dependencias declaradas,
no acredita paquetes instalados, funcionamiento o recursos medidos.

## Referencias y procedencia

Las páginas primarias de [firmware](https://github.com/meshcore-dev/MeshCore),
[SDK](https://github.com/meshcore-dev/meshcore_py) y
[CLI](https://github.com/meshcore-dev/meshcore-cli) fueron consultadas en la web
durante la revisión de septiembre. Su disponibilidad no demuestra que las copias locales sean
el último upstream. No se hizo fetch/pull ni se modificó `reference/`.

| Referencia | Revisión Git local | Autoridad |
| --- | --- | --- |
| `reference/meshcore/` | `d92964352441e53b93e8667b802e04f6e072b39e` (`companion-v1.17.1`) | Firmware oficial. |
| `reference/meshcore_py/` | `c487efbe187f4b000020afdfc0349c4cdf503c5a` (`v2.3.8`) | SDK oficial. |
| `reference/meshcore_cli/` | `0856c723cdea3438811c62c190bbec3059e2dc48` | CLI oficial; paquete local 1.6.0. |
| `reference/meshmonitor/` | `d9ade72f6d32de420d18c4d9838af00ddda4c6e9` | Tercero, comparación; no autoridad del protocolo. |

Los cuatro árboles con Git propio estaban limpios. Hay once copias adicionales
sin `.git` propio; su revisión no se puede acreditar con Git. Ejecutar `git -C`
en ellas sin comprobar ese marcador devuelve el repositorio padre por ascenso.

| Copia sin Git | Origen declarado localmente; no acredita contenido ni revisión |
| --- | --- |
| `akita-bridge` | [AkitaEngineering/akita-meshtastic-meshcore-bridge](https://github.com/AkitaEngineering/akita-meshtastic-meshcore-bridge), README. |
| `ipnet-meshcore-mqtt` | [ipnet-mesh/meshcore-mqtt](https://github.com/ipnet-mesh/meshcore-mqtt), badges del README. |
| `meshcore-proxy` | [rgregg/meshcore-proxy](https://github.com/rgregg/meshcore-proxy), instrucción clone. |
| `meshcoretomqtt` | [Cisien/meshcoretomqtt](https://github.com/Cisien/meshcoretomqtt), instrucción clone. |
| `michaelhart-mqtt-broker` | Autor Michael Hart; no URL de repositorio acreditada. |
| `openhop_core` | Catálogo/README usan `openhop-dev/openhop_core`, pyproject usa `openhop-dev/openhop-core.git`; discrepancia de origen pendiente. |
| `openHop_docs` | `openhop-dev/openHop_docs`, catálogo local. |
| `openhop_repeater` | `openhop-dev/openhop_repeater`, README/catálogo. |
| `openHop_RepeaterUI` | `openhop-dev/openHop_RepeaterUI`, catálogo local. |
| `openHop-Glass` | `openhop-dev/openHop-Glass`, catálogo; README denomina el stack `pyMC_Glass`. |
| `remote-terminal` | [jkingsman/Remote-Terminal-for-MeshCore](https://github.com/jkingsman/Remote-Terminal-for-MeshCore), instrucción clone. |

`reference/README.md` sólo enumera nueve árboles y llama oficial a todo el conjunto.
Este inventario corrige la clasificación sin modificar las referencias de sólo
lectura. Encontrar un archivo LICENSE tampoco certifica compatibilidad de licencia
para copiar código; las licencias completas no se auditaron.

## Divergencias históricas y conciliación actual

La tabla siguiente conserva hallazgos de septiembre; sus estados "pendiente" son
históricos. Por lectura del 2026-10-09, `_handle_admin_request` ya conserva mappings
y convierte texto/escalar a `action`; el inspector define `_inspect_file` y su regex
de defines evita absorber saltos. Linux update usa `staged_update.py`, el modo dev
propaga fallos y Windows selecciona/verifica su entorno. La ejecución histórica de
reproducciones no valida estas correcciones en el checkout actual.

La auditoría actual corrigió credenciales sin enmascarar en `custom_presets`, valores
de excepciones en logs/eventos de controladores y seis sinks HTML de métricas del mapa.
`all_presets` y `custom_presets` comparten la proyección pública sanitizada sin cambiar
credenciales operativas. Origin conserva la admisión amplia de LAN privada; no es
una política estricta de mismo origen. Esa revisión fue estática; posteriormente
el usuario autorizó QA aislado para la actualización actual. Sus resultados se
registran por herramienta y no se atribuyen a la revisión histórica.

Se corrigieron las afirmaciones documentales localizadas sobre LQI, salud, trace,
heatmap, configuración, resultado TX, errores Companion, rango SF, cifrado,
dependencias SDK, framing y enlaces ligados al equipo. La revisión semántica es
dirigida por evidencia; el inventario estructural no certifica toda la prosa.

| Hallazgo | Evidencia reproducible y estado |
| --- | --- |
| MQTT admin global pierde el comando textual/escalar y puede perder `action` al extraer `params`. | `src/mqtt_dispatcher.py`, `_handle_admin_request`: inicia `params={}` y entrega ese dict aunque sólo haya asignado `action`. Pendiente de corrección de código y regresión autorizada; usar JSON con `action` en el objeto entregado al handler. |
| Inspector oficial falla con `--path <archivo>`. | `.agents/skills/meshcore-source-inspector/scripts/inspect_meshcore_ast.py:86` llama `_inspect_file`, inexistente. Agente investigador reprodujo `AttributeError`; el modo directorio funcionó. Pendiente de reparación. |
| Inspector puede citar línea anterior. | Extrajo `ADV_TYPE_NONE` como línea 6; `rg` muestra línea 7. Regex `^\s*` absorbe el salto. Cotejar siempre líneas/offsets con parser y fuente. |
| Linux update puede borrar su propio origen. | `install.sh`, rama `--update`: borra `$INSTALL_DIR/src` antes de copiar `$CURRENT_DIR/src`. Si ambas rutas coinciden, el origen desaparece. No ejecutado; pendiente de parche. |
| Linux dev anuncia éxito pese fallos. | `install.sh`, rama `--dev`: usa `|| true` para deps, Chromium y runner, y termina 0. El runner cubre pytest/mypy/ruff/docs; no una auditoría Bandit independiente. No ejecutado. |
| Instalador Windows no selecciona el venv detectado ni valida todos los códigos de salida. | `install.ps1`: usa Python de PATH, no crea/activa `.venv`, no comprueba `$LASTEXITCODE`; `-Run` depende del cwd. No ejecutado; pendiente de parche. |
| Helper de arquitectura anuncia conformidad total con inspección parcial. | `.agents/skills/software-architecture-patterns/scripts/audit_architecture.py`: omite errores de parseo y módulos ausentes. No ejecutado; no interpretar su banner como certificación. |
| Skill API describe mocks antiguos pese un helper local ya modificado. | `.agents/skills/api-design-testing/SKILL.md` y `scripts/validate_api_contract.py` dentro de esa skill divergen: el helper del checkout utiliza temporales/configuración aislada/hardware falso, pero sólo cubre el router. No se incorpora esa modificación previa del helper a esta publicación ni se ejecuta. Pendiente de conciliar junto con su cambio original. |
| Snapshot upstream/proveniencia parcial. | Once copias sin Git y discrepancia openhop_core. Falta comparar SHA con upstream o acreditar archivos de origen; conservar como limitación. |

La semántica comprobada del firmware está en `AdvertDataHelpers.h` (tipo RF en
cuatro bits bajos de flags), `MyMesh.cpp` (errores y serialización de contactos),
`CommonCLI.cpp` (SF), `Utils.cpp` (AES128) y parsers serial del SDK/firmware.
Companion serializa contactos como 147 bytes de datos más un opcode; esto no es
`sizeof(ContactInfo)` ni implica packing C++ idéntico.

## Skills y agentes

El catálogo inicial contenía 20 skills propias y los paquetes externos Archify y
ui-ux-pro-max. Se agregan dos skills propias; no se actualizan vendors ni herramientas
globales. Se consultó [skills.sh](https://www.skills.sh/) para descubrimiento; las
necesidades particulares del repositorio se cubrieron con skills locales pequeñas,
evitando instrucciones de frameworks ajenos a esta SPA.

| Tarea | Skills |
| --- | --- |
| Inventario/procedencia documental | [project-reference-audit](../.agents/skills/project-reference-audit/SKILL.md), domain-adr-keeper, meshcore-source-inspector. |
| Instalación/publicación | [installer-release-maintenance](../.agents/skills/installer-release-maintenance/SKILL.md). |
| Python/concurrencia | python-patterns-typing, async-concurrency-engineering, asyncio-profiler-leak-detector. |
| Protocolo/simulación | lora-frame-validator, lora-packet-simulator, distributed-mesh-simulation. |
| API/frontend | api-design-testing, contract-openapi-sync, html-css-modern-js, web-ui-design-system, web-browser-inspection. |
| Arquitectura/refactor | clean-code-solid, refactoring-clean-architecture, gof-design-patterns-expert, software-architecture-patterns. |
| QA/seguridad/búsqueda | bridge-test-runner, security-code-auditor, tgrep-code-search (rg si no está instalado). |

AGENTS.md conserva los roles 0–5 y agrega Agente 6 (documentación/procedencia) y
Agente 7 (instalación/publicación). Los perfiles son contratos de delegación, no
daemons ni agentes persistentes instalados. El principal asigna archivos y mantiene
el ledger; las tareas paralelas de esta revisión fueron de sólo lectura.

## Evidencia y reproducción

Entorno histórico de septiembre: `.venv/Scripts/python.exe`, Python 3.12.14; `python` y
`tgrep` no estaban en PATH, se utilizó `rg`. No se modificó el intérprete.

```powershell
.venv/Scripts/python.exe scripts/inventory_project_knowledge.py
.venv/Scripts/python.exe scripts/validate_project_docs.py
.venv/Scripts/python.exe .agents/skills/domain-adr-keeper/scripts/audit_domain_adr.py
```

El inventariador imprime JSON sin importar el bridge, leer `.env`, escribir estado
operativo, actualizar repositorios o ejecutar suites. El snapshot publicado se
guarda deliberadamente como `docs/PROJECT_INVENTORY.json`; regenerarlo después de
cambios para actualizar hashes. No se incluye a sí mismo en el listado documental.

La primera comprobación estructural revisó 44 documentos/skills con cero incidencias;
los ocho ADRs pasaron secuencia y secciones. La evidencia final, la validación de
las nuevas skills y la publicación Git se registran en el ledger de esta tarea.
El validador estructural excluye informes históricos y vendors; no comprueba anchors,
URLs remotas ni semántica. Los enlaces URI antiguos a archivos no eran detectados.

No se ejecutaron pytest, Playwright, fuzzing, Bandit completo ni el runner de QA,
no se arrancó el bridge, no hubo RF/broker/n8n operativos ni mediciones de carga.
Las instrucciones de AGENTS.md requieren petición explícita para suites. La
comprobación de enlaces, lectura de parsers y metadatos Git acreditan únicamente
los aspectos indicados aquí. Las vulnerabilidades, compatibilidad hardware y
actualidad de todas las dependencias quedan fuera de esta revisión documental.
