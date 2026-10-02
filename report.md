# Auditoría por capas de MeshCore Bridge

Auditoría: 2026-10-01 a 2026-10-02 (America/New_York). Revisión base: `c071e61c965ce6db7ae2b8c454d9099c263c96b5`, rama `main`.

## Alcance y método

Auditoría solicitada del código, instrucciones, agentes y skills. No se corrigen defectos ni se cambian contratos, fixtures mantenidas o expectativas para hacer pasar pruebas. Las capas se revisan consecutivamente con agentes especializados; el principal integra la evidencia. Los hallazgos históricos se vuelven a comprobar antes de presentarlos como vigentes.

Las reproducciones utilizan adaptadores virtuales, mocks, archivos temporales y servicios propios en loopback. Las reproducciones finales bloquean `.env` y usan estado sintético; no se usa radio física ni broker de producción. Una primera prueba del comando CLI channels pudo consultar su ruta hardcodeada antes de interceptar open; no se conservaron sus contenidos y la reproducción final usa mock_open (ADM-09). Los permisos elevados del usuario no anulan las restricciones de ejecución del entorno. Los archivos previos de `scratch/` quedan fuera de la tarea.

Cada defecto registra ubicación, causa, impacto, reproducción, resultado esperado y observado. Las mejoras, sospechas y limitaciones se distinguen de los errores comprobados. Una suite aprobada no acredita ausencia de defectos ni interoperabilidad RF.

## Entorno

Windows; Python local `.venv/Scripts/python.exe` 3.12.14. Versiones instaladas: pytest 9.1.1, pytest-asyncio 1.4.0, pytest-cov 7.1.0, mypy 2.3.1, ruff 0.16.3, Bandit 1.9.4, Playwright 1.62.0 y SDK meshcore 2.3.8. Compatibilidad declarada del proyecto: Python >=3.10; ejecutar en 3.12 no acredita funcionamiento en 3.10.

Inventario inicial: 59 módulos Python de producción, 21.780 líneas físicas, 63 módulos de pruebas y 24 skills de primer nivel. El alcance de lectura y las limitaciones de cada fase se detallan en su sección.

Severidad: P1 = alta (pérdida de datos, vulneración de invariantes o control relevante); P2 = media (comportamiento incorrecto observable); P3 = baja/mejora de precisión. No se asigna CVSS ni se atribuye explotación remota a una reproducción de función aislada.

Evidencia local: `scratch/qa-results/audit-20261001/` y `scratch/audit-20261001/governance/`. Estos directorios contienen únicamente artefactos de esta auditoría. Los comandos se ejecutan desde la raíz con `.venv/Scripts/python.exe`; los paths relativos de cada agente se resuelven contra su carpeta indicada. El informe conserva resultados relevantes aunque los artefactos temporales no se publiquen.

Verificación de gobernanza: `scripts/run_quality_checks.py --only-docs`: 54 documentos/skills comprobados, 0 incidencias estructurales. Cuatro módulos de tests de helpers/calidad/inspector/aislamiento: 29 aprobadas en 8,16 s; una advertencia por permisos de caché de pytest, sin fallo de expectativas. Las fases posteriores usan una caché específica de auditoría para no repetir esa limitación ambiental.

## Secuencia de capas

1. Gobernanza, instrucciones, agentes, skills y documentación.
2. Protocolo, tipos, framing y decodificación frente a referencias oficiales.
3. Dominio, contactos, roles, resolución de destinos y persistencia.
4. Pipeline asíncrono, colas, airtime, ciclo de vida, administración, MQTT y Companion TCP.
5. API HTTP/WebSocket, configuración, validación y seguridad.
6. SPA, contratos REST/WebSocket, accesibilidad y navegador aislado.
7. Instaladores, dependencias, entrypoints, servicio y CI.
8. Verificación completa, consolidación y limitaciones.

## Resultado y prioridades

Auditoría completada en el alcance documentado, con siete capas consecutivas y una verificación global. **No se corrigió el código, los tests mantenidos, las instrucciones ni las skills.** Los reproducer propios confirman la presencia de cada comportamiento descrito; su exit 0 no significa que el componente defectuoso sea correcto. Se conservaron también intentos fallidos de fixtures y restricciones del entorno.

Los cinco hallazgos de prioridad P1 son:

| Hallazgo | Resultado observado | Alcance de evidencia |
|---|---|---|
| HTTP-01 | Exportación de PSK y lectura de logs sin API key mediante barra final | Peticiones HTTP reales a servidor aislado |
| ADM-07 | Contraseña administrativa íntegra en logs y evento MQTT | Handler real, contraseña y publicación sintéticas |
| MT08 | Nombre visible suplanta whitelist y genera comando administrativo | Código JS real del export n8n, sin enviar el comando |
| INS-05 | Update reemplaza autenticación y bind del broker por acceso anónimo a todas las interfaces | Instalador copiado, archivo sintético y systemctl simulado |
| Gobernanza, defecto 1 | Helper ADR sobrescribe una decisión existente si hay huecos | Archivos de documentación sintéticos |

Además se documentan errores de protocolo/telemetría, identidad y persistencia, deduplicación, colas, administración, contratos REST/WS, SPA, accesibilidad e instaladores. Los hallazgos de API interna, simulación, configuración atípica y QA mantienen esas condiciones expresas. Las mejoras documentales no se contabilizan como vulnerabilidades funcionales. No se ofrece una suma de observaciones como si fueran defectos independientes.

Suite completa: **663 passed, 1 skipped**, cobertura de líneas de src **66,93%**; mypy --strict aprobado en 59 archivos, Ruff aprobado y validación estructural de 54 documentos/skills sin incidencias. La suite no contempla varios defectos reproducidos fuera de sus expectativas actuales. El detalle y el comando reproducible están en capa 8.

Se utilizaron los tres agentes especializados de gobernanza, protocolo/dominio y subsistemas backend/API con propiedad de lectura definida por fase. Alcanzaron el límite de uso durante la preparación del navegador; el principal cerró SPA, instaladores y consolidación. Las skills aplicadas constan por sección. MCP de Codex se usó para inspeccionar adjuntos y mostrar el informe; no se llamó SSH operativo. Las capas con lectura dirigida y los componentes no verificados exhaustivamente se enumeran expresamente.

Deduplicación: PRT-08 remite al defecto 6 de gobernanza; RC-05 amplía RUN-05; RC-S01 verifica la divergencia documental API ya identificada en capa 1. Sus detalles se conservan por trazabilidad, sin sumarlos dos veces. Los hallazgos históricos refutados o ya resueltos se distinguen de los actuales.

## Capa 1 — Gobernanza, agentes, skills y documentación

Estado: cerrada. Sin cambios de producción, documentación mantenida, skills ni tests. Se usaron project-reference-audit y domain-adr-keeper. Catálogo: 24 entradas top-level, 22 propias y 2 vendors; se leyeron las 22 skills propias y se verificó parseo de los 17 helpers propios. Revisión semántica dirigida de helpers; bundles Archify/ui-ux-pro-max sin auditoría exhaustiva.

Reproducción única: `.venv/Scripts/python.exe scratch/audit-20261001/governance/reproduce_governance.py`. Resultado final: exit 0; **15 observaciones confirmadas**, con assertions que verifican la manifestación del defecto, no la corrección del helper. Evidencia: `results.json`, `run-output.txt`. Fixtures sintéticos exclusivamente bajo este directorio. No aplicación importada, .env, datos operativos, radio, broker ni servidor.

### Defectos confirmados

1. **P1 — Destrucción de historial ADR ante huecos**. `.agents/skills/domain-adr-keeper/scripts/audit_domain_adr.py:75,113,127`. `next_num=len(existing)+1` y `write_text` sobrescriben sin exclusión. Con 0001-first.md y 0003-same.md, crear título `same` reescribe 0003-same.md; `original_history_lost=true`. `main --new` prosigue aunque `audit_adrs` haya detectado secuencia rota. Esperado: nuevo número máximo+1 o rechazo; nunca reemplazar ADR existente.

2. **P2 — Auditor async no inspecciona módulos anidados y oculta fallos de parseo**. `.agents/skills/async-concurrency-engineering/scripts/audit_async_concurrency.py:44,57,65`. Fixture src/web/blocking.py con `async def handler(): time.sleep(1)` produce main exit 0 y «100% conformidad»; invocar detector sobre ese archivo sí identifica bloqueo. Archivo sintácticamente inválido devuelve [] por `except Exception: pass`. Esperado: inspección recursiva y errores explícitos/inconcluso. Son fallos de la herramienta, no evidencia de bloqueo real en producción.

3. **P2 — Auditor async acusa trabajo correctamente delegado al hilo**. Mismo helper:30-43. `async def handler` define función síncrona `work` con time.sleep y ejecuta `await asyncio.to_thread(work)`; ast.walk recorre cuerpo de la función anidada y acusa bloqueo del event loop. Confirmado fixture offloaded.py. Esperado: no atribuir al cuerpo async el trabajo de otro contexto de ejecución.

4. **P2 — Auditor arquitectura emite violaciones pero sale 0 y omite imports relativos**. `.agents/skills/clean-code-solid/scripts/audit_architecture_contracts.py:85,103,128`. Dominio ficticio `import src.web`: violación detectada, main devuelve None y proceso exit 0 (`GOV-ARCH-PROCESS-EXIT`). `from . import serial_driver` devuelve lista vacía pese importar infraestructura. Esperado: código no cero y resolución del ImportFrom.module=None/level. No afirmar aislamiento completo por el banner.

5. **P2 — Validador de tramas falla en modalidad documentada --file**. `.agents/skills/lora-frame-validator/scripts/validate_frame.py:336`. No importa Path. Comando sobre frame.bin aislado produce exit 1 y `NameError: name 'Path' is not defined`. Modalidad recomendada en SKILL.md:46.

6. **P2 — Validador de tramas da falso VALID y decodifica mal el formato raw propio**. `.agents/skills/lora-frame-validator/scripts/validate_frame.py:184,227-232,255`. Supone header de 8 bytes sin hop; formato real src/protocol_types.py:27,291 es 9 bytes `<BBHHBH`. Fixture con hop=4,payload_len=1,payload='x' decodifica longitud 260 y payload 0078 de 2 bytes. Además cabecera sintética de 8 bytes con longitud declarada 65535 y cero payload (CRC correcto) se acepta VALID. Esperado: layout explícito/correcto y comprobación de longitud, o anunciar sólo checksum genérico; nunca presentarlo como validación integral raw.

7. **P2 — Validador de tramas no propaga CRC inválido en código de salida**. `.agents/skills/lora-frame-validator/scripts/validate_frame.py:315,367`. CLI `--hex AA01020355 --format json` responde CRC_MISMATCH pero exit 0. Esperado: no cero para uso de validación automatizada. El resultado JSON sí permite al consumidor detectar el fallo si lo interpreta.

8. **P2 — Validador tipado omite cuatro clases de parámetros**. `.agents/skills/python-patterns-typing/scripts/verify_python_standards.py:40,68`. `def example(posonly, /, *args, kwonly, **kwargs) -> None` devuelve [] pese cuatro parámetros sin tipo. Sólo recorre args.args. Esperado: revisar posonlyargs, kwonlyargs, vararg, kwarg; mensaje «100% anotaciones completas» inexacto. Mypy es la comprobación canónica y la skill ya declara carácter orientativo.

9. **P3 — Paridad REST pierde llamadas frecuentes y acepta subrutas inventadas**. `.agents/skills/contract-openapi-sync/scripts/verify_api_parity.py:48,82`. Fixture fetch('/api/status'), fetch('/api/nodes?limit=10'), fetch(`/api/contacts/${encodeURIComponent(key)}`) detecta sólo status. `is_route_covered('/api/status/not-an-endpoint', {'/api/status'})=true`. Esperado: declarar cobertura incompleta de estas formas e investigar prefijos antes de atribuir rutas válidas. Skill advierte comparación parcial, por lo que esto no es una vulnerabilidad de la API ni un contrato real probado.

10. **P3 — Inspector marca packed después de pragma pack(pop)**. `.agents/skills/meshcore-source-inspector/scripts/inspect_meshcore_ast.py:166`. Tras push(1), struct Packed, pop y struct Normal, ambos reciben is_packed=true. Esperado: conservar estado de packing o resultado desconocido; disclaimer sobre ABI no justifica la marca packed errónea. Fixture packed_fixture.h.

11. **P2 — Manual de extensión describe APIs inexistentes**. `docs/SYSTEM_LAYERS_MANUAL.md:100,106,397-399,418-420`. AST de clases actuales confirma ausencia de WebAPIRouter.register_route, MeshCoreBridge.send_text, AdminCommandHandler.execute_command y NodeRegistry.list_all_nodes. La receta `self.register_route(...)` no puede seguirse sobre el router del checkout. Reproducción GOV-DOC-MISSING-API confirma las cuatro ausencias sin importar aplicación. Esperado: ejemplos y matriz acordes a API implementada. Son errores documentales, no defectos de esos métodos inexistentes.

### Divergencias documentales comprobadas

- **P3 — Modelos de capas incompatibles**. `docs/SYSTEM_LAYERS_MANUAL.md:30-63` define C4 dominio/protocolo y C5 infraestructura/persistencia; `docs/AUDIT_REPORT_LAYER_BY_LAYER.md:12-18` dice seguir ese mismo modelo pero define C4 persistencia y C5 hardware, asigna ProtocolTypes a C3 y RxEventRouter a C2. No hay correspondencia canónica única; dificulta propiedad e integración. Evidencia textual directa.
- **P3 — Estado de informe antiguo desactualizado**. `docs/AUDIT_REPORT_LAYER_BY_LAYER.md:3` mantiene «En Ejecución, fases 1/2» aunque contiene recapitulación de cinco capas en sección 14. No reutilizar sus defectos como vigentes; requiere validar individualmente contra checkout.
- **P3 — Pendientes del mapa de conocimiento ya no vigentes**. `docs/PROJECT_KNOWLEDGE.md:110-111` afirma que `_inspect_file` no existe y regex `^\s*` cita línea anterior. Checkout actual tiene `_inspect_file` en inspector:105 y regex `[ \t]` en :121. La prueba sobre archivo packed_fixture.h funciona. No catalogar esas dos afirmaciones históricas como defectos actuales del inspector.
- **P3 — Skill API contradice helper actualizado**. `.agents/skills/api-design-testing/SKILL.md:69` dice mocks antiguos/no garantía de aislamiento; helper actual describe aislado y implementa temporales/env limpia/dotenv mock en validate_api_contract.py:29-64. No se ejecutó este helper en esta capa; el aislamiento efectivo debe comprobarse durante la capa HTTP, no inferirse sólo de su docstring.
- **P3 — Manual conserva enlaces personales no portables**. `docs/SYSTEM_LAYERS_MANUAL.md:412-451` contiene 8 referencias `file:///c:/Users/Ruby/Desktop/...`; validator docs:29 ignora todos los esquemas, incluyendo file://, por lo que «54 files 0 issues» del principal no acredita portabilidad. No se trata de enlaces HTTPS externos.

### Mejoras de instrucciones (sin catalogarlas como fallos de producción)

- AGENTS.md:264 instruye simular reinicio con pkill; precisar fixtures aisladas y PID del proceso de prueba para no sugerir detener estaciones operativas.
- Agente 1: tipos exclusivamente frozen/enums es demasiado amplio si futuras interfaces Protocol o aliases forman parte de protocol_types.py; aclarar valores de dominio vs interfaces/estado.
- Separar valores wire de advert de capacidades (p.ej. NONE no demuestra capacidad chat); verificar inferencias contra firmware en capa protocolo.
- AGENTS permite publicar origin/main al finalizar; documentar manejo seguro de checkout sucio/hunks y rama distinta (installer skill ya trata parte).
- tgrep skill promete latencia submilisegundo sin benchmark; thresholds 50/70 líneas y 5/6 parámetros en clean-code-solid son guías divergentes, no bugs.
- Bundles terceros traen frameworks ajenos a Vanilla; `.agents/README.md` ya establece precedencia adecuada. No ejecutarlos indiscriminadamente como suites.

### Límites

Sólo esta capa, sin auditoría runtime ni promesa de «todos los errores». Helpers project-reference inventory/document validator no comprueban semántica, anchors ni upstream; suites mantenidas/ruff/mypy/navegador se coordinarán en sus capas por principal. Scripts de vendors, referencias remotas y hardware no ejecutados. El resultado exitoso del reproducer confirma presencia de problemas actuales, no que herramientas auditadas hayan pasado.

### Complemento de gobernanza — métricas de arquitectura

#### GOV-12 [P3] El helper presenta una cuenta AST aproximada como complejidad McCabe

Fuente: `.agents/skills/clean-code-solid/scripts/audit_architecture_contracts.py:45-56`. `ast.walk` agrega decisiones de funciones internas a la función contenedora e ignora expresiones condicionales `IfExp`. Reproducción `.venv/Scripts/python.exe scratch/qa-results/audit-20261001/architecture_metrics.py`, exit 0: función con un único ternario devuelve score1 aunque hay dos caminos; outer que sólo define/devuelve inner devuelve score2 por el if que vive dentro de inner. Expected contabilizar decisiones por función y el ternario. Una tercera observación muestra que un `with` sin decisión explícita añade1; depende del modelo de CFG elegido y se conserva como precisión del modelo, no como defecto independiente.

Ejecutado sobre todo src: cero imports prohibidos detectados por sus reglas y **55 avisos de score >20**. El JSON conserva los 55 candidatos. No se presentan como 55 defectos funcionales ni valores exactos de McCabe. Mejorar el nombre del score y sus límites o usar una implementación validada antes de adoptar esos números como gate. El banner «100% OK» sólo refleja sus reglas parciales de imports, ya limitadas en GOV-04.

## Capa 2 — Protocolo, tipos y adaptación SDK

### Framing, telemetría y tipos oficiales

Auditoría del checkout local, 2026-10-01. No se modificó código de producción, referencias oficiales ni tests mantenidos. Reproducciones offline, sin UART/RF/broker. `dotenv.load_dotenv` se parcheó antes de importar `src`, ya que su inicializador importa infraestructura.

#### Evidencia y verificación

- `reproduce.py` ejecuta 133 verificaciones: 19 desajustes reproducidos y 114 controles satisfactorios, incluyendo todos los valores enum compartidos con la referencia SDK. El script **afirma el comportamiento defectuoso observado**, por eso salir 0 no significa que se solucionó. Expected/actual completos en `reproduce.json`.
- Pytest: **25 passed in 4.66s**; `pytest.txt`, `pytest.xml`, `coverage.json` y `.coverage` en este directorio. Cobertura de suite dirigida, no cobertura de toda la aplicación; el denominador global `src` dio 25% por importar infraestructura.
- Ruff: sin hallazgos en los seis archivos asignados; `ruff.json` contiene `[]`.
- Mypy strict: seis archivos sin errores, con `--follow-imports=skip`; `mypy.txt`. No acredita el tipado de dependencias ni del proyecto completo.
- Skills aplicadas: `meshcore-source-inspector` y `lora-frame-validator`; salida de inspector `advert-constants.json`; salida del validador `frame-validator.json`.

Comandos reproducibles desde la raíz (PowerShell):

```powershell
$env:COVERAGE_FILE=(Join-Path $PWD 'scratch/qa-results/audit-20261001/protocol/.coverage')
.venv/Scripts/python.exe -m pytest tests/test_protocol_types.py tests/test_sensor_decoder.py tests/test_lqi_routing.py tests/test_packet_deduplicator.py tests/test_serial_adapter.py::TestSerialAdapter::test_raw_framing_adapter_roundtrip -o cache_dir=scratch/qa-results/audit-20261001/protocol/cache --basetemp=scratch/qa-results/audit-20261001/protocol/temp --cov-report=json:scratch/qa-results/audit-20261001/protocol/coverage.json --junitxml=scratch/qa-results/audit-20261001/protocol/pytest.xml
.venv/Scripts/python.exe scratch/qa-results/audit-20261001/protocol/reproduce.py
.venv/Scripts/python.exe -m ruff check src/protocol_types.py src/sensor_decoder.py src/lqi_engine.py src/deduplicator.py src/serial/raw_framing.py src/serial/serial_base.py --output-format json --no-cache
.venv/Scripts/python.exe -m mypy --strict --follow-imports=skip --cache-dir=scratch/qa-results/audit-20261001/protocol/mypy-cache src/protocol_types.py src/sensor_decoder.py src/lqi_engine.py src/deduplicator.py src/serial/raw_framing.py src/serial/serial_base.py
.venv/Scripts/python.exe .agents/skills/meshcore-source-inspector/scripts/inspect_meshcore_ast.py --path reference/meshcore/src/helpers/AdvertDataHelpers.h --format json --out scratch/qa-results/audit-20261001/protocol/advert-constants.json
$frameHex=Get-Content scratch/qa-results/audit-20261001/protocol/sample_raw.hex
.venv/Scripts/python.exe .agents/skills/lora-frame-validator/scripts/validate_frame.py --hex $frameHex --format json
```

#### PRT-01 — P2 — Se pierden las unidades explícitas de batería y voltaje

**Código:** `src/sensor_decoder.py:350` `_extract_power_telemetry`, y `:253` `_map_lpp_item_to_res`; el paso por `clean_battery_input` transforma porcentajes en floats y se aplica `normalize_battery` basado en heurísticas aun cuando el nombre del campo ya fija unidades.

**Esperado / real reproducido:** `{"battery_pct":4}` → 4% / **83%**; LPP `percentage=4` → 4% / **83%**; `{"voltage_v":12.0}` → 12 V / **3.14 V**; `{"battery_mv":100}` → 100 mV / **100000 mV**. Otro subcaso: medición explícita `battery_pct=80, voltage_v=3.2` → conserva medición 80% / **17%**, por sobreescritura con curva fija de celda. Esta última reconciliación es intencional en el código, pero hace desaparecer la medición real y asume una química de batería sin indicar que el dato se reemplazó por estimación.

**Impacto:** telemetría y UI pueden mostrar alta carga cuando el sensor informa batería casi agotada; fuentes alimentadas a 12 V se presentan como una celda a 3.14 V.

**Alcance de prueba:** invocación real del normalizador, sin inyectar evento por radio. Ruta de consumo productiva inspeccionada: `NodeRegistry._extract_telemetry_fields()` (`src/contact_manager.py:1262`) delega a este módulo y `record_packet()` (`:1290`) usa el resultado; `src/rx_router.py:528,804` también lo consume. No se probó el flujo RF→UI completo.

**Mejora propuesta, no aplicada:** respetar unidades declaradas por clave y tipo LPP; separar porcentaje medido de estimación desde voltaje y declarar fuente/curva.

#### PRT-02 — P2 — Conversión de airtime depende de valor y confunde segundos/milisegundos

**Código:** `src/sensor_decoder.py:440` `_extract_radio_telemetry`, selección de `airtime_ms/tx_air_secs/airtime` y condición `clean_at < 10000 and "tx_air_secs" in data`.

**Esperado / real reproducido:** estado oficial con `airtime=30` segundos → **30000 ms / 30 ms**; `tx_air_secs=10000` → **10000000 ms / 10000 ms**; `airtime_ms=123, tx_air_secs=1` → **123 ms / 123000 ms**, aunque el campo en ms tiene prioridad.

**Fuente oficial:** `reference/meshcore/examples/simple_repeater/MyMesh.h:51` declara `total_air_time_secs`, y `MyMesh.cpp:224` lo llena mediante `getTotalAirTime()/1000`. El parser oficial `reference/meshcore_py/src/meshcore/parsing.py:96` y `src/protocol_types.py:328` exponen este dato como `airtime` sin renombrar unidades. El layout de estado usa campos enteros LE del target; la reproducción construye 56 bytes sintéticos con el campo de offset 16, sin asumir packing de otra plataforma.

**Impacto:** estadísticas normalizadas de airtime incorrectas hasta factor 1000. No se atribuye este error al algoritmo `AirtimeTracker` ni se acredita efecto sobre regulación RF.

**Alcance de prueba:** `parse_status_response()` → `extract_telemetry_fields()` confirmado en memoria; consumidores productivos iguales a PRT-01, sin extremo a extremo.

#### PRT-03 — P2 — GPS raw decodificado no se aplana y desaparece del resumen

**Código:** `src/sensor_decoder.py:217` coloca GPS bajo `res["gps"]`; `:530` busca coordenadas en el `data` original, no en el resumen decodificado. Además `:298` `_parse_lpp_gps_val` reconoce `alt/altitude`, no `altitude_m`.

**Reproducción:** `raw_bytes` con GPS `(40.7128,-74.006,15.5)` obtiene `res["gps"]` correcto, pero `res.get("latitude")` es **None** y `format_telemetry_summary()` no muestra coordenadas. Lista LPP `{"type":"gps","value":{"latitude":40.7128,"longitude":-74.006,"altitude_m":15.5}}` pierde la altitud: **None**, esperado 15.5.

**Impacto:** consumidor que utiliza los campos canónicos planos no recibe la posición, aunque el decoder sí la descifró.

**Alcance:** utilidades de producción ejecutadas; no se verificó actualización del mapa por WebSocket. Ruta productiva estática `NodeRegistry.record_packet` y `src/rx_router.py:1006` para el resumen.

#### PRT-04 — P3 — Truncado de texto raw rompe caracteres UTF-8

**Código:** `src/protocol_types.py:438` corta alias a 15 bytes y texto a 238 bytes, sin respetar frontera de caracteres; `:444` decodifica con `errors="replace"`.

**Reproducción:** alias `"a"*14+"ñ"` y texto `"a"*237+"ñ"`, ambos codificados y decodificados por las funciones reales, terminan en **�**. Se esperaba truncar a un prefijo válido UTF-8 o rechazar el exceso.

**Alcance:** **formato raw propio**, no mensaje oficial Companion ni interoperabilidad RF. La clase pública pierde información en un roundtrip; no se encontró consumo de estas clases en el envío físico del SDK.

#### PRT-05 — P3 — Raw framing descarta comienzo de trama válida tras ESC truncado

**Código:** `src/serial/raw_framing.py:67` aborta si llega SOF/EOF después de ESC; consume ese SOF en vez de usarlo como resincronización.

**Reproducción:** una trama raw correcta por sí sola produce 1 frame; prefijarla con `AA 1B` produce **0 frames**. Expected=1, actual=0. El nuevo SOF inicia una trama válida y es una frontera suficiente para recuperarse, como hace la rama de SOF inesperado sin ESC.

**Alcance:** parser en memoria, sin UART. Es una pérdida puntual ante flujo malformado; no se atribuye al framing oficial `<`/`>`.

#### PRT-06 — P3 — Adaptador raw informa envío aunque no tiene transporte

**Código:** `src/serial/raw_framing.py:111` `send_message` devuelve siempre `{"status":"SENT_RAW","text":...}`, incluso recién construido y desconectado. No serializa trama, no despacha callback de salida ni escribe UART.

**Reproducción:** llamada asíncrona con texto `hello`, sin `connect()`, devuelve **SENT_RAW**; semántica de capacidad esperable: `NOT_SUPPORTED` o un resultado equivalente explícito de simulación.

**Alcance/limitación:** comportamiento de clase pública confirmado; **no se confirmó un flujo productivo que seleccione este adaptador**. Su docstring admite que es framing en memoria. Es deuda del contrato de resultado y puede tratarse como mejora si sus consumidores consideran `SENT_RAW` simulación expresamente.

#### PRT-07 — P3 — LQI trata métricas NaN como enlace excelente; EMA inicial ignora límite

**Código:** `src/lqi_engine.py:45` clamping con `min/max` sin validación finita; `:81` devuelve instantáneo directamente cuando `prev_lqi<=0`.

**Reproducción:** `compute_instant_lqi(nan,nan)` → **100**, `classify_lqi_status` → **EXCELLENT**; `update_ema_lqi(0,200)` → **200** (esperado máximo 100 según contrato de score).

**Alcance:** helper real ejecutado. Para NaN existe ruta estática productiva directa `src/rx_router.py:1000`, con `float()` y sin filtro finito en ese callsite, por lo que cadenas `"nan"` también pasan la conversión local; no se inyectó evento end-to-end y podría haber validación previa según origen. La EMA=200 sólo se acreditó con llamada aislada: `NodeRegistry` calcula primero un instantáneo acotado, por lo que no se afirma que ese 200 sea alcanzable desde su flujo normal. Sus pruebas de extremos pasan; falta caso finito/NaN.

#### PRT-08 — Remisión al defecto 6 de gobernanza: helper valida cabecera raw equivocada

**Código de herramienta:** `.agents/skills/lora-frame-validator/scripts/validate_frame.py:223-232` presupone header de **8 bytes**, lee longitud en `[6:8]` y extrae payload desde 8. El contrato real `FrameHeader.pack()` es `<BBHHBH` (**9 bytes**, hop en 6, longitud en 7:9).

**Reproducción:** `sample_raw.hex` contiene `AA84010200030000010078CAF255`, frame real con payload **1 byte `78`**, header con hops=0 y CRC correcto. La herramienta imprime **declared_payload_len=256, payload_length=2, payload_hex=0078, validation_status=VALID** sin errores. El parser productivo acepta esta trama correcta y devuelve 1 frame.

**Impacto:** evidencia QA engañosa y bytes de payload mal interpretados; el validador no acredita el contrato de longitud que la skill pretende inspeccionar. **Afecta herramienta de auditoría, no parser productivo.**

**Alcance:** CLI real de la skill ejecutada, salida conservada. Fuente del contrato `src/protocol_types.py:274`, `docs/PROTOCOL_SPEC.md:146`.

#### Discrepancias y mejoras, sin afirmar bugs de interoperabilidad

- **PRT-M01 — LPP parcial:** el enum de `src/sensor_decoder.py` omite tipos oficiales `CURRENT(117)`, `FREQUENCY(118)`, `ALTITUDE(121)`, `POWER(128)`, etc. Al recibir 117 seguido de temperatura válida, devuelve un `unknown` y pierde la temperatura. Reproducido en `reproduce.json`. La descripción admite soporte de un subconjunto: clasificar como **mejora de soporte/skip seguro de tipos oficiales de tamaño conocido**, no automáticamente como bug por no implementar toda la norma. Fuentes `reference/meshcore/src/helpers/sensors/LPPDataHelpers.h:20-35` y su `skipData()`.
- **PRT-M02 — conflicto de voltaje firmado:** código `src/sensor_decoder.py:116-124` convierte uint16>32767 a negativo siguiendo `reference/meshcore_py/src/meshcore/lpp_json_encoder.py` (SDK). Firmware `LPPReader.readVoltage()` y `LPPWriter.writeVoltage()` en `LPPDataHelpers.h` usan unsigned; `docs/PROTOCOL_SPEC.md:364` también promete unsigned. Fixture 40000→**-255.36 V**, mientras firmware/doc→**400 V**. **Discrepancia firmware/SDK/documentación**, no fallo universal: para baterías normales no hay divergencia, y la pila SDK interpreta lo mismo que bridge. Documentar la elección explícitamente.
- **PRT-M03 — documentación de códigos incompleta:** el enum bridge contiene `CommandType.RUN_CLI_COMMAND=66` y `PacketType.CLI_REPLY=29`; las tablas de `docs/PROTOCOL_SPEC.md` §9 no los incluyen. La referencia SDK local tampoco los declara. No inferir soporte por ese SDK; mantener procedencia por firmware/build y señalar nombres históricos distintos (`DEVICE_QEURY` y `PUSH_CODE_NEW_ADVERT`) al comparar enums. Todos los valores presentes en ambos lados coinciden (114 controles).
- **PRT-M04 — nombres raw históricos:** docstrings `TextMessagePayload` y `NodeAdvertisement` dicen `OpCode 0x02/0x03`, mientras dispatcher raw usa `PacketType.CHANNEL_MSG_RECV(8)` y `CONTACT(3)`. El módulo global aclara que es formato propio, pero esos comentarios locales pueden confundir comando Host y respuesta. Mejora documental, no error de bytes confirmado.

#### Sin hallazgo confirmado y límites

- `PacketDeduplicator` usa reloj monotónico y lock alrededor de chequeo+inserción. Pasaron deduplicación, TTL y capacidad. No se midió contención/performance multihilo; el comentario de "lock reentrante" es impreciso porque se usa `threading.Lock`, pero no se halló anidación que reproduzca deadlock en el scope. No se calificó la ventana desde primera aceptación como bug: puede ser política intencional para no suprimir un mensaje indefinidamente.
- `BaseSerialAdapter` se inspeccionó; no se enumeraron puertos físicos ni se conectó hardware. Selección automática depende de OS/dispositivos y queda sin prueba real.
- Header raw, CRC BE y byte stuffing se verificaron por roundtrip y controles dirigidos. La etiqueta CCITT corresponde a poly=0x1021/init=FFFF; no extrapolar CRC a wire Companion ni radio oficial.
- No se extrajeron structs C++ para cambios de producción: los headers inspeccionados sólo sustentan campos existentes. No se certifica packing, padding ni layout para otro compilador/target.

#### Archivos inspeccionados

Scope principal: `src/protocol_types.py`, `src/sensor_decoder.py`, `src/serial/raw_framing.py`, `src/serial/serial_base.py`, `src/lqi_engine.py`, `src/deduplicator.py`, `docs/PROTOCOL_SPEC.md`.

Contexto de llamadas y aislamiento: partes de `src/shared_utils.py`, `src/contact_manager.py`, `src/rx_router.py`, `src/__init__.py`, `tests/conftest.py`, `pyproject.toml`; tests ejecutados arriba; inventario de nombres de regresiones oficiales/mutación/fuzz (no ejecutados como suites completas).

Referencias read-only: `reference/meshcore_py/src/meshcore/packets.py`, `parsing.py`, `lpp_json_encoder.py`; `reference/meshcore/src/helpers/sensors/LPPDataHelpers.h`, `reference/meshcore/src/helpers/AdvertDataHelpers.h`; fragmentos `reference/meshcore/examples/simple_repeater/MyMesh.h`, `MyMesh.cpp`, y búsquedas de campos airtime en fuentes oficiales.

Tools: los dos `SKILL.md` aplicados y sus scripts de inspección/validación. Artefactos nuevos limitados a `scratch/qa-results/audit-20261001/protocol/`.

### Contrato del adaptador SDK

Inspección dirigida de `src/serial/sdk_adapter.py` completo y contrato de `BaseSerialAdapter`; consulta de serializadores de mensajería del SDK y ramas Companion del firmware. No hardware conectado.

#### P2 — La capacidad anunciada de canales no se respeta al transmitir

Ubicación: `src/serial/sdk_adapter.py:985-987`; comparación con `_channel_capacity()` en `:1242`, y validación de `set_channel` en `:1255`. El rango de TX está fijo en 0..15, aunque GET/SET usan `max_channels` anunciado. Firmware `reference/meshcore/examples/companion_radio/MyMesh.cpp:1030` anuncia capacidad y `:1131` atiende envío por índice; SDK `reference/meshcore_py/src/meshcore/commands/messaging.py:167` serializa el índice como un byte.

Reproducción: `.venv/Scripts/python.exe scratch/qa-results/audit-20261001/protocol_sdk.py`. Mock conectado anuncia 40 canales: envío al índice 16 rechaza con `ValueError: ... rango 0..15` y cero llamadas SDK. Otro mock anuncia 2 canales: índice 12 se envía, devuelve SENT y llama SDK una vez. Esperado: validar con capacidad anunciada en ambos casos. Impacto: canales configurables por la misma interfaz no utilizables y peticiones fuera de capacidad llegan a firmware. El mock no demuestra que un equipo físico concreto tenga 40 canales; comprueba el contrato de capacidad anunciado que el propio código admite.

Evidencia: `protocol-sdk-result.json`. Las assertions del reproductor confirman el defecto y su exit 0 no significa que el comportamiento productivo sea correcto.

Suite existente dirigida: `tests/test_serial_official_compatibility.py`, `tests/test_serial_integration_regressions.py`, `tests/test_serial_adapter.py`: 43 aprobadas, 0 fallos, 0 skips, 2.82s. Comando/salida completa en `sdk-tests.json`. No se modificaron esas pruebas. La inspección no acredita radio física, BLE ni todos los eventos del SDK.

#### P3 — Alias broadcast 0xFFFF tratado como destinatario DM

Ubicación: `src/serial/sdk_adapter.py:992-996`. Se compara `target_clean.upper()` contra la cadena literal `"0xFFFF"`, cuyo `x` queda en minúscula. El alias incluido explícitamente en la lista no coincide y se resuelve como identidad privada inválida. Reproductor anterior, caso `broadcast_sentinel`: `send_message('hello', target='0xFFFF')` devuelve `ValueError: Destinatario no encontrado o clave pública inválida`; esperado envío de canal según esa misma lista. Impacto limitado a llamadores directos del adaptador que usan el alias; no se acredita aquí su exposición por todas las entradas REST/MQTT.

## Capa 3 — Dominio y persistencia

### Alcance y ejecución

Lectura completa de `src/contact_manager.py`, `src/shared_utils.py`, `src/target_resolver.py`, `src/packet_buffer.py`, `src/repeater_manager.py`; contraste selectivo de sus llamadores en RX, Web y administración. Skills leídas: domain-adr-keeper, python-patterns-typing, async-concurrency-engineering y bridge-test-runner; dominio contrastado con CONTEXT.md e índice docs/README.md. Sin correcciones en producción, tests mantenidos o documentación. Sin radio ni broker real. `.env` bloqueado mediante patch de `dotenv.load_dotenv`; JSON de reproducciones en TemporaryDirectory y fixtures de suite en ruta scratch única.

- `.venv/Scripts/python.exe scratch/qa-results/audit-20261001/domain/reproduce.py`: exit 0, once comportamientos defectuosos/condicionales reproducidos y un control positivo; assertions comprueban la observación defectuosa actual, no certifican el resultado deseado. Evidencia: reproduce-results.json.
- `.venv/Scripts/python.exe scratch/qa-results/audit-20261001/domain/run_targeted.py`: 32 passed, 1 warning, 2.38 s; Python 3.12.14, pytest 9.1.1. JUnit en targeted-junit.xml, salida íntegra en targeted-pytest.txt y comando en targeted-command.json. Cobertura parcial global src 23%; módulos asignados: consultar tabla de salida. No significa que esté cubierta toda la aplicación.
- Primer intento: 32 errores de setup por PermissionError en el directorio temporal preexistente `pytest-of-Ruby`, conservados en targeted-pytest-initial-permission-error.txt. La repetición cambió únicamente `--basetemp` a un scratch nuevo y ejecutó los mismos tests. Warning restante: cache de pytest sin permisos; no fallo del producto.
- Suites: contact_manager, node_registry_telemetry, registry_persistence_regressions, target_resolver_unit, packet_buffer, repeater_manager, repeater_manager_unit, shared_utils_unit.
- Cobertura dirigida de archivos asignados: contact_manager 80%, packet_buffer 88%, repeater_manager 20%, shared_utils 46%, target_resolver 80%. Esta cobertura de los tests mantenidos no incluye las reproducciones scratch ejecutadas aparte.
- mypy/ruff y navegador: no ejecutados por este subagente; la matriz global corresponde al principal/QA. Las reproducciones no acreditan interoperabilidad RF ni latencia de la instalación operativa.

### Hallazgos reproducidos con llamadores de producción

#### D01 [P2] Un TX hacia un nodo ausente actualiza su última recepción

Fuente: `src/contact_manager.py:1297-1311`, `src/contact_manager.py:1012-1019`. Llamador real: `src/web/controllers/tx_controller.py:108` registra un TX tras el envío. `record_packet` pasa al update el RSSI/SNR del contacto anterior aunque `is_rx=False`; `_build_updated_contact` interpreta cualquier RSSI/SNR no nulo como observación nueva y usa now.

Repro `tx_refreshes_last_seen`: contacto con last_seen=100 y RSSI=-80; reloj controlado now=1000; TX sin RSSI ni respuesta recibida. Esperado: tx_packets=1 y last_seen=100. Actual: tx_packets=1 y last_seen=1000. Impacto: presencia y limpieza de inactivos pueden presentar al destinatario como visto recientemente por actividad TX del bridge.

#### D02 [P2] Un advert completo no promociona la identidad previamente conocida por prefijo

Fuente: `src/contact_manager.py:1203-1219`; llamadores: `src/routers/advert_handler.py:100`, `src/rx_router.py:565`. `discover_node` encuentra la entrada por prefijo y llama `add_or_update(existing_key, ...)`, perdiendo la clave completa del advert antes de la consolidación que sí sabe ejecutar add_or_update.

Repro `discovery_does_not_upgrade_prefix`: registrar KEY[:12], luego descubrir KEY de 64 caracteres. Esperado: una entrada canónica bajo KEY completo. Actual: una entrada bajo KEY[:12]. Impacto: persistencia, UI y resoluciones vía registry mantienen una identidad truncada aunque ya recibieron la pública completa; operaciones que necesitan los 32 bytes dependen innecesariamente del libro SDK.

#### D03 [P2] Las búsquedas del registry seleccionan nombres duplicados aunque TargetResolver los rechaza

Fuente: `src/contact_manager.py:1133-1143`, `src/contact_manager.py:1339-1343`, `src/contact_manager.py:1356-1365`. Llamadores: `src/web/api_router.py:235` y `src/rx_router.py:429,443` usan find_by_name como fallback para adjudicar el remitente. `src/admin/traceroute_executor.py:301` también lo usa.

Repro `duplicate_name_first_match`: dos claves completas distintas con name='Same'. Esperado: no atribuir a una identidad una etiqueta ambigua. Actual: `find_by_name('Same')` y `get('Same')` retornan la segunda identidad; `TargetResolver.resolve('Same')` lanza Destinatario ambiguo correctamente. Impacto: atribución incorrecta de datos, contadores y labels cuando llega un evento con nombre sin clave inequívoca. No se afirma que TargetResolver pierda su guarda ni que la ruta DM SDK use siempre esta búsqueda.

#### D04 [P2] Un registro JSON malformado deja una carga parcial y omite consolidar LOCAL

Fuente: `src/contact_manager.py:1715-1739`; deserialización numérica `src/contact_manager.py:1662-1666`; llamador inicial `src/bridge_core.py:100`. El bucle muta el registry entrada a entrada; una excepción aborta antes del bloque local_pubkey y devuelve 0 sin rollback.

Repro `load_partial_failure_skips_local_identity`: JSON con local_pubkey=KEY, primero entrada KEY declarada CLIENT/no local y luego una entrada con rx_packets='not-an-int'. Esperado: rechazo atómico, o saltar el inválido y completar las guardas. Actual: retorno 0, un nodo residente, local_pubkey='', y la estación aparece en list_client_contacts. Impacto: arranque con estado parcial anunciado como cero importaciones y pérdida temporal de la invariante LOCAL hasta que la inicialización de hardware vuelva a establecer la clave. Requiere archivo semánticamente corrupto; no se afirma que el escritor JSON atómico cree por sí solo esa corrupción.

#### D05 [P2] Roundtrip de JSON pierde ruta, flags y máximo TX reportado

Fuente: `src/contact_manager.py:1630-1702`, con guardado `src/contact_manager.py:1600`. `_deserialize_node_contact` omite flags, last_advert, out_path, out_path_len, out_path_hash_mode y max_tx_power, que sí aparecen en el JSON guardado.

Repro `rf_fields_lost_during_load`: flags=19, last_advert=900, out_path='abcd', out_path_len=2, out_path_hash_mode='1', max_tx_power=14. Esperado: preservar seis campos tras save/load. Actual: los seis valen None. Impacto: rutas/advert y límite hardware perdidos al reiniciar; el DTO vuelve a calcular límites por board/default en vez de conservar el máximo reportado. Sin transmisión RF de prueba.

#### D06 [P2] La persistencia convierte el LQI almacenado en una valoración de presentación temporal

Fuente: `src/contact_manager.py:601-605`, `src/contact_manager.py:1435`, `src/contact_manager.py:1600`, `src/contact_manager.py:1698-1699`. Guardar usa `_list_nodes_snapshot` y `to_dict`; para nodos desconectados la presentación escribe score=0 y status=DISCONNECTED sobre el dato que se persistirá.

Repro `presentation_lqi_overwrites_stored_measurement`: nodo con LQI 75/GOOD y last_seen=1. Esperado: guardar el dato medido y derivar presencia al consultar. Actual tras save/load: LQI=0/DISCONNECTED. Impacto: tras reiniciar se pierde la medición anterior y cambia la semilla del suavizado EMA cuando vuelve la señal. La UI que muestre desconectado es apropiada; el defecto es reutilizar el DTO derivado como estado persistente.

#### D07 [P3] El payload de una captura cambia después de haberse registrado

Fuente: `src/packet_buffer.py:155`; ruta real `src/rx_router.py:299` pasa el dict al búfer y posteriormente lo entrega a handlers (`src/rx_router.py:314`). Entre las mutaciones posteriores existentes: `src/routers/telemetry_handler.py:72-76`, `src/routers/advert_handler.py:134` y normalización adicional en rx_router.

Repro `packet_capture_payload_mutates`: registrar dict con event_type original y nested sensor=1; modificar event_type y nested sensor=2 desde productor. Esperado: la captura histórica mantiene snapshot. Actual: get_packets devuelve el dict mutado; `packet.payload_dict is payload` es True. Impacto: exportación posterior puede diferir de la primera difusión `rf_packet` de esa misma captura. La repro comprueba API de captura; el código de handlers acredita que existen mutaciones reales después del registro. No se afirma que se modifiquen los raw_bytes, que se copian a bytes.

#### D08 [P2] Se puede evitar cooldown del mismo repetidor alternando clave y prefijo

Fuente: `src/repeater_manager.py:65-68,93-96`; llamadores concretos `src/admin/repeater_executor.py:197-201,440-445,652-662,910-934`. Los callers pasan la cadena original req.target_node al cooldown, aunque para resolver/admin ya se deriva una clave canónica; manager sólo strip/lower.

Repro `same_identity_prefix_bypasses_cooldown`: registrar comando/full query para KEY; consultar inmediatamente KEY y KEY[:12]. Esperado: ambos bloqueados por representar el mismo nodo. Actual: KEY bloqueado con 30 s restantes y KEY[:12] autorizado sin espera. Impacto: protección de airtime por destinatario no se comparte entre representaciones admitidas de la identidad. Prueba sin enviar comandos, complementada con lectura de rutas que pasan la representación original.

### Defectos de contrato/robustez reproducidos con exposición condicional

Estos tres casos están confirmados en las APIs de dominio; no se encontró una ruta ordinaria del bridge que cumpla todas sus precondiciones. Mantenerlos separados de incidencias demostradas de producción.

#### D09 [P3, condicional] record_packet pierde incrementos si dos hilos lo usan simultáneamente

Fuente: `src/contact_manager.py:1282-1290,1305`. Lookup/read/modify de contadores ocurre fuera de `_lock`; el lock de add_or_update no abarca esa transacción.

Repro `threaded_packet_increment_lost_conditional`: dos hilos detenidos por Barrier después de leer el estado inicial, ambos registran un RX; esperado rx_packets=2, actual=1. El owning loop serializa las llamadas habituales actuales; no se demuestra dos callbacks de radio reales entrando en paralelo. La API/threading.RLock no protege esta operación compuesta ante consumidores de hilo.

#### D10 [P3, condicional] is_local=False explícito puede anular la identidad canónica local

Fuente: `src/contact_manager.py:1105-1106`, `src/contact_manager.py:1454-1457`. `is_local` proporcionado gana sobre is_local_key; listar sólo excluye n.is_local/rol, y list_nodes no reescribe el flag por clave.

Repro `explicit_false_local_flag_overrides_guard_conditional`: fijar local_pubkey=KEY sin una entrada LOCAL existente y añadir KEY con role=CLIENT,is_local=False; esperado contactos=[], actual=[KEY]. Esto aísla el override de is_local del caso donde un rol LOCAL previo pudiera conservarse. No se halló ruta pública que permita enviar simultáneamente esa identidad exacta y ese override sin otra guarda; es incumplimiento defensivo de la invariante en la API de dominio.

#### D11 [P3, contrato] safe_device_query bloquea loop y no impone timeout para comandos síncronos

Fuente: `src/shared_utils.py:355-360` y su docstring que promete respuestas síncronas y corutinas con timeout determinista. Llama cmd directamente antes de decidir si es coroutine.

Repro `sync_query_timeout_not_enforced_contract`: stub sync duerme 50 ms, timeout=5 ms y ticker asyncio programado para 5 ms. Esperado: loop disponible y timeout aplicable. Actual: devuelve ok tras 51 ms; ticker no pudo correr antes del retorno. No se encontró un uso real actual de safe_device_query (rg sólo definición), y comandos del SDK oficial usan async. No calificar como bloqueo medido de producción; el contrato expuesto de helper es incorrecto.

### Controles positivos y límites

- Exclusión habitual de REPEATER/LOCAL y monotonía de last_seen ante updates explícitos anteriores: verificadas con assertion.
- Persistencia concurrente en sustitución atómica e incorporación de dirty/delete: las dos regresiones existentes pasan.
- TargetResolver rechaza el nombre ambiguo enumerable; no se encontró invención de claves desconocidas. Sus opciones de passthrough son contrato explícito.
- Buffer circular descarta lo más antiguo conforme a maxlen y suite; no se demuestra crecimiento ilimitado en cantidad de capturas.
- Se revisó memoria temporal de cooldowns pero no se reporta una violación de scheduler persistente sólo por existir diccionarios RAM: las acciones administrativas manuales y los timers automáticos requieren distinguir sus llamadores.
- La revisión completa de los archivos asignados y pruebas dirigidas no garantiza ausencia de otros defectos.

## Capa 4 — Runtime, administración e integraciones

### RX, concurrencia, cola TX y airtime

**Estado: inspección cerrada; no correcciones.** Archivos inspeccionados: `src/bridge_core.py`, `src/rx_router.py`, `src/routers/__init__.py`, `base.py`, `advert_handler.py`, `channel_handler.py`, `direct_handler.py`, `repeater_handler.py`, `system_handler.py`, `telemetry_handler.py`, `src/event_utils.py`, `src/serial/watchdog.py`, `src/rate_limiter.py`. Se leyeron auxiliares necesarios para contrastar callsites de submit y formato oficial del timestamp; no se amplió a otra capa.

Skills aplicadas: async-concurrency-engineering, python-patterns-typing, bridge-test-runner. Configuración aislada antes de importar aplicación: dotenv mock; entorno limpio; temporales bajo este directorio; web/TCP deshabilitados; logging persistente mock; adaptación serie y MQTT mock. Nunca connect, start bridge, broker, hardware ni .env operativo.

#### Comprobaciones ejecutadas

Reproducción: `.venv/Scripts/python.exe scratch/qa-results/audit-20261001/runtime/reproduce_runtime.py`. Exit 0; **8 observaciones confirmadas** con assertions que verifican manifestación, no corrección. Evidencia `reproduction-results.json`, `reproduction-output.txt`. El script elimina sus temporales al terminar.

Suite dirigida:

```powershell
$env:COVERAGE_FILE = (Join-Path (Get-Location) 'scratch/qa-results/audit-20261001/runtime/.coverage')
.venv/Scripts/python.exe -m pytest tests/test_rate_limiter_priority.py tests/test_tx_rate_limiter.py tests/test_airtime_persistence_regressions.py tests/test_serial_watchdog.py tests/test_rx_routers.py tests/test_bridge_core_comprehensive.py tests/test_core_lifecycle_regressions.py tests/test_concurrency_and_flapping.py -q -o cache_dir=scratch/qa-results/audit-20261001/runtime/pytest-cache --basetemp=scratch/qa-results/audit-20261001/runtime/pytest-temp --junitxml=scratch/qa-results/audit-20261001/runtime/junit.xml --cov-report=json:scratch/qa-results/audit-20261001/runtime/coverage.json
```

Resultado: **56 passed, 5.58s, cero skips**, Python 3.12.14, Windows. Cobertura dirigida de archivos principales: bridge_core 68.12%, rx_router 18.66%, rate_limiter 59.22%, watchdog 72.07%, event_utils 50.00%. Cobertura sobre TODO src de esa selección: 25.81%; no atribuir ese número a suite completa ni a cobertura exhaustiva de capa.

Mypy: `.venv/Scripts/python.exe -m mypy --strict src/bridge_core.py src/rx_router.py src/routers src/event_utils.py src/serial/watchdog.py src/rate_limiter.py --cache-dir scratch/qa-results/audit-20261001/runtime/mypy-cache` → exit 0, **no issues, 13 source files**.

Ruff: `.venv/Scripts/python.exe -m ruff check src/bridge_core.py src/rx_router.py src/routers src/event_utils.py src/serial/watchdog.py src/rate_limiter.py --output-format json --cache-dir scratch/qa-results/audit-20261001/runtime/ruff-cache` → exit 0, `[]`.

Navegador/Bandit no ejecutados en esta fase; no necesarios para la reproducción runtime. No se ejecutó toda la suite.

#### Hallazgos de flujo real con IO simulado

##### RUN-01 — P2: pérdida de mensajes legítimos por identidad de deduplicación incompleta

Fuente: `src/rx_router.py:615-628`, `src/routers/base.py:12-23`, handlers direct/channel al construir MeshMessageEvent. SDK oficial conserva `sender_timestamp` (`reference/meshcore_py/src/meshcore/reader.py:232,261`), pero la normalización de mensaje lo pierde y dedup usa sólo sender/channel/text/txt_type.

Reproducción RUN-DEDUP-IDENTITY: dos eventos CONTACT_MSG_RECV, mismo CLIENT y texto, sender_timestamp 1700000001 y 1700000002, procesados mediante `bridge.on_mesh_event`; sólo **1 DM publicado**. Son mensajes nuevos, no retransmisión del mismo paquete. Esperado: deduplicar usando identidad temporal/hash del paquete conservando mensajes nuevos. Impacto: confirmaciones repetidas, comandos de usuario y mensajes cortos desaparecen dentro de la ventana (default bridge 60s).

El mismo caso expone un defecto condicional de contador: si `bridge.dup_count` existe, se incrementa **2** por un duplicado porque `_ctx.bridge` y `_ctx.counters` apuntan al mismo bridge (`src/bridge_core.py:382-384`). El constructor actual no inicializa dup_count: no presentar este segundo síntoma como contador funcional predeterminado; existe al habilitar/añadir ese atributo.

##### RUN-02 — P2: límite de concurrencia RX no se aplica a eventos SDK

Fuente: `src/rx_router.py:217,310,1040`. El semáforo configurado MAX_RX_CONCURRENCY se usa sólo en `_dispatch_parsed_frame`; todos los handlers del SDK reciben tareas independientes sin adquirirlo. La creación de tareas no tiene una cola limitada.

Reproducción RUN-SDK-RX-LIMIT-BYPASS: MAX_RX_CONCURRENCY=2, 12 eventos CONTACT_MSG_RECV entregados por `bridge.on_mesh_event`; DirectMessageHandler real y seam de procesamiento lento controlado por Event: **12 llamadas simultáneas y 12 tareas propias pendientes**. Esperado: máximo configurado de 2 (y backpressure/cola acotada). Impacto: ráfagas de anuncios/mensajes o consumidor lento multiplican tareas y memoria. Es prueba de dispatch real, no prueba de consumo RAM en estación física. En raw el semáforo limita procesamiento, pero no la cantidad de tareas creadas en espera; no se midió ese segundo riesgo en esta fase.

##### RUN-03 — P2: STATS_PACKETS se intercepta y descarta como ACK

Fuente: `src/routers/repeater_handler.py:25,45,65-71`, `src/rx_router.py:219-226` (orden de handlers), `src/routers/system_handler.py:26`. El predicado `"ACK" in meta.ev_upper` coincide con STATS_PACKETS, evento oficial en `reference/meshcore_py/src/meshcore/events.py:48`.

Reproducción RUN-STATS-PACKETS-AS-ACK: `bridge.on_mesh_event` con type STATS_PACKETS y payload recv/sent produce **0 publicaciones MQTT**. El SystemHandler que reconoce ese evento nunca lo recibe; handler ACK retorna por is_local_sender o código ACK ausente. Esperado: estadísticas por handler correspondiente; matching preciso de ACK. Impacto: pérdida silenciosa de estadísticas/percepción de API incompleta.

##### RUN-04 — P2: texto común de CLIENT se desvía hacia respuestas administrativas

Fuente: `src/rx_router.py:107-109,127-150,671-713`. `_SYSTEM_EXACT_MATCHES` contiene ok, error, success, failed, ping, etc.; se aplica incluso si txt_type=0 y remitente CLIENT. El rol/canal de origen no restringe esa heurística.

Reproducción RUN-PLAIN-OK-RECLASSIFIED: evento CONTACT_MSG_RECV con CLIENT conocido, txt_type=0 y texto `ok` produce **repeater_response**, sin publicación de DM. Esperado: mensaje chat normal cuando firmware/rol indican chat; filtrado de respuestas administrativas con contexto. Impacto: mensajes cotidianos invisibles en conversación/n8n. Puede tratarse de política intencional histórica de filtros, pero la consecuencia actual está comprobada y no se presenta como protocolo oficial.

##### RUN-05 — P2: un mensaje SDK se cuenta dos veces en analítica del nodo

Fuente: `src/rx_router.py:521,592-601,717-725`. Normalización registra RX en `_update_node_registry_presence`; mensaje chat vuelve a llamar record_packet en `_handle_mesh_msg_common`.

Reproducción RUN-RX-DOUBLE-COUNT: un CONTACT_MSG_RECV de CLIENT → **rx_packets del nodo +2**, contador bridge RX +1. Esperado: un evento recibido cuenta una vez. Impacto: métricas por nodo y agregados difieren del tráfico real; deduplicación ocurre después del primer incremento, por lo que no protege esa primera contabilización. No duplica los hallazgos anteriores de almacenamiento/presencia TX de capa dominio.

##### RUN-06 — P2 condicional: callback de RX puede recrear actividad después del apagado

Fuente: `src/bridge_core.py:588-613,889-891`, `src/rx_router.py:227-310`. `on_mesh_event` y `handle_event` no consultan running/_is_stopped; stop captura una lista de tareas antes de detener el transporte al final.

Reproducción RUN-RX-AFTER-STOP: tras `await bridge.stop()`, entregar un callback SDK tardío por `bridge.on_mesh_event` produce **2 llamadas publish_safe** con running=false y _is_stopped=true; además modifica RX/registro. Esperado: rechazar callbacks tras cierre o cerrar ingress antes de capturar/cancelar tareas. Impacto: trabajo y tareas tardías fuera de la lista de apagado. La prueba acredita aceptación real en el callback, no que una versión concreta del driver necesariamente lo invoque después de desconectar. MQTT está mock, por lo que no demuestra publicación externa exitosa con cliente parado.

#### Defectos/limitaciones de API interna — no elevarlos a ingress REST/MQTT vigente

##### RUN-07 — P2 interna: payload dict aceptado por queue registra airtime de 32 bytes sin mirar texto

Fuente: `src/rate_limiter.py:652-660,719-723`; compatibilidad dict en `src/bridge_core.py:740-755`. Reproducción RUN-AIRTIME-DICT usa bridge real + worker y send_message mock: texto de 140 bytes se transmite, status sent, historial suma **411.6ms** (estimación de 32 bytes) frente a **1230.85ms** de estimación del mismo payload real (ratio .334). Esperado: estimar contenido transmitido, no tamaño fallback.

**Alcance imprescindible:** callsites normales actuales REST y MQTT pasan `payload=text` string (`src/web/controllers/tx_controller.py:71`, `src/mqtt_dispatcher.py:137`), por lo que esta manifestación de dict se alcanza por API interna/compatibilidad/tests, no está probada desde esos ingress. El comparador es el estimador del mismo software y payload sólo; no es airtime RF físico ni incluye overhead firmado/cifrado/routing.

##### RUN-08 — P3 interna: submit después de stop deja Future pendiente sin worker

Fuente: `src/rate_limiter.py:614-639,641-683`. RUN-SUBMIT-AFTER-STOP: stop; submit('after stop') → running=false, queue_depth=1, future_done=false. Esperado en cierre terminal: rechazo/cancelación o estado explícito; API permite también encolar ANTES de start, por lo que no basta rechazar todo `_running=false`.

No se reprodujo vía HTTP/MQTT durante cierre; registrar límite de contrato/lifecycle y riesgo de carrera, no un deadlock público confirmado. Un segundo stop cancela y limpia el fixture.

#### Hallazgos negativos y límites

- La suite dirigida confirma regresiones mantenidas de cancelación TX, flush final airtime, startup rollback, limpieza de tareas propias y threading de broadcast; los nuevos defectos están en rutas no cubiertas por esa selección.
- No aparece scheduler de beacon periódico en los archivos de esta capa. No se fabricó un fallo de persistencia de beacon/timer ni se ejecutaron pings físicos. Configuración/ejecutor que declara beacon queda para la capa administrativa.
- Airtime cutoff persiste flags/umbrales en JSON y tiene histéresis; el worker deliberadamente descarta sólo LOW en duty critical según dominio actual. No considerar ese contrato una garantía regulatoria ni inferir bug porque NORMAL/HIGH continúan.
- Watchdog se leyó y probó con mock; reconexión física/puerto real no certificada. No se simuló hardware USB ni se midió RF.
- No se repitieron fallos de unidades/GPS/LQI NaN, registry prefix/load/presencia TX/local-false ni cooldown alias entregados por capa anterior.
- Ningún fix, cambio de expectativas en tests mantenidos ni relajación de validadores. Sólo evidencia en scratch asignado.

### Administración local y remota

Auditoría del checkout local, 2026-10-01. Scope: `src/admin_handler.py` y todos los `src/admin/*.py`. Sin cambios de producción/tests/referencias; sin hardware, RF, broker real ni nuevos timers. Skills leídas/aplicadas: `async-concurrency-engineering`, `python-patterns-typing`, `meshcore-source-inspector` (leída en capa anterior, referencia oficial inspeccionada offline).

#### Resultados y evidencia

- **51 pytest passed in 16.54s** en tres módulos administrativos; XML en `pytest.xml`, salida en `pytest.txt`, cobertura JSON en `coverage.json`. El 33% global de `src` es cobertura dirigida con importaciones de dependencias, no suite completa.
- **16 desajustes reproducidos** en `reproduce.json`; script `reproduce.py` usa `AdminCommandHandler.handle` con SDK/registry/MQTT sintéticos y afirma el defecto observado. Su exit 0 acredita reproducibilidad, no corrección.
- Ruff: 0 hallazgos en siete archivos (`ruff.json`).
- Mypy strict con `--follow-imports=silent`: siete archivos sin errores (`mypy-fulltypes.txt`), dependencias resueltas y sus errores suprimidos; no acredita todo el proyecto. Primer intento `--follow-imports=skip` generó nueve `no-any-return` al borrar información de tipos importados (`mypy.txt`); **no se reportan como nueve defectos de producción**, porque al resolver tipos desaparecen.
- Config: `dotenv.load_dotenv` se parchea antes de importar `src/config`. Canales se reproduce con `mock_open` y `os.path.exists` mockeados; sólo PSK y contraseña sintéticas. La primera ejecución intentó redirigir canales mediante `CHANNELS_JSON_PATH`; reveló que la implementación ignora ese valor y falló el assertion. Se sustituyó por `mock_open` para aislar por completo el hardcode. No se guardaron ni se incluyeron contenidos operativos de canales en la evidencia.

Comandos principales desde la raíz:

```powershell
$env:COVERAGE_FILE=(Join-Path $PWD 'scratch/qa-results/audit-20261001/admin/.coverage')
.venv/Scripts/python.exe -m pytest tests/test_admin_executors.py tests/test_admin_official_compatibility.py tests/test_node_and_repeater_config.py -o cache_dir=scratch/qa-results/audit-20261001/admin/cache --basetemp=scratch/qa-results/audit-20261001/admin/temp --cov-report=json:scratch/qa-results/audit-20261001/admin/coverage.json --junitxml=scratch/qa-results/audit-20261001/admin/pytest.xml
.venv/Scripts/python.exe scratch/qa-results/audit-20261001/admin/reproduce.py
.venv/Scripts/python.exe -m ruff check src/admin_handler.py src/admin --no-cache --output-format json
.venv/Scripts/python.exe -m mypy --strict --follow-imports=silent --cache-dir=scratch/qa-results/audit-20261001/admin/mypy-fulltypes-cache src/admin_handler.py src/admin
```

#### ADM-01 — P2 — Configuración RF remota usa separadores incompatibles con CommonCLI

**Código:** `src/admin/repeater_executor.py:237` construye `set radio {freq} {bw} {sf} {cr}` y lo manda a `send_cmd`. **Fuente:** `reference/meshcore/src/helpers/CommonCLI.cpp:588-604` utiliza `mesh::Utils::parseTextParts(tmp, parts, 4)`; `reference/meshcore/src/Utils.h` fija `separator=','`, `Utils.cpp:219` separa exclusivamente por ese carácter.

**Reproducción:** handler recibe `remote_repeater_set_config` con frequency=916, bandwidth=125, sf=7, cr=5. SDK mock captura **`set radio 916 125 7 5`**. Bajo el separador exacto de fuente, expected **4 campos**, actual **1 campo**; CommonCLI toma bw/sf/cr=0 y responde `Error, invalid radio params`. La respuesta de bridge es `dispatched`, así que no miente sobre la confirmación remota, pero el comando enviado no puede aplicar esos parámetros en ese parser oficial.

**Alcance:** construcción/despacho real del handler probados; parser C++ contrastado por fuente y reproducción léxica de `split(',')`, no firmware compilado/hardware. Se observó también la misma construcción en `src/repeater_manager.py:284`, fuera del scope de edición; integrar como misma raíz, no duplicar.

**Mejora no aplicada:** serializar conforme al CLI de la referencia (`set radio 916,125,7,5`) y añadir regresión de comando exacto.

#### ADM-02 — P2 — `req_telemetry` rechaza la lista LPP que devuelve el SDK oficial

**Código:** `src/admin/repeater_executor.py:746` rama `req_telemetry`, acepta `data` sólo si es `dict`. **Fuente:** `reference/meshcore_py/src/meshcore/commands/binary.py:51-78` retorna `telem_event.payload["lpp"]`; `parsing.py:20` serializa `LppFrame` a lista y `reader.py:863` pone esa lista en el evento.

**Reproducción:** mock SDK devuelve `[{'channel':1,'type':'temperature','value':22.5}]`, forma oficial. Handler llama `req_telemetry_sync` una vez, pero devuelve **status=error, "Solicitud binaria sin respuesta válida del repetidor"**; esperado éxito y temperatura normalizada 22.5. La consulta en lote (`_execute_batch_telemetry_query`) sí envuelve la respuesta con `{"lpp": lpp_res}` antes del decoder: hay inconsistencia entre dos entrypoints.

**Prueba mantenida que deja el hueco:** `tests/test_admin_official_compatibility.py::test_repeater_registry_broadcast_completes_in_request_lifecycle` fabrica respuesta `dict` de `req_telemetry_sync` y pasa, aunque el contrato de la referencia retorna lista.

**Alcance:** handler/executor reales, SDK mock ajustado a la forma oficial; no RF real. Mejora: normalizar el resultado del SDK mediante el decoder y probar lista auténtica.

#### ADM-03 — P2 — Entradas inválidas se silencian y se informa configuración aplicada

**Código:** `src/admin/local_config_executor.py:514-619` sustituye valores RF no parseables por anteriores; `:684-730` captura errores PIN/tuning/path_hash y sigue; `set_local_config:421` termina con status=ok.

**Expected/actual:** frequency=`"broken"` → esperado error sin escritura; actual **ok** y `set_radio(915.0,250.0,11,5,0)` con todos esos valores marcados `applied`. PIN=`"bad-pin"`, path_hash_mode=3 y rx_delay=`"broken"` → esperado error; actual **ok/applied={}**. No son errores SDK rechazados (que las pruebas sí cubren); son validación de parámetros antes de escribir.

**Impacto:** usuario recibe confirmación aunque se ignoró su ajuste o se reescribió configuración previa. El frontend/API puede interpretar la operación como satisfactoria.

**Alcance:** entrypoint `handle` completo ejecutado con SDK sintético; las entradas `broken` no dependen de tolerancia del firmware. No se afirma aquí que valores numéricos fuera de rango sean aceptados por hardware; el firmware puede rechazarlos.

#### ADM-04 — P2 — Flags avanzadas convierten `"false"` en habilitado

**Código:** `src/admin/local_config_executor.py:660` usa `int(bool(val))` para `manual_add_contacts`, `multi_acks`, `adv_loc_policy` si no son números, distinto de `to_bool` usado para `repeat`.

**Reproducción:** `set_local_config` con `manual_add_contacts="false", multi_acks="false"` manda infos **[1,1]**, expected **[0,0]**; status=ok. `reference/meshcore_py/src/meshcore/commands/device.py:117` serializa estos valores directamente.

**Alcance:** handler y valores entregados al SDK confirmados. Sólo afecta entrada string; JSON boolean false funciona. Mejora: una única coerción booleana estricta o rechazo de strings según contrato API.

#### ADM-05 — P2 — Estados de error de reinicio y CLI remoto se presentan como éxito

**Código/primer caso:** `src/admin/cli_command_executor.py:253` llama `reboot` sin `require_success`. Mock `Event(EventType.ERROR, {'error_code':2})` produce handler **status=ok** y texto **"Comando de reinicio enviado"**. SDK oficial `device.py` anota retorno Event; que un reboot exitoso pueda cortar conexión no justifica convertir un ERROR explícito en ok.

**Código/segundo caso:** `src/admin/repeater_executor.py:945` asigna ok a cualquier texto no vacío. Respuesta realista **`Error, invalid radio params`** → **status=ok**, expected status=error. La cadena sigue visible, pero el envelope contradice el resultado remoto.

**Alcance:** handler ejecutado; ERROR SDK y respuesta remota sintéticos, no reinicio real. Mejora: distinguir transporte (`MSG_SENT`/dispatched), respuesta y resultado de aplicación; reconocer rechazo CLI sin asumir que toda respuesta no vacía confirma éxito.

#### ADM-06 — P2 — Un prefijo de waiter puede atribuir respuesta de otra identidad completa

**Código:** `src/admin_handler.py:207-249` y `:175-205` comparan prefijos incluso cuando existe identidad completa diferente. `WaiterRegistry` registra el mismo futuro bajo fullkey/8/4 (`src/admin/repeater_executor.py:633`).

**Reproducción:** se registra waiter para A=`11223344`+`aa`*28, con alias de 8 y 4 caracteres. Se notifica B=`11223344`+`bb`*28, identidad completa conocida diferente. Expected **no completar A**, actual **A.done=True** con texto **"B response"** y matched=True. Aunque el fullkey no coincide, el alias de 8 sí matchea.

**Impacto:** comandos concurrentes o respuestas retardadas en nodos con prefijos iguales pueden completar la espera equivocada y reportar aplicación/telemetría del nodo incorrecto. No requiere romper criptografía: es correlación después de la recepción.

**Alcance:** registro/notificación reales dentro del loop con registry sintético que conserva las claves completas. No se inyectó RX de SDK extremo a extremo; el comportamiento de método público está acreditado. Un resolver previo que rechace prefijos ambiguos no evita esta notificación por fullkey B. Mejora: identidad canónica completa primero; prefix match sólo si se prueba unicidad y tag corresponde.

#### ADM-07 — P1 — Cambiar contraseña por CLI refleja la contraseña completa en logs y MQTT

**Código:** `src/admin/repeater_executor.py:153` registra `req.action` completo; `_execute_unit_command_rf:942-946` devuelve/publíca `cmd_dispatched` y respuesta con cmd_text. Handler `src/admin_handler.py:311` incluye action original en res. El login binario sí enmascara password, pero los comandos de cambio de contraseña siguen este otro flujo.

**Reproducción:** `handle({'action':'password AUDIT_SYNTH_SECRET','target_node':REMOTE})` con confirmación sintética. Expected ausencia del valor sensible en salidas diagnósticas; actual **`AUDIT_SYNTH_SECRET` en logging.INFO y publish_safe(MQTT)**. Sólo se usó contraseña inventada. Puede ocurrir también con `set admin.password/guest.password` según constructor de payload.

**Impacto:** la nueva credencial administrativa queda disponible para lectores de logs/suscriptores de estado aunque no deberían recibirla. Severidad P1 por contraseña completa; explotación depende de permisos de lectura de logs/MQTT, auditados en otras capas.

**Mejora no aplicada:** redactar comandos sensibles antes de log/envelope/status, manteniendo el texto secreto sólo en la llamada SDK que lo requiere.

#### ADM-08 — P2 — CLI `channels` expone material de PSK y contradice cifrado público

**Código:** `src/admin/cli_command_executor.py:703` agrega `psk[:6]...psk[-4:]` y etiqueta canal Public como **"Sin cifrar"**. `execute:126` publica el result completo a MQTT.

**Reproducción:** mock_open entrega archivo sintético con PSK=`00112233445566778899aabbccddeeff`; salida contiene **`PSK: 001122...eeff`**, expected ninguna porción de clave. Se revelan 10 dígitos hex/40 bits; **no** se afirma exposición de clave completa ni posibilidad práctica de recuperar AES por ello.

**Discrepancia:** `docs/PROTOCOL_SPEC.md:243` declara canal Public cifrado con PSK pública conocida; el texto de CLI dice sin cifrar. Mejora: estado de confidencialidad sin reflejar material de clave, y texto coherente con fuente.

#### ADM-09 — P2 — CLI `channels` ignora ruta configurada y hace lectura bloqueante en el loop

**Código:** `src/admin/cli_command_executor.py:682-687` hardcodea `data/channels.json` y hace `open/json.load` síncrono desde handler async `execute`.

**Reproducción:** se configura `config.CHANNELS_JSON_PATH` a fixture temporal y se intercepta `open`. Expected ruta configurada, actual **`data/channels.json`**. El primer intento con sólo patch de config mostró el problema; la evidencia final usa mock_open para no consultar archivos operativos.

**Impacto:** instalaciones con directorio/ruta personalizada muestran otro inventario o fallback Public; UI/API y CLI divergen. La lectura es una llamada síncrona en el loop por inspección/callpath, pero **no se midió latencia de disco ni event-loop lag**: el bloqueo cuantitativo es un riesgo, no un benchmark confirmado.

**Mejora:** consumir el repositorio de canales existente o ruta configurada, con I/O delegado. No migrar datos ni crear otro almacén en esta auditoría.

#### ADM-10 — P2 — Diagnósticos falla con telemetría desconocida y declara conexión inexistente

**Código/sensores:** `src/admin/cli_command_executor.py:809` formatea `volt:.2f` cuando `get_local_config()` conserva `voltage=None`. Expected resumen de sensores sin lectura, actual **status=error** / **`unsupported format string passed to NoneType.__format__`** al llamar action=sensors.

**Código/estado:** `:305` asume `serial_connected=True`; `LocalConfigExecutor.get_local_config` no deriva ese campo del adaptador. `ctx.mc_provider=lambda:None` y ningún serial_adapter → action=status devuelve **"Transceptor LoRa: Operativo" y "Enlace Serial: Conectado"**, expected desconocido/desconectado. La conexión MQTT del fixture no determina la disponibilidad del radio.

**Alcance:** handler real, radio ausente y telemetría desconocida de forma válida. Mejora: tolerar None en sensores y basar estado serial en adaptador/conexión real.

#### Revisión de contratos, concurrencia y límites sin nuevos hallazgos confirmados

- `run_sdk_command` usa el gateway del adaptador cuando `adapter.mc is mc`, preservando serialización de comandos de SDK. Fallback directo depende de coroutine SDK; no se ejecutó hardware ni se acreditó exclusión mutua de toda una transacción de varias llamadas. Los comandos oficiales asíncronos son coroutines.
- `WaiterRegistry.expect_response` tiene limpieza en finally y cancela futuros no resueltos. `TracerouteExecutor` retiene tarea de espera, registra antes de send y cancela/espera en finally; inspección sin fuga confirmada. Correlación por tag del traceroute es distinta de la colisión de ADM-06.
- `TracerouteExecutor` separa hashes trace 1/2/4 bytes (`flags=0/1/2`) del modo de contacto 1/2/3 bytes; rechaza modo contacto 3 bytes no representable en send_trace. Esto coincide con documentación de la referencia `commands/messaging.py:222`.
- Autenticación remota: login binario exige LOGIN_SUCCESS, valida `is_admin=False` y prefijo; tests existentes cubren rechazo y ausencia de fallback a chat. No se afirma ausencia total de carreras entre login y respuesta, ni autenticidad de datos externos no SDK.
- No duplicar hallazgos anteriores de cooldown por alias/en memoria, capacidad de canales SDK 0..15 ni sentinel raw0xFFFF; remitidos por principal.
- `LocalConfigExecutor` docstring dice **"Modificación atómica"**, pero el método puede aplicar identidad y fallar luego en radio; retorna explícitamente `partial` si ya hubo cambios. **Mejora documental**, no nueva acusación de éxito falso: no hay rollback de hardware, y `partial` expresa ese estado.
- `_apply_timing_settings` cambia memoria (`advert_interval`, `telemetry_interval`, `hop_limit`) sin escribir estos ajustes a hardware ni persistirlos en esta clase; no se probó que un scheduler productivo consuma esas claves ni que aquí se rearme un timer. Documentar qué parámetros son metadatos del bridge y cuáles hardware antes de prometer cambio RF. No se modificaron límites/intervalos.
- Presentación de vecinos conserva heurísticas de prefijos de 6 caracteres y nombre local en `cli_command_executor.py:608-659`; puede excluir o rotular vecinos con identidades distintas. **Candidato inspeccionado, no reproducción propia en esta fase**; no sumar como defecto confirmado.
- No se acreditó RF aplicado, funcionamiento del modem, interoperabilidad sobre hardware ni corrección del middleware HTTP/MQTT, fuera de esta capa.

#### Archivos inspeccionados

Todos los siete archivos de administración: `src/admin_handler.py`, `src/admin/__init__.py`, `sdk_commands.py`, `local_config_executor.py`, `repeater_executor.py`, `traceroute_executor.py`, `cli_command_executor.py`.

Referencia/contexto read-only: métodos relevantes `reference/meshcore_py/src/meshcore/commands/device.py`, `messaging.py`, `binary.py`, `base.py`; LPP en `reader.py`, `parsing.py`; `reference/meshcore/src/helpers/CommonCLI.cpp`, `reference/meshcore/src/Utils.h`, `Utils.cpp`; fragmentos de `src/repeater_manager.py` sólo para procedencia/cross-reference; tres módulos tests ejecutados; docs protocolo para cifrado. Reproducciones adicionales limitadas al directorio `scratch/qa-results/audit-20261001/admin/`.

### MQTT, TCP Companion y workflow n8n

#### Alcance y resultados

Lectura completa: `src/mqtt_client.py`, `src/mqtt_dispatcher.py`, `src/tcp_companion_server.py`, `n8n_workflow_meshcore.json`, `docs/N8N_WORKFLOW_GUIDE.md`. Contraste selectivo con bridge_core y transporte raw SDK. Skills: async-concurrency-engineering, bridge-test-runner y security-code-auditor. `tools/ssh_mcp/server.py` recibió sólo lectura parcial; no se ejecutó SSH y no se presenta como auditado completamente. Sin cambios en producción, tests mantenidos ni docs.

- `reproduce.py`: exit 0; 15 checks Python reproducidos. Broker/administración simulados, TCP real sólo loopback efímero propio, adaptador SDK nunca conectado. Hilos/tareas/sockets de escenarios se liberan en finally.
- `n8n_actual.cjs`: ejecuta **el JavaScript leído del export actual**, con `$input`/`$getWorkflowStaticData` mínimos y reloj fijo. Ocho checks: siete comportamientos/contratos y control negativo de autorización sin nombre suplantado. Node v24.19.0. No se importa/activa un workflow externo ni se consulta Open-Meteo.
- `run_targeted.py`: **47 passed, 0 warnings, 4.06 s**, Python 3.12.14, pytest 9.1.1. Tests: mqtt_subsystem, mqtt_dispatcher_regressions, tcp_companion_server, tcp_official_compatibility, n8n_parser_matrix. Logs/JUnit/comando preservados en targeted-pytest.txt, targeted-junit.xml y targeted-command.json. Temp/cache/COVERAGE_FILE propios de esta capa; dotenv bloqueado antes de import.
- Cobertura parcial: mqtt_client 61%, mqtt_dispatcher 82%, tcp_companion_server 60%; global src 21%. JS real scratch se ejecutó aparte, no participa en esa cobertura Python. Mypy/ruff/navegador pertenecen a matriz global, no ejecutados aquí.
- Evidencia detallada: reproduce-results.json, n8n-results.json, n8n-stdout.txt y scripts de reproducción. Assertions verifican el comportamiento defectuoso observado, no son tests de aceptación de una solución.

#### Hallazgos confirmados en rutas actuales

##### MT01 [P2] La frontera MQTT entrante ignora el máximo de payload configurado

Fuente: `src/mqtt_client.py:246-258`, frente al límite outbound `src/mqtt_client.py:171-176`; conexión real callback->dispatcher en `src/bridge_core.py:898-902`. Se decodifica y programa el mensaje entero antes de cualquier control de longitud; tampoco se aplica el límite en dispatcher.

Repro `oversize_ingress_reaches_tx_queue`: JSON de 131102 B con `text='ok'` y padding, configuración máxima 131072 B. Esperado: rechazo/admisión acotada antes de decode/JSON/tasks conforme a frontera de entrada. Actual: se procesa y llama a submit una vez. Impacto demostrado: un publicador autorizado al tópico suscrito fuerza procesamiento de datos mayores al límite local de publicación. No se midió agotamiento de RAM, caída ni DoS; el límite existente sólo protege publicaciones salientes.

##### MT02 [P2] La admisión MQTT crea una tarea pendiente por mensaje sin backpressure

Fuente: `src/mqtt_dispatcher.py:39-49`. Las tareas se crean antes de clasificar/parsear/admitir el trabajo; la cola radio no acota solicitudes admin pendientes.

Repro `mqtt_pending_tasks_scale_without_admission_bound`: handle_admin controlado espera Event, 100 entradas dejan 100 tareas pendientes; otras 100 dejan 200. Esperado: admisión finita independiente del tiempo de servicio y cola TX. Actual: crecimiento proporcional a entradas pendientes. Impacto: ráfagas mientras hardware/admin responden lentamente acumulan tareas y strings en memoria. No se inventa un límite de producción ni se afirma que 200 tareas causen indisponibilidad; demuestra ausencia de backpressure en esta frontera. Todas se cancelan/esperan tras la medición.

##### MT03 [P2] Resultado TX de error pierde la causa en la publicación del dispatcher

Fuente: `src/mqtt_dispatcher.py:145-154`; productor del resultado con error/expected_ack: `src/bridge_core.py:838-856`.

Repro `tx_error_result_drops_details`: el future devuelve status=error y error='Receiver rejected message'. Esperado: conservar la causa retornada al consumidor MQTT. Actual: resumen publicado con status=error y request_id, sin error. El mapeo también omite expected_ack cuando está presente en el resultado. Impacto: errores tempranos de `_validate_tx_target` retornan sin publicación propia del core (`src/bridge_core.py:808-810`) y su único status vía dispatcher queda sin explicación; en TX que sí alcanza publicación core puede aparecer luego un segundo resumen menos completo para el mismo request_id. No se afirma entrega RF por publicar sent.

##### MT04 [P2] Rechazos TCP y errores de autenticación retienen tareas completadas

Fuente: `src/tcp_companion_server.py:204-211,218-271`; el finally que descarta tarea está sólo en `src/tcp_companion_server.py:355-357`, después de admisión/autenticación.

Repro real `rejected_tcp_clients_retain_tasks`: MAX_COMPANION_CLIENTS=0, cinco conexiones rechazadas secuencialmente. Esperado: active_clients=0 y tareas almacenadas=0. Actual: active_clients=0, cinco tareas done conservadas. Esta misma estructura afecta los retornos por allowlist/token/timeout, aunque el check concreto ejecutó rechazo por capacidad.

Repro adicional `oversize_auth_line_escapes_cleanup`: token habilitado y línea de autenticación de 70000 B; readline lanza ValueError fuera de cleanup. Actual: tarea con ValueError retenida; **el socket sí termina cerrado por asyncio** (`reader.read` devuelve b''). Impacto probado: referencias a tasks/errores se acumulan hasta stop; no afirmar fuga de sockets abiertos. El primer borrador de la repro esperaba socket abierto; esa hipótesis quedó descartada y la assertion final comprueba sólo ValueError/tarea retenida.

##### MT05 [P2] Autenticaciones concurrentes sobrepasan MAX_COMPANION_CLIENTS

Fuente: `src/tcp_companion_server.py:209-211,237,280`. Capacidad se comprueba antes del await de autenticación, pero conexiones pendientes no se reservan ni se revalida el cupo al agregarlas a active_clients.

Repro real `concurrent_authentication_bypasses_connection_cap`: máximo 1; abrir dos conexiones, ambas reciben AUTH_REQUIRED antes de responder; enviar token válido a las dos. Esperado: como máximo una admitida. Actual: active_clients=2. Impacto: el límite configurado no se respeta con sesiones autenticándose en paralelo; pendientes también consumen tareas/streams antes de contar como activos. No se usó el token del operador, sólo 'audit-token' en entorno patch.

##### MT06 [P2] El reporte meteorológico n8n no cabe en el protocolo de envío actual

Fuente: `n8n_workflow_meshcore.json`, nodo ID 14 `Formatear Reporte Estado y Clima` (nombre en línea 66); contrato SDK en `src/serial/sdk_adapter.py:977-980`.

Repro JS actual + adapter Python: clima 28.5 °C, sensación 32 °C, humedad 72%, viento 12.5, sin lluvia. Salida real=233 B UTF-8. Esperado: payload aceptable por el bridge. Actual: `send_message` rechaza `233 > 160` antes de llamar send_chan_msg. Impacto: el ejemplo de reporte periódico no transmite con el bridge actual. No es un fallo del guard MTU SDK; es incompatibilidad de la salida del workflow. La guía ya advierte que no garantiza máximo en bytes, pero no elimina el fallo reproducido.

##### MT07 [P2] /help n8n falla en canal cuando la estación tiene nombre

Fuente: export nodo ID 5 `Procesar Canal Público` (nombre línea 172), branch `/help`; SDK `src/serial/sdk_adapter.py:1038-1045` incluye prefijo de nombre en el presupuesto oficial.

Salida real de `/help`=158 B. Estación stub con nombre Audit añade 5+2 B; presupuesto de texto=153. Actual: `Texto de canal excede límite oficial con prefijo (158 > 153 bytes)`, sin transmisión. Esperado: respuesta que respete el tamaño completo del mensaje de canal. Impacto: la ayuda anunciada no llega desde estaciones con nombre no vacío. Una estación con nombre vacío usa prefijo de 2 B y puede admitir exactamente esos 158 B; no se afirma falla universal sin esa condición.

##### MT08 [P1] Un nombre visible suplanta la whitelist administrativa del export

Fuente: export nodo ID 7 `Procesar DMs y Admin` (nombre línea 198), expresiones `ADMIN_WHITELIST.includes(senderId) || ADMIN_WHITELIST.includes(senderName)` y branch reboot. Guía `docs/N8N_WORKFLOW_GUIDE.md`, sección 4, reconoce whitelist de nombres/IDs de ejemplo.

Repro JavaScript actual `name_spoofs_admin_whitelist`: clave completa desconocida ('cd' repetido 32), role CLIENT, sender_name='admin_master', texto='/admin reboot'. Esperado: esa clave no autorizada no produce comando admin. Actual: se genera payload `topic=meshcore/admin/cmd,action=reboot`. Control negativo con sender_name='Unknown' no genera admin.

Impacto: si se activa el export con whitelist de nombres, cualquier cliente que adopte un nombre permitido consigue que n8n publique comandos administrativos como el propio cliente MQTT del workflow. Se probó generación del comando, nunca se ejecutó reboot. Es la configuración/política presente en el ejemplo; sustituir la whitelist por claves completas confiables y eliminar nombres cambia la precondición. No se afirma intrusión en una instancia activa desconocida.

##### MT09 [P3] /time muestra hora local del proceso y la etiqueta UTC

Fuente: export nodo ID 5, expresión `now.toTimeString().split(' ')[0] + ' UTC'`. La guía ya reconoce esta discrepancia.

Repro JS actual `local_clock_labeled_utc`: fecha fija 2026-10-01T17:00:00Z, proceso TZ America/New_York. Esperado: 17:00:00 UTC. Actual: 13:00:00 UTC. Impacto: horario incorrectamente rotulado en despliegues n8n cuyo proceso no esté en UTC. El formatter meteorológico usa explícitamente America/New_York y no comparte este fallo.

#### Defectos confirmados con condiciones de contrato/configuración

##### MT10 [P2, condicional] Normalizador n8n clasifica por nombre/telemetría e ignora tipo de advert al faltar role

Fuente: export nodo ID 2 `Deduplicar y Validar` (nombre línea 93), branch `if (!role)` con sender_name.includes('REP') y temperatura/humedad. Contradice la clasificación canónica por FirmwareAdvertType exigida por AGENTS/CONTEXT; la guía describe explícitamente la heurística presente.

Repros reales JS: sin role, adv_type=1 y sender_name='REPorte personal' se convierte REPEATER; sin role, adv_type=2 y name='Tower' se convierte CLIENT y el handler DM genera eco. Esperado: identidad derivada de la metadata oficial si está disponible, sin evidencia de nombre como rol. Impacto: falso bloqueo de cliente o creación indebida de solicitud de chat en workflow ante metadata incompleta. El bridge SDK aún tiene guardas independientes al transmitir; no se afirma envío real al repetidor, ni que la ruta ordinaria siempre omita role.

##### MT11 [P3, condicional] Cliente MQTTConfig con prefijo propio mezcla tópicos globales

Fuente: `src/mqtt_client.py:218`; `src/mqtt_dispatcher.py:72-73,154,166,177,180,209`.

Repros con topic_prefix='audit_custom' y config.TOPIC_PREFIX='meshcore': TX/admin de entrada usan audit_custom; sus estados salen por meshcore/tx/status y meshcore/admin/status. Suscripción y procesamiento de repetidores siguen meshcore/admin/repeater; un comando audit_custom/admin/repeater/abcd/cmd se ignora y meshcore/admin/repeater/abcd/cmd se ejecuta en el mock admin.

Esperado: namespace de la instancia consistente. Impacto: consumidores de instancia aislada pierden respuestas/admin remoto y la instancia sigue un namespace ajeno. **El constructor ordinario MeshCoreBridge pasa el mismo config.TOPIC_PREFIX al MQTTConfig (`src/bridge_core.py:130`)**, por lo que esta discrepancia necesita una instancia reconfigurada de forma independiente. No se afirma fuga entre namespaces del arranque estándar.

##### MT12 [P3, condicional] Dos clientes creados en el mismo segundo comparten client_id

Fuente: `src/mqtt_client.py:92,96`. Repro congela reloj y construye dos instancias con prefijos distintos: ambas entregan a Paho client_id='meshcore_bridge_1700000000'. Esperado: identidades independientes. Actual: identidad igual. Impacto/riesgo: colisión cuando dos procesos/instancias arrancan en el mismo segundo contra el mismo broker. Se confirmó la generación de identificadores duplicados con mock de constructor; no se ejecutó broker ni se midió bucle de reconexión/desconexión. No atribuir un fallo de broker probado a este escenario.

##### MT13 [P3, condicional] Timeout de cierre MQTT no termina el worker de stop si el hilo Paho no responde

Fuente: `src/mqtt_client.py:151-152`, `src/bridge_core.py:641-645`; implementación instalada Paho Client.loop_stop usa `_thread.join()` sin timeout después del join(timeout=1) del wrapper.

Repro `paho_stop_outlives_bridge_shutdown_timeout_conditional`: Paho real sin red, `_thread` reemplazado por hilo local esperando Event para representar hilo no responsivo; ejecutar stop vía to_thread y wait_for=1.5 como bridge. Actual después de 1508 ms: wrapper_timed_out=True, stop_thread_finished=False, network_thread_alive=True; **ticker asyncio completó**, no bloqueo del event loop. Se libera Event y se espera toda limpieza.

Impacto condicionado: cancelar el await del shutdown no cancela los joins del executor; ese worker puede permanecer vivo y retrasar el cierre final del executor/proceso si el hilo MQTT no termina. No se demostró que el hilo normal de Paho se atasque con broker real; registrar como límite del apagado, no caída operacional confirmada.

#### Brecha de verificación

##### MT14 [P2, QA] Los tests n8n simulan una implementación Python diferente del export

Fuente: `tests/test_n8n_parser_matrix.py:10-103`. `N8nSimulator` contiene lógica propia/whitelist reducida y no carga n8n_workflow_meshcore.json.

Repro `python_test_simulator_differs_from_actual_workflow`: mismo input `data` como objeto con sender completo y text Hola. JS actual lo desempaqueta y conserva la clave; simulador Python devuelve sender='unknown'. El simulador tampoco reproduce la heurística REP del export, ni ejecuta sus Code nodes. Esperado: pruebas del workflow detectan el comportamiento del código que se entrega. Actual: los ocho tests n8n pasan para su simulador aunque exista la diferencia comprobada. Impacto: el resultado de esa suite no certifica el export ni su seguridad/MTU; es un defecto de verificación separado de bugs de workflow.

#### Controles y límites

- Tests existentes confirman no difusión de respuestas SDK internas, propiedad de respuesta, exclusión raw local/repeater, arbitraje SDK/raw, recuperación framing, rechazo sobredimensionado y ausencia de respuesta sintética duplicada ante ERROR.
- Protocolos TCP sin request_id tienen limitación inherente para respuesta tardía tras timeout; el adaptador ya la documenta. No se reporta por inspección como nuevo fallo sin reproducción de atribución errónea.
- Los clientes loopback, hilos, tareas y mocks se cierran; ninguna prueba consulta la estación operativa, broker productivo, SSH, API de clima o instancia n8n activa.
- No se añadió ni cambió timer, umbral, reintento o transmisión RF; se reprodujo sólo el comportamiento vigente con fixtures controlados.
- La revisión y suite parcial no garantizan ausencia de otros errores ni certifican interoperabilidad completa.

### Observabilidad y adaptador virtual

Lectura de `src/health_reporter.py`, `src/preflight.py`, `src/diagnostics.py` y `src/virtual_mesh_adapter.py`, y callsites de diagnósticos. Reproducción: `.venv/Scripts/python.exe scratch/qa-results/audit-20261001/observability_reproduce.py`; exit 0, assertions de presencia del defecto. Evidencia `observability-results.json`. No archivos operativos, sockets externos, radio ni broker; preflight y eco sustituidos por stubs sólo en el script de reproducción.

#### OBS-01 [P2] Exportar diagnósticos bloquea el event loop

`src/web/api_router.py:428,437` invoca directamente `DiagnosticManager.generate_markdown_report/generate_full_diagnostic_bundle`; `src/web/controllers/logs_controller.py:118` repite el patrón. `src/diagnostics.py:255-266` llama al preflight síncrono, que realiza conexiones TCP con timeout en `src/preflight.py:29-32,73-74`. Ruta real `_dispatch_system` con checker sintético que tarda 50 ms: respuesta 200 tras 50 ms y ticker asyncio de 5 ms aún sin ejecutarse. Esperado: delegar I/O fuera del loop, como hace `run_all_async`; no mantener bloqueadas las demás tareas al exportar. La medición acredita el bloqueo por la cadena real con stub, no tiempo de red de una estación operativa.

#### OBS-02 [P2] Reporte Markdown marca como fallo los checks aprobados

`src/diagnostics.py:335-336` espera `chk.status == PASS/WARN`, mientras `PreflightChecker.run_all` entrega `passed` e `is_critical`. Check sintético `passed=True` termina como fila `❌ None`. Esperado: aprobado visible como tal, y warnings derivados de criticidad. Impacto: exportación engañosa para diagnóstico/soporte, aunque su JSON sí conserva el resultado correcto.

#### OBS-03 [P3] El bundle preflight no utiliza la configuración vigente del servidor TCP

`src/diagnostics.py:255-266` sólo pasa broker, puerto MQTT y serie. Omite `TCP_SERVER_PORT`, `TCP_SERVER_ENABLED`, `TCP_SERVER_HOST`, que `run_all` sustituye por 5000/True/0.0.0.0. El reproductor registra kwargs y confirma las tres omisiones. El código de `SystemController.run_preflight` sí entrega la configuración, por lo que las dos formas de diagnóstico difieren. Esperado: comprobar el servidor configurado. No se abrieron sockets para probar un puerto ocupado; el impacto sobre otro listener se deriva del callsite y defaults inspeccionados.

#### OBS-04 [P3] Salud publica la selección configurada en lugar del puerto resuelto

`src/health_reporter.py:63` utiliza `config.SERIAL_PORT`, no `ctx.serial_adapter.port`. Con configuración AUTO y adapter `VIRTUAL_REAL_PORT`, el payload devuelve AUTO. Esperado: identificación efectiva del transporte; impacto limitado a observabilidad. DiagnosticManager sí consulta el puerto del adaptador.

#### VRT-01 [P2, simulación] add_contact ignora campos del SDK y convierte repetidor en CLIENT

`src/virtual_mesh_adapter.py:462-473` sólo consulta `name` y `role`; ignora `adv_name` y `type`. Añadir `{public_key:cd*32,adv_name:'Official repeater',type:2}` crea `Node_cdcdcd`, rol CLIENT y acepta chat a esa clave. Esperado: conservar identidad/rol canónico, en consonancia con el adaptador SDK y el contrato común. Resultado confirmado sin simular RF físico. La exposición comprobada es la API del adaptador virtual; no implica que el driver físico omita sus propias guardas.

#### VRT-02 [P2, simulación] DM Companion por prefijo evade guarda de repetidor con clave completa

`src/virtual_mesh_adapter.py:561-570` compara sólo nombre/alias/clave exacta; `:730-732` pasa el prefijo oficial de seis bytes. Al registrar un nodo con clave completa y rol REPEATER, un raw DM a su prefijo se considera un nuevo cliente desconocido y devuelve opcode 6 (MSG_SENT). Esperado: resolver el prefijo único y rechazar chat al repetidor, como sucede con la clave exacta. Acreditado por frame de respuesta `06…`, callback local; sin transmisión real.

#### VRT-M01 [P3, mejora de fidelidad] Simulador acepta texto y canales que el adaptador SDK rechaza

`src/virtual_mesh_adapter.py:527-607`: 1000 caracteres en canal 250 devuelve ok, sin validación MTU/capacidad. Esperado para una prueba de paridad: mismo rechazo que firmware/SDK cuando procede. El simulador es explícitamente un subconjunto; clasificar como brecha de QA/fidelidad, no como fallo de radio real. Falta una batería compartida de contratos entre adaptadores.

#### Límites adicionales

Preflight valida que una conexión TCP abre; no acredita sesión MQTT ni handshake Companion. `check_serial_port` acepta un nombre COM por formato y no prueba que exista: mejora de precisión del diagnóstico, sin acceso a hardware real. No se midió salud/rendimiento de producción ni se auditó cada interleaving del simulador.

Suite existente dirigida de diagnósticos, exportación, salud/preflight y simulación: **31 aprobadas en 5,41 s**, sin fallos ni skips. Comando y salida completa en `observability-tests.json`. No se modificó la suite.

## Capa 5 — HTTP, WebSocket, REST y configuración

### Autenticación y exposición de diagnósticos

Inspección completa de `src/web/http_server.py` y `security_inspector.py`, contraste de rutas con `api_router.py` y `logs_controller.py`. Skill `security-code-auditor`. Reproducción: `.venv/Scripts/python.exe scratch/qa-results/audit-20261001/http/auth_reproduce.py`, exit 0; ocho peticiones reales a servidor propio en 127.0.0.1, puerto efímero. Mapas, canales y estáticos apuntan a directorio temporal; dotenv bloqueado, clave/PSK/log inventados, cierre en finally. No hubo consultas a una estación operativa.

#### HTTP-01 [P1] La normalización de ruta se aplica después de autenticar y permite exportar PSK sin clave

Fuente: `src/web/http_server.py:575-600`, `src/web/api_router.py:339`. Auth compara rutas sensibles exactas antes de que el router elimine barras finales. Con BRIDGE_API_KEY configurada, GET `/api/channels/export?index=1` sin clave produce 401; GET `/api/channels/export/?index=1` sin clave produce 200 y devuelve la PSK sintética completa. La misma discordancia permite `/api/logs/raw/` y `/api/logs/download/`, que devuelven logs, mientras `/api/logs/raw` produce 401. `/api/diagnostics/export/` también se despacha sin autenticar; en este fixture no hay DiagnosticManager, por lo que no se afirma extracción real de su bundle.

Impacto: la protección existente de exportación de claves y logs se omite usando una ruta equivalente admitida por el router, incluso en modo con clave configurada. No se extrajo ninguna credencial operativa. Mejora no aplicada: normalizar ruta/alias una sola vez antes de decidir autorización y despachar; probar variantes equivalentes y GET sensibles.

#### HTTP-02 [P2] La vista de logs de sistema carece de la protección aplicada a su descarga

Fuente: `src/web/http_server.py:584-600`, `src/web/controllers/logs_controller.py:67-116`. GET `/api/system/logs` devuelve 200 y el mensaje sintético del buffer sin clave, aun con BRIDGE_API_KEY configurada. Las dos rutas de reportes markdown tampoco pertenecen a sensitive_read_paths; el fixture confirma 200, pero no contiene diagnóstico sensible real. No es el defecto de slash: la ruta canónica ya permite lectura.

Impacto: lectores con acceso a la WebUI pueden obtener mensajes de logs aunque no tengan la clave exigida para descarga. En combinación con ADM-07, un comando que registre una contraseña puede reflejarla por esta vista; la auditoría confirmó cada tramo con datos sintéticos, sin ejecutar esa cadena contra una instalación. Si el producto pretende logs públicos debe explicitar esa política y garantizar redacción antes de almacenar; actualmente el mismo contenido recibe tratamientos distintos.

#### Mejoras y límites de esta inspección

- Origin permite cualquier origen de red privada o loopback además de BRIDGE_ALLOWED_ORIGINS (`http_server.py:629-648`), por diseño del código. La variable no constituye una allowlist estricta. La API key sigue exigida en WS y mutaciones; no se afirma ejecución no autorizada por CORS. Mejorar documentación/política antes de endurecer compatibilidad.
- El inspector se invoca con path sin query y body_dict=None (`http_server.py:353-359`), y no se repite tras leer JSON. Sus reglas de query/body existen en el helper, pero no están conectadas aquí. Esto es una discrepancia de cobertura de la heurística, no prueba de inyección ejecutable ni sustituto de validación de esquema/escape de salidas.
- Se comprobó por lectura la resolución canónica de estáticos, máximo HTTP de 1 MB, rechazo Transfer-Encoding, autenticación WS, máscara y controles básicos de frames. Las pruebas de mapas/estáticos/compatibilidad WS se registran por separado. No se realizó prueba de carga, exposición a Internet ni auditoría criptográfica.

### Controladores REST

Fecha: 2026-10-01/02 local; checkout compartido. Se inspeccionaron íntegramente los **11 archivos reales** de `src/web/controllers/` (la asignación mencionaba 12): `__init__.py`, `base.py`, `channels_controller.py`, `contacts_controller.py`, `config_controller.py`, `repeater_controller.py`, `tx_controller.py`, `system_controller.py`, `packets_controller.py`, `nodes_controller.py`, `logs_controller.py`.

Se aplicaron las skills `api-design-testing`, `contract-openapi-sync` y `security-code-auditor`. Las reglas RFC/OpenAPI de las skills se trataron como recomendaciones; no se supuso una especificación OpenAPI publicada. No se ejecutaron helpers históricos con mocks antiguos. Lecturas auxiliares acotadas: despacho `src/web/api_router.py`, normalización de contactos `src/serial/sdk_adapter.py`, persistencia `src/contact_manager.py`, `src/rate_limiter.py`, adaptador virtual, opcodes/tipos `src/protocol_types.py`, serializador oficial `reference/meshcore_py/src/meshcore/commands/contact.py`. Referencias sólo lectura. HTTP/auth/router y frontend son otras asignaciones.

#### Evidencia y aislamiento

- `reproduce.py`: 24 escenarios por **WebAPIRouter real**, registros `NodeRegistry` reales, una instancia virtual **sin connect()**, adaptador SDK real con frontera `run_sdk_command` sintética y `AirtimeTracker` real. 20 escenarios observan discrepancias y 4 son controles positivos; no son 20 defectos independientes.
- `reproduction.json`: petición, expected/actual, HTTP, respuesta, argumentos enviados y estado observable; `reproduction.txt`: tracebacks esperados y warnings de IO sintético.
- `pytest.xml`/`pytest.txt`: **69 passed, 1 skipped**, 70 casos, 12.07s. Skip: Windows no permite symlink en fixture map; no se elevó privilegio sólo para convertir ese skip en pass.
- `ruff.json`: `[]`, salida 0, los 11 archivos limpios.
- `mypy.txt`: salida 0, `--strict --follow-imports=silent`, 11 archivos. Aviso de sección `serial.*` no usada. No certifica implementaciones externas silenciadas.
- `.env` no leído: patch de `dotenv.load_dotenv` antes de imports; JSON/logs/env y MapTileService en temporales debajo de esta carpeta. Cierre de todos los mapas en finally. No HTTP listeners, hardware, RF, broker ni datos operativos. Credenciales/PSK/claves de prueba son sintéticas.

Comandos ejecutados desde la raíz:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_rest_controllers.py tests/test_channels_and_contacts_controllers.py tests/test_node_and_repeater_config.py tests/test_web_official_compatibility.py -q -o cache_dir=scratch/qa-results/audit-20261001/controllers/cache --basetemp=scratch/qa-results/audit-20261001/controllers/temp --junitxml=scratch/qa-results/audit-20261001/controllers/pytest.xml
.venv/Scripts/python.exe scratch/qa-results/audit-20261001/controllers/reproduce.py
.venv/Scripts/python.exe -m ruff check src/web/controllers --output-format json
.venv/Scripts/python.exe -m mypy src/web/controllers --strict --follow-imports=silent --cache-dir scratch/qa-results/audit-20261001/controllers/mypycache
```

Las salidas se redirigieron a los archivos indicados. El primer pytest heredó `--cov` del proyecto y escribió `.coverage` compartido en raíz; se comunicó al principal. Las cifras de cobertura siguientes provienen del texto de **esa ejecución dirigida**, no de inferir cobertura del driver ni de una suite completa: base85%, channels63%, config33%, contacts48%, logs12%, nodes55%, packets82%, repeater50%, system61%, tx71%, package100%; total de proyecto34% porque muchas capas no formaban parte de la selección. No se añadieron tests mantenidos ni cambios productivos.

#### Hallazgos reproducidos

##### CTRL-01 — P2: eliminación virtual se aplica y luego devuelve 503 dejando caché divergente

Fuentes: `base.py:66-76`; `channels_controller.py:334-340`; `virtual_mesh_adapter.py:445-448`.

`DELETE /api/channels {index:1}` invoca `VirtualMeshAdapter.delete_channel`, elimina el canal y recibe `{status:DELETED}`. `command_failure` sólo acepta OK/SUCCESS/SENT y rechaza el resultado válido como `command_unconfirmed`. **Actual: HTTP503, radio_has_1=false, cache_has_1=true**. Esperado204 con ambos eliminados. Repro `virtual_delete` usa el adaptador del producto sin radio real. El status CLEARED también queda fuera del conjunto aceptado por lectura, pero este escenario concreto sólo acredita DELETED. No confundir con un rechazo oficial Companion, que sí debe impedir commit local.

##### CTRL-02 — P2: sincronizaciones fallidas se anuncian como exitosas

Fuentes: `channels_controller.py:124-161`; `contacts_controller.py:99-131`.

`get_channels` y `sync_all_contacts` arrojan `ConnectionError("synthetic offline")`; ambos endpoints POST sync devuelven **200/statusok** y el snapshot anterior/0 importados. Esperado fallo503 o respuesta que declare explícitamente que no hubo sincronización. Repros `channels_sync_offline`, `contacts_sync_offline`. Las excepciones están atrapadas y ocultas por los propios controllers (DEBUG/WARNING). También faltan adapter/método sin señalar indisponibilidad por lectura. No se atribuye fallo del hardware a esta capa: el problema es su presentación API.

##### CTRL-03 — P2: importación por lote valida tarde, muta parcialmente y pierde persistencia/ack

Fuentes: `contacts_controller.py:347-372, 391-407`.

POST `/api/contacts/import` con primer contacto válido y segundo public_key=`bad`: el primero ya fue enviado al adapter y añadido al registro cuando la validación del segundo retorna422. **Actual: radio_calls1, registry_has_first=true, disk_unchanged=true, respuesta sólo error invalid_public_key**. Esperado validar el lote antes de efectos, o persistir/acknowledge el prefijo exitoso con semántica parcial documentada. Repro `batch_invalid_after_valid` parte de archivo real de NodeRegistry guardado. La rama de fallo serial intenta guardar el prefijo; la rama de fallo de validación no lo hace. Su comentario sobre "acknowledged" tampoco se corresponde con la respuesta de error serial genérica, observado por lectura y no contado como otra reproducción.

##### CTRL-04 — P2: no se propaga el fallo real de persistencia de contactos

Fuentes: `contacts_controller.py:47-54, 471-479`; `contact_manager.py:1594-1627`.

El path de fixture apunta debajo de un archivo regular, por lo que `NodeRegistry.save_to_file` recibe WinError183 y devuelve False. `_save_registry_async` descarta ese bool. **POST /api/contacts devuelve201/statusok, registry_has_key=true, disk_exists=false**. Esperado reconocer el fallo de guardado, no anunciar una creación durable. Repro `contact_save_fails`; IO real, no sólo mock de retorno. Pérdida al reiniciar/caché vs disco es el riesgo; no se reinició el servicio productivo. La misma fachada se usa en import/delete por lectura.

##### CTRL-05 — P2: ROOM/SENSOR y GPS se degradan antes del comando oficial

Fuentes: `contacts_controller.py:366, 455-468`; `sdk_adapter.py:1384-1400`; `protocol_types.py:114-120`; referencia oficial `commands/contact.py:112, 166-173`.

El controller acepta role ROOM/SENSOR y coordenadas pero sólo pasa `{public_key,name,role}` al adaptador. El SDK real normaliza `type` faltante a1 (CHAT), lat/lon faltantes a0. No traduce role. El serializador oficial escribe precisamente `contact["type"]` y `adv_lat/adv_lon` (enteros LE escalados1e6).

- Repro `room_real_sdk`: POST201 y registro ROOM con(40,-3), **run_sdk_command("add_contact", {type:1,adv_lat:0,adv_lon:0,...})**. Esperado type3, coordenadas40/-3.
- Repro `sensor_real_sdk`: POST201, registro SENSOR, **comando type1**, esperado4.

Adapter real conectado sólo por flag y comandos sintéticos, sin transporte ni radio. Esto confirma discrepancia **en el comando productivo construido**, no estado de flash real ni interoperabilidad RF. Editar un contacto sólo por nombre también puede resetear GPS en el transceptor por estos defaults; no se creó escenario adicional. is_favorite sólo queda local, flags0 en SDK; no se afirma que favoritas deban sincronizarse sin contrato explícito.

##### CTRL-06 — P2: coerción de índices y overwrite cambia el slot/recurso sin intención explícita

Fuentes: `channels_controller.py:268-286` (delete usa int igualmente en317).

Repro `overwrite_false_string`: `{index:1, overwrite:"false"}` cambia canal existente Old→Replaced y HTTP200 porque bool("false") es True. El texto de la respuesta de conflicto exige explícitamente overwrite=true. Esperado422 por tipo o409 sin booleanTrue.

Repro `fractional_index`: index2.9 se convierte a2, envia `set_channel(2,...)`, guarda índice2 y devuelve201. Esperado rechazar índice no entero, no editar otro slot. Son peticiones JSON válidas atravesando el router; el query merge puede introducir strings y amplía la relevancia del boolean string (auth/routing se audita aparte). No atribuir el hallazgo al límite de canales0..15 previo del SDK.

##### CTRL-07 — P2: path hash inválido se convierte silenciosamente en0 y configura hardware

Fuentes: `config_controller.py:355-367`.

POST `/api/config/path_hash_mode` con "nonsense", -1, true o1.0: todos **HTTP200/path_hash_mode0 y admin.set_path_hash_mode(0)**. Esperado422 antes de comando y rango0/1/2. Repros `path_hash_*` capturan todos los argumentos. El contrato explícito del docstring dice0/1/2; pasar valores inválidos resetearía el modo real al cero. No duplica validación batch del executor admin de capa4; ésta es conversión anterior exclusiva REST.

##### CTRL-08 — P3: tipo inválido de autoadd produce500

Fuentes: `config_controller.py:377-387`; integración `api_router.py:653, 411-415`.

Repro `autoadd_bad_flags`: flags="nonsense" causa ValueError por int sin guard y **HTTP500 internal_server_error**. Esperado422, ninguna llamada admin. No es corrupción/mutación confirmada, sí un error de contrato y exposición de texto de excepción al cliente. No se plantea como exploit crítico.

##### CTRL-09 — P2/P3: exportación de contacto permite clave inválida y mezcla errores con raw_hex

Fuentes: `contacts_controller.py:148-211`.

Repro `contact_export_invalid_key`: public_key="not-a-key" genera **HTTP200/statusok y QR/URI/tag con esa clave no hexadecimal ni32 bytes**, pese a respuesta ERROR del adapter. Esperado422 previo a adapter y generación. También public_key se concatena sin encoding propio; la validación64hex eliminaría ese riesgo, no se hizo ataque externo.

Repro `contact_export_rejected`: adapter devuelve `{status:ERROR,error:"synthetic rejected"}` y la respuesta anunciaok almacenando ese **objeto en `data.raw_hex` y `result`**, no stringhex. La URI derivada localmente de una clave válida puede ser una capacidad de fallback legítima; este repro **no prueba que todo fallback de export deba fallar**, sólo que no se distingue el fracaso de export de hardware y raw_hex viola su formato declarado por nombre. No contar el fallback útil como pérdida de datos. Sin adapter también retorna URI local por diseño leído.

##### CTRL-10 — P2: logout remoto ignora error del administrador

Fuentes: `repeater_controller.py:80-89`.

Repro `logout_rejected`: handler retorna `{status:error,code:503,message:"synthetic rejected"}` y POST `/api/repeater/remote/logout` responde **200/statusok/data.statuserror**, además registra INFO "Sesión cerrada". Esperado503 y no afirmar cierre. Se usó handlerfake para materializar su contrato de rechazo; no se ejecutó logout remoto real ni comprobó autenticación de hardware.

##### CTRL-11 — P3: is_favorite stringfalse se guarda True

Fuentes: `contacts_controller.py:374, 438`.

Repro `contact_coords_favorite`: POST nuevo contacto con `is_favorite:"false"` devuelve201 y **is_favorite:true** en registro real persistido. Esperado422 (esquema estricto) ofalse si se admite coerción textual. No es fallo de rol; las guardas LOCAL/REPEATER sí pasaron los controles.

##### CTRL-12 — P2: configuración REST admite NaN/infinito/rangos imposibles en protecciones de airtime

Fuentes: `config_controller.py:118-155`; consumidores/persistencia `rate_limiter.py:321-373, 458-463`.

Repro `airtime_nonfinite_config`: POST `/api/config` con duty_cycle_limit_pct="NaN", warn_threshold_pct=-20, cutoff_threshold="Infinity", cutoff_resume250, flagsenabled="false", delays="NaN" retorna **200/statusok**. Tracker real queda duty_limitnan, warning-20, cutoffinf, resume250, cutoff_enabledTrue; delay_enabledTrue ydelay_snan enconfig. Esperado422 antes de cambios: finitud/rangos consistentes y booleanos verdaderos. Las cadenas "NaN"/"Infinity" son JSON válido, no depende de permitir tokens JSON no estándar de entrada. Handleradmin simulado acepta parámetros (el executor actual no valida estos campos de airtime por lectura); no se usa hardware.

Tras `await tracker.flush_history()` se guarda **JSON real que contiene tokens NaN e Infinity**; un parser estricto lo rechaza. `get_stats()` calcula hourly_budget_ms=nan yis_criticalFalse. Repro `airtime_persisted_nonstandard_json`. El uso inválido contamina presupuesto/alertas y el contratoJSON; no se midió tráfico real ni se afirmó un bypass de RF observado. No se escogieron nuevos límites ni timers: sólo valores manifiestamente inválidos para el esquema existente.

Se descartó un candidato de bloqueo: `save_history(sync=True)` dentro de loop **programa `_drain_history()` que escribe mediante asyncio.to_thread**, sync sólo evita throttle. No está justificado afirmar IO síncrono enloop desde esta llamada.

#### Controles y límites

- `local_contact_guard`: 400 y no adapter; `repeater_reclassification_guard`: 400 sobre repetidor registrado real. Las suites también comprueban TX LOCAL/REPEATER y rechazo de mutaciones con respuestas oficiales ERROR/None/NOT_SUPPORTED.
- `psk_masked`: GET /api/channels devuelve bullets para PSK privadas; create/update y WS usan máscara por lectura. Export incluye secreto deliberadamente para compartir canal; su autorización pertenece a HTTP y quedó probada por suite para API key existente. No se halló nueva fuga PSK en respuestas ordinarias. No se inspeccionaron datos privados.
- `concurrent_channel_routes`: POST simultáneo canales3/4→201/201, JSON contiene ambos, cero tmp remanentes. Cada ruta usa `_mutation_lock`; save usa thread y replace atómico. **No se confirmó race de escrituras por rutas públicas**. Esto no cubre callers que muten `channels` directamente sin mutex.
- LogsController devuelve raw logs, path local y markdown diagnóstico sin auth propia; el servidor es la frontera de autorización. Se comunicó al agente HTTP/router para contrastar rutas sensibles; no se duplican fugas OBS/admin ya reportadas.
- Lectura de `system_controller`, `packets_controller`, `nodes_controller`, `logs_controller`, `tx_controller` realizada en completo. Paginación negativa/format export desconocido aceptados como fallback, health con defaults y métricas sin limiter son oportunidades de contrato, no se declararon defectos sin endpoint reproducido/expectativa firme.
- No se probó hardware, compatibilidad de firmware real, reinicio de estación, seguridad completa, navegador, cargas sostenidas o performance. Las suites pasan porque sus escenarios no cubren las reproducciones nuevas; no se relajaron expectativas ni se corrigió producción.
- Mejoras propuestas, sin implementación: regresiones mantenidas para cada escenario confirmado; esquema estricto común de entrada, estados de resultado exhaustivos incluidos virtuales y parciales; propagación de save false; validación previa del batch; traducción role→type/GPS en frontera del adaptador; respuesta que distinga export local y hardware. AGENTS/skills requieren preservar estos contratos pero los tests actuales cubren parcialmente; no se cambió ninguna instrucción.

### Router y configuración

Inspección cerrada. No se modificó producción, tests mantenidos, documentación ni skills. Se revisaron completamente `src/web/api_router.py`, `config.py` y `.agents/skills/api-design-testing/scripts/validate_api_contract.py`; dependencias sólo para acreditar rutas de ejecución. Skills utilizadas: `api-design-testing`, `security-code-auditor`, `contract-openapi-sync`, con sus límites explícitos. La frontera HTTP y los controladores corresponden al principal y otro agente.

#### Ejecución y aislamiento

Desde `C:/Users/Ruby/Desktop/meshcore-bridge`:

```powershell
.venv/Scripts/python.exe scratch/qa-results/audit-20261001/router-config/reproduce.py
.venv/Scripts/python.exe scratch/qa-results/audit-20261001/router-config/run_targeted.py
```

- Reproducción final: **11 checks confirmados, exit 0**; de ellos ocho comprobaciones de defectos/mecanismos (tres agrupadas como URL), dos controles y un mecanismo adicional a integrar con RX. Evidencia exacta en `reproduce-results.json`; el trace esperado de `epoch='not-an-epoch'` identifica línea 691, no un fallo del runner.
- Helper vigente: **20 smoke cases pasan**; salida en `helper-smoke.txt`. No prueba cabeceras, CORS, autenticación, WebSocket, interoperabilidad RF ni ausencia de bugs.
- Pytest dirigido: **16 passed, cero warnings, 5.02 s**. Python 3.12.14, pytest 9.1.1, pytest-asyncio 1.4.0, pytest-cov 7.1.0. Detalles en `targeted-command.json`, `targeted-junit.xml`, `targeted-pytest.txt`.
- Suite: `test_web_server.py` (11), `test_http_cache_contract.py` (1), tres tests de helper API de `test_skill_helpers.py`, y persistencia/reload de canales de `test_sanitization_fixes.py` (1). El test caché usa puerto SO en loopback y radio virtual; las pruebas restantes usan mocks. No se repitieron suites MQTT, firmware ni fuzzing histórico de otros subsistemas.
- Cobertura de esa suite: `src/web/api_router.py` **45%**, total `src/` **33%**; `config.py` queda fuera del alcance configurado `--cov=src`. Estas cifras no incluyen las reproducciones y no equivalen a auditoría completa.
- Toda importación de config se realiza con `dotenv.load_dotenv` desactivado. El helper limpia/restaura entorno y parchea globals de config, directorios de datos/logs/canales/mapas. `tempfile`, pytest cache/basetemp y coverage tienen rutas propias bajo esta carpeta. Nunca se leyó `.env`, radio, MQTT de producción, SSH, servicios operativos ni navegador.

#### Hallazgos confirmados

##### RC-01 — P2: el router vuelve a parsear query strings y pierde la decodificación URL

Fuentes: `src/web/api_router.py:344-349` primero usa `parse_qs`; `466-499` y `513-519` sobrescriben valores a partir de fragmentos raw con `split('&')`/`split('=')`.

Esperado: parámetros URL equivalentes llegan decodificados al mismo controlador. Actual: `/api/nodes?limit=2` devuelve 200, mientras `limit=%32` devuelve 400 `invalid_integer_param`; filtro de paquetes `direction=%72x&type=CHANNEL%20MSG` se entrega literalmente como `('%72x','CHANNEL%20MSG')`; export `format=%6ason` llega `%6ason` en lugar de `json`. Repros `percent_encoded_pagination_rejected`, `packet_filters_not_url_decoded`, `packet_export_format_not_url_decoded` con espías del controlador y sin consulta a hardware. Impacto: clientes que codifican legalmente la URL pierden paginación/filtros/export aunque la primera fase del router los hubiese interpretado correctamente. El resultado de export concreto depende del rechazo por formato en el controlador; la corrupción del argumento está demostrada.

##### RC-02 — P2: `refresh` se decide por substring de toda la URL

Fuente: `src/web/api_router.py:620`, consumidores `623` y `667`; `ConfigController.get_device_config` consulta hardware cuando `refresh` es verdadero.

Esperado: sólo el parámetro `refresh=true` habilita consulta forzada. Actual: `not_refresh=true` y `refresh=trueish` producen `refresh=True`; `refresh=%74rue` produce False aunque se decodifica como `true`. Repro `refresh_uses_substring_not_parameter` comprueba los cuatro argumentos en un `AsyncMock`. Impacto: lectura de configuración fuerza consultas seriales innecesarias o deja un snapshot antiguo por interpretación errónea. No se enviaron paquetes RF ni se afirma un flood por este único defecto.

##### RC-03 — P2: entrada incorrecta de reloj se transforma en HTTP 500 o se trunca antes de validarla

Fuente: `src/web/api_router.py:688-692`, catch general `412-415`.

Esperado: entrada inválida del cliente genera error de validación; booleanos/fracciones no se convierten silenciosamente en epochs enteros. Actual: `{'epoch':'not-an-epoch'}` devuelve 500 `internal_server_error` con `invalid literal for int()`; `epoch=True` y `epoch=1.5` llegan al controlador como entero 1. Repro `clock_input_500_and_lossy_coercion`. El controlador es un espía que devuelve 200 para acreditar transformación; no se afirma que el RTC real haya quedado en 1970 ni se modificó un reloj. Impacto confirmado: un error de cliente se contabiliza como fallo interno y los validadores siguientes pierden el tipo/valor original. Alias `/api/node/sync-clock` y `/api/config/sync_clock` convergen a esa ruta.

##### RC-04 — P3: rutas inexistentes con prefijo reconocido se presentan como método no permitido

Fuentes: dispatch por `startswith` en `362`, `371`, `391`, `398`; fallbacks 405 en `462`, `505`, `558`, `616`.

Esperado: recurso inexistente 404 independientemente de que su nombre contenga un prefijo conocido. Actual: GET `/api/system/logs_extra`, `/api/packets_extra`, `/api/analytics/unknown`, `/api/admin_extra` devuelven 405, mientras `/api/unknown` devuelve 404. Repro `unknown_prefix_routes_405`. Impacto: contrato/error de descubrimiento incorrecto, no demostración de acceso a recurso ni bypass de autorización.

##### RC-05 — Complemento de RUN-05: caché Web incrementa nuevamente estadísticas RX

Fuentes: `src/web/api_router.py:268-275`, `327-329`; entrada productiva `MeshCoreWebServer.broadcast_event` en `src/web/http_server.py:199-201`; RxEventRouter agenda ese broadcast en `src/rx_router.py:370` después de contabilizar RX.

Esperado: el broadcast y la caché de un evento ya procesado conservan sus contadores. Actual: nodo CLIENT con RX=1, evento normalizado `{'event_type':'direct','sender':key,'text':'Hello audit'}` → `recent_messages` recibe un elemento y RX pasa a 2. Repro `web_cache_counts_already_recorded_rx`. La misma escritura existe en rama telemetría. Este es un mecanismo adicional al doble conteo de SDK DM observado por el agente runtime; integrar en su hallazgo en lugar de contar dos veces el mismo defecto. La reproducción acredita el incremento adicional sobre un paquete previamente registrado; no pretende medir aquí el total de la cadena runtime completa.

##### RC-06 — P2 condicional a valores de entorno: capacidad RX/TX sin rango y parser central eludido

Fuentes: `config.py:51-56`, `113-114`, validación `164-225`; consumidores reales `src/rx_router.py:217`, `src/rate_limiter.py:582-583` vuelven a leer el entorno con `int()`.

Esperado: configuración inválida se rechaza con explicación o usa el fallback central consistentemente; capacidades mantienen admisión finita y permiten recepción. Actual, repro `invalid_capacity_config_accepted_or_parser_bypassed`:

| Entorno MAX_RX_CONCURRENCY / MAX_TX_QUEUE_SIZE | config importado | Consumidor RX | Cola TX |
|---|---|---|---|
| `0` | ambos 0, sin error | semaphore 0; acquire no termina y vence timeout controlado | maxsize 0; admite 501 entradas NORMAL |
| `-1` | ambos -1, sin error | ValueError de Semaphore en construcción | maxsize -1; admite 501 entradas NORMAL |
| `not-an-int` | fallback 20 / 500 | ValueError de int al construir | ValueError de int al construir |

El desalojo por LOW de `CustomTxQueue` no impide 501 entradas NORMAL cuando maxsize<=0. No se inició worker ni callback TX. Impacto: valor configurado puede detener procesamiento RX, romper arranque o retirar el límite de admisión TX. Los defaults 20/500 no reproducen este problema; no se presenta como agotamiento de memoria medido ni como vector remoto.

##### RC-07 — P2 condicional a entorno: NaN pasa el validador y anula la supervisión serial

Fuentes: `config.py:58-63`, `106`, `190`; `src/serial/watchdog.py:74-75`, `157-159`; bridge construye watchdog con el intervalo de config.

Esperado: intervalo finito validado antes de iniciar supervisor. Actual: `WATCHDOG_INTERVAL_SEC=nan` importa sin rechazo ni la advertencia `interval < 5`; en ciclo conectado `int(interval / step_sleep)` registra `cannot convert float NaN to integer`, entra en salvaguarda y nunca alcanza la comprobación de hardware de esa iteración. Repro `nonfinite_watchdog_interval_accepted_breaks_cycle` usa adaptador fake sin ping/reconexión, captura una iteración y cancela el sleep para terminar limpiamente. Impacto: mientras esa configuración permanezca, el supervisor repite el error en vez de comprobar vivacidad. No se requiere Ni se ejecutó acceso serial real; se distingue misconfiguración local de entrada remota.

#### Instrucciones/skills: discrepancia comprobada

##### RC-S01 — P3 documental: aviso del skill API no describe el helper vigente

`.agents/skills/api-design-testing/SKILL.md:69` dice «utiliza mocks antiguos» y no ejecutarlo como garantía de «aislamiento». El helper actual `validate_api_contract.py:27-65` limpia/restaura entorno, desactiva dotenv, parchea paths y globals, usa MapTileService temporal; sus mocks `68-106` emplean contratos actuales, future TX fake y no arrancan worker ni conexiones. Pasan sus 20 casos y los tres tests mantenidos que verifican aislamiento, contratos y exit code. Mejorar sólo la descripción para separar smoke del router de cobertura HTTP/RF; ningún archivo de skill se modificó. La parte «no comprueba cabeceras HTTP» sigue correcta.

#### Controles, coordinación y límites

- Fuzz dirigido de `limit` sólo en GET, con 12 valores JSON/strings: ninguna excepción sale del router; resultados 200/400 en `bounded_get_fuzz_does_not_throw`. `True` se admite como 1 por `int`, registrado como límite del contrato de tipo sin sumar un hallazgo independiente.
- El helper `isolated_environment` fue inspeccionado antes de ejecutarlo; tests vigentes confirman no apertura de dotenv/datos operativos y restauración del entorno/config del llamador.
- El principal tiene propiedad de los bypass HTTP por barra final y `/api/system/logs` canónico público. Se comunicó la discrepancia entre normalización del router y autorización exacta; no se duplican hallazgos ni se afirma que el router autentique por sí mismo.
- No se duplican diagnóstico bloqueante/Markdown/puertos, ya asignados al principal. Persistencia, secretos y caché de los controladores quedan a su agente; `config.py` no contiene un escritor de configuración que justifique inventar una carrera de persistencia propia.
- No se ejecutó Playwright ni se generó OpenAPI; las skills distinguen comparación léxica de contrato semántico y no prometen equivalencia. En esta fase no se realizaron fixes, commits, push ni cambios en umbrales/timers/radio.
- La revisión dirigida no garantiza ausencia de otros fallos. Los hallazgos condicionales requieren los valores explícitos reproducidos y los controles con mocks no certifican interoperabilidad física.

### Mapas, estáticos y WebSocket

Auditoría de documentación de defectos, sin modificaciones de producción. Inspección cerrada. Archivos revisados: `src/web/map_tile_service.py`, `src/web/http_server.py` (estáticos/caché, lector y loop WebSocket, apagado); lectura inicial de `src/web/security_inspector.py` para contextualizar pruebas existentes. La autenticación HTTP pertenece al principal y consta en `auth-notes.md`; no se duplica aquí.

Skills aplicadas: `security-code-auditor` y lectura de `web-browser-inspection` para sus límites de aislamiento. No se ejecutó navegador ni pruebas de carga. Datos y SQLite sintéticos, dotenv mock antes de importar, DATA_DIR/LOG_DIR temporales, sin radio, broker, archivos operativos ni cambios en referencias.

#### Verificación

Comando de suite dirigida ejecutado antes de estrechar la asignación a contratos de mapas/estáticos/WS:

```powershell
$env:COVERAGE_FILE = (Join-Path (Get-Location) 'scratch/qa-results/audit-20261001/http/.coverage')
.venv/Scripts/python.exe -m pytest tests/test_web_security_and_maps.py tests/test_security_audit.py tests/test_websocket_live.py tests/test_http_cache_contract.py tests/test_web_official_compatibility.py -q -k 'client_ip or websocket or map or traversal or dos or static or auth or secret_export' -o cache_dir=scratch/qa-results/audit-20261001/http/pytest-cache --basetemp=scratch/qa-results/audit-20261001/http/pytest-temp --junitxml=scratch/qa-results/audit-20261001/http/junit.xml --cov-report=json:scratch/qa-results/audit-20261001/http/coverage.json --cov-report=term
```

Resultado: **21 passed, 1 skipped, 38 deselected**, 3.95 s; JUnit sin fallos ni errores. Skip: `test_map_tile_symlink_cannot_escape_map_storage`, plataforma sin permiso de creación de symlinks. No se aumentaron privilegios para ese caso. La fixture de caché levanta su propio servidor virtual de loopback; no utiliza una estación operativa. Cobertura dirigida: http_server 51.33%, map_tile_service 75.63%, security_inspector 86.27%; no acredita cobertura integral de seguridad. Mypy/ruff/navegador no se ejecutaron en esta fase.

Reproducción final, independiente de pytest:

```powershell
.venv/Scripts/python.exe scratch/qa-results/audit-20261001/http/reproduce_maps_compat.py | Tee-Object -FilePath scratch/qa-results/audit-20261001/http/maps-compat-output.txt
```

Resultado **exit 0**, 9 observaciones de comportamiento y control de limpieza, todas con assertions. Evidencias `maps-compat-results.json` y `maps-compat-output.txt`. Este driver no abre servidores: llama los handlers reales usando StreamReader/Writer en memoria y archivos temporales. Para WebSocket se reproducen frames enmascarados de cliente. Control final: cero tareas pendientes, bases explícitamente cerradas, sockets virtuales descartados/cerrados. Los defectos son reproducibles en las funciones reales; este driver no constituye prueba por red de navegador/proxy.

#### Defectos reproducidos

##### MAP-TMS-WRONG-FALLBACK — P2, coordenadas geográficas incorrectas

Fuente: `src/web/map_tile_service.py:108`, `:121-126`. El fallback por coordenada XYZ se activa cuando falta una tesela TMS, sin identificar el esquema del archivo. Fixture MBTiles estándar: única tesela z=1/x=0/tile_row=0, sur. `get_tile(1,0,0)` pide norte; debería faltar (404), pero devuelve 200 y los mismos bytes que `get_tile(1,0,1)` sur. La ausencia de una tesela puede sustituirse por otra región del mundo. Repro directa de MapTileService, sin UI. La expectativa de eje Y invertido viene de [MBTiles 1.3](https://github.com/mapbox/mbtiles-spec/blob/master/1.3/spec.md).

##### MAP-URI-SPECIAL-FILENAME — P2, archivo incorrecto y pérdida de solo lectura

Fuente: `src/web/map_tile_service.py:69-75`. La ruta se inserta sin codificar en `file:{path}?mode=ro`. El archivo sintético permitido `map#synthetic.mbtiles` tiene una tesela válida, pero SQLite interpreta `#` como fragmento URI: `PRAGMA database_list` apunta a `map`, se crea ese archivo vacío y `get_tile` devuelve 404. Se registra una conexión como mapa cargado pese a abrir otra base y perder `mode=ro`. Esperado: abrir exactamente el archivo encontrado, exclusivamente en lectura. Reproducción confirmada en Windows con nombres locales sintéticos; no se probó escribir fuera del directorio ni se afirma una explotación de traversal.

##### MAP-CONNECTION-AFTER-WEB-STOP — P3, recursos de mapas permanecen abiertos

Fuente: `src/web/http_server.py:73`, `:90-136`; cierre disponible `src/web/map_tile_service.py:40-51`. El servidor retiene el servicio de mapas del router y `stop()` no lo cierra. Después de cargar una base y ejecutar el stop real con tareas/sockets vacíos, queda una conexión y `SELECT COUNT(*) FROM tiles` sigue funcionando (=1). Esperado de un apagado completo: liberar también ese recurso o definir explícitamente otro propietario que lo cierre. Impacto: manejadores conservados al reiniciar el componente en el mismo proceso y posible bloqueo de reemplazo del archivo en Windows. No se midió agotamiento de recursos ni se afirma fuga entre procesos terminados. El driver llama `service.close()` en finally para limpiar su fixture.

##### HTTP-GZIP-QZERO — P3, negociación de compresión

Fuente: `src/web/http_server.py:1102-1104`. Con `GET /` y `Accept-Encoding: gzip;q=0`, la comprobación por subcadena selecciona gzip. Resultado 200 con `Content-Encoding: gzip` y cuerpo de 68 bytes comprimidos frente a 3263 bytes originales. Esperado: excluir explícitamente esa codificación, sirviendo una representación aceptable. Afecta clientes con preferencias de compresión; no es evidencia de bypass de autenticación. Expectativa: [RFC 9110, Accept-Encoding](https://www.rfc-editor.org/rfc/rfc9110.html#name-accept-encoding).

##### HTTP-HEAD-HAS-BODY — P3, respuesta HEAD

Fuente: `src/web/http_server.py:988`, `:1126-1133`. `_serve_static_file` recibe el método en ctx pero envía el contenido completo. `HEAD /` sintético devuelve 200 y 3263 bytes de cuerpo. Esperado: misma metadata pertinente que GET, sin contenido (o rechazo explícito si el producto no soporta HEAD). El defecto está en el handler real; no se probó pipeline de un intermediario. Expectativa: [RFC 9110, HEAD](https://www.rfc-editor.org/rfc/rfc9110.html#name-head).

##### WS-INVALID-UTF8-ACCEPTED — P3, texto inválido transformado en mensaje válido

Fuente: `src/web/http_server.py:800-804`. El frame de texto enmascarado contiene `{"ty\xffpe":"ping"}`. `errors="ignore"` borra el byte inválido, produce la clave `type` y envía un pong JSON. Esperado: rechazar texto UTF-8 inválido y cerrar apropiadamente, sin reinterpretarlo. Impacto demostrado: comportamiento del heartbeat ante un frame inválido; no se afirma ejecución de comandos ni exposición de datos. El loop real cierra el writer al recibir el siguiente cierre. Expectativa de validación: [RFC 6455 §8.1](https://www.rfc-editor.org/rfc/rfc6455.html#section-8.1).

##### WS-CLOSE-NO-ACK — P3, falta la respuesta del handshake de cierre

Fuente: `src/web/http_server.py:793-794`, `:809-819`. Un Close enmascarado con código 1000 termina el loop y cierra el transporte sin escribir Close de respuesta: `writes=[]`, `writer_closed=true`. Esperado: completar el intercambio de cierre antes del cierre del transporte. Puede provocar cierre anormal percibido por clientes; no se ejecutó un navegador para medirlo. Expectativa: [RFC 6455 §5.5.1](https://www.rfc-editor.org/rfc/rfc6455.html#section-5.5.1).

##### WS-PARTIAL-TIMEOUT-DESYNC — P3, timeout parcial pierde el estado del parser

Fuente: `src/web/http_server.py:829`, `:856-857`, `:865-873`. Control: el frame completo de texto `{"type":"ping"}` se parsea correctamente como opcode 1. Repro: alimentar sólo prefijo `81 8f 61 62` (cabecera y dos bytes de máscara) y esperar el timeout de máscara; para hacerlo determinista la fixture usa `WS_IDLE_TIMEOUT_SEC=0.01`. El catch envía Ping `89 00` y vuelve a leer una nueva cabecera con los bytes de máscara conservados `61 62`, devolviendo Close 1002 `88 02 03 ea`. Resultado en loop real: finaliza, writer cerrado, cero conexiones activas y cero tareas pendientes. El cliente no envió una cabecera inválida; estaba incompleto un frame válido. Esperado: conservar estado o terminar por una política explícita de timeout, sin reinterpretar el remanente como una nueva trama inválida. Con el timeout predeterminado requiere retraso parcial de 30 s; no se midió ese tiempo real ni se hizo carga. Repro en memoria confirma el defecto de estado y el cierre.

#### Limitación de compatibilidad, no explotación demostrada

##### WS-LEGAL-FRAGMENT-REJECTED — compatibilidad RFC pendiente

Fuente: `src/web/http_server.py:834`. Un mensaje legal con frame de texto FIN=0 `{"type":` y continuación FIN=1 `"ping"}` se rechaza inmediatamente con Close 1002. El lector admite sólo FIN=1 y no admite opcode continuación 0. [RFC 6455 §5.4](https://www.rfc-editor.org/rfc/rfc6455.html#section-5.4) contempla ensamblar fragmentos. Registrar como limitación de implementación si el producto sólo promete el subconjunto de frames no fragmentados usado por su SPA actual. No hay evidencia de que el navegador actual emita fragmentos ni de un fallo del flujo ordinario de la SPA; no clasificarlo como vulnerabilidad por sí solo.

#### Límites de cierre

No se ampliaron pruebas REST de controllers/router, autenticación, carga, fuzzing o navegador después de la reducción de alcance. No se volvió a reportar diagnostics bloqueantes (OBS01) ni carreras/cierre TCP de la capa 4. Ningún defecto corregido; sólo driver, evidencia y estas notas en scratch. Los tests mantenidos pasan aun con estas observaciones, que identifican contratos no cubiertos por sus casos actuales.

## Capa 6 — SPA, contratos JS y navegador

Revisión dirigida por el principal tras alcanzar los tres subagentes el límite de uso de la cuenta. Se inspeccionaron completamente core/websocket.js, utils.js, storage.js y eventbus.js; métodos y contratos seleccionados de app.js y los siete módulos, marcado de paleta/formularios/mapa, dependencias externas y reglas CSS relevantes. Los otros módulos extensos no recibieron una lectura exhaustiva línea por línea tras esa interrupción. No presentar esta capa como prueba de todos los caminos de cada módulo ni auditoría completa WCAG. Skills: contract-openapi-sync, html-css-modern-js y web-browser-inspection.

### Evidencia

- Navegador Chromium 151.0.7922.34 / Playwright 1.62.0, estación virtual de fixtures mantenidas, MQTT simulado, loopback efímero y recursos externos bloqueados. **19 pruebas mantenidas aprobadas en 34,31 s**: test_e2e_playwright y test_playwright_e2e_simulation. JUnit/cobertura/salida en frontend-browser/. Dos capturas de suite redirigidas por plugin de scratch; ningún test mantenido editado.
- Driver `reproduce_browser.py`, ejecución final exit 0; 14 vistas capturadas (siete tabs en 1920x1080 y 390x844), controles de teclado/lenguaje/importación y autenticación real. `browser-results.json` y `all-view-geometry.json`. Tras teardown quedaba una coroutine IOCP accept del entorno Windows; el driver la registra, cancela y espera, dejando cero tareas. No se atribuye esa observación sola a una fuga productiva.
- `core_reproduce.mjs`, Node local v24.19.0, exit 0. Importa **JS real del repositorio**; DOM/IndexedDB/fetch/WebSocket mínimos simulados para observar argumentos y resultados. core-results.json registra controles y discrepancias. No se acredita durabilidad IndexedDB real con ese mock ni RF.
- Primer navegador sandbox: 19 errores de setup por spawn EPERM; no fallos del producto. Chromium autorizado fuera del sandbox funcionó. El primer driver borró variables Windows necesarias y Node abortó CSPRNG; se corrigió únicamente el fixture scratch conservando variables OS. Otras hipótesis del driver (salida de foco tras un solo Tab, foco siempre oculto tras Escape, texto literal 401 en consola) fueron corregidas contra lo observado; se conservan salidas originales. No se relajaron pruebas mantenidas ni se arregló producción.
- Se visualizaron las capturas de mapa móvil y chat desktop. No hay overflow horizontal global en las 14 vistas. El mapa real Leaflet no se inicializa porque su CDN se omite deliberadamente; no catalogar ese lienzo vacío como defecto del backend. La geometría de los controles de mapa sí pertenece al HTML/CSS real.
- Helpers: paridad léxica 58 llamadas/101 rutas sin discrepancia detectada; linter frontend anuncia 100% por presencia de marcadores. Ninguno certifica contratos, teclado, etiquetas o sanitización de todos los sinks.

### Hallazgos reproducidos

#### FE-01 [P2] La SPA no conecta WebSocket cuando la clave está configurada y guardada correctamente

Fuente: core/websocket.js:23-26, app.js:23; getAuthHeaders en utils.js:86-94 sí añade X-Api-Key a REST. Browser con BRIDGE_API_KEY sintética y localStorage correcto: GET nodes autenticado 200, **cero WS activos** y consola HTTP Authentication failed; servidor rechaza handshake sin clave. El constructor JS real genera ws://host/ws sin token. Esperado conexión WS autenticada usando la clave guardada. Impacto: actualizaciones en vivo y ACK dejan de llegar en modo protegido aunque REST funcione. No es defecto de exigir autenticación del servidor. Mejora: mecanismo coherente de credencial WS, sin registrar secretos; no aplicada.

#### FE-02 [P2] Un contacto cuyo nombre contiene channel se importa como canal

Fuente utils.js:332/352; settings.js:1164-1185. buildMeshCoreContactUri('channel', clave64) genera URI de contacto válida; parseMeshCoreUri devuelve kind=channel por buscar substring en toda la URI. **processImportPayload real llama POST /api/channels, index1, psk vacío**, en vez de contactos. Control nombre Audit se interpreta contacto. Esperado decidir por esquema/host/path, no por contenido del query. Puede crear o proponer sobrescribir otro recurso; sólo se capturó petición con fetch sintético.

#### FE-03 [P2] Compartir un canal privado usa la clave pública por falta del secreto real

Fuente utils.js:278-286; chat.js:597-602. GET de canales enmascara PSK; confirmShareChannel recibe la cadena de bullets y construye **URI con MESHCORE_PUBLIC_CHANNEL_SECRET** para el canal privado. No consulta exportación autenticada. Repro sobre método real, salida capturada; no se transmitió. Esperado obtener secreto real autorizado o impedir compartir mientras esté enmascarado. El enlace actual no corresponde al canal privado. La PSK pública mostrada es conocida, no una credencial extraída.

#### FE-04 [P2] Importación JSON cambia índice cero a uno

Fuente settings.js:1202. Payload {type:channel,index:0,name:Public Audit} se transforma con parseInt(...) || 1 y **POST index1**. Esperado preservar cero; URI de canal usa ?? y sí puede conservarlo. Repro método real con fetch mock. Posible edición del slot incorrecto, sin hardware.

#### FE-05 [P3] Historial pierde nombre del destinatario en conversaciones sólo salientes

Fuente storage.js:54-74 frente a getDmConversations:229. Chat crea dm_target_name, pero saveMessage no lo conserva. Repro guarda mensaje saliente para Remote Audit; hilo reconstruido se llama **11223344**, no Remote Audit. Esperado preservar el nombre ya proporcionado. Si luego entra un mensaje con sender_name el nombre puede recuperarse; no se afirma pérdida del texto.

#### FE-06 [P2 condicional] Coincidencia con ocho caracteres locales oculta una conversación remota distinta

Fuente storage.js:224. Clave local 11223344+aa*28 y remota 11223344+bb*28, ambas completas y distintas: historial remoto existe pero **getDmConversations retorna cero hilos**. Sin clave local en DOM, aparece. Esperado excluir identidad local exacta o prefijo resuelto sin ambigüedad. No es envío a sí mismo, sino ocultación errónea de datos. Repro almacenamiento mock del método real; requiere colisión de prefijo.

#### FE-07 [P2 condicional] Resolver JS elige el primer nodo ante prefijo ambiguo

Fuente nodes.js:156-169; app.js:592-593 delega a este resolver. Dos claves completas comparten 11223344; resolver del prefijo devuelve la primera completa sin señalar ambigüedad. Esperado rechazo/selección explícita, coherente con TargetResolver backend. Repro método real. Como la API recibiría una clave ya completa, su guarda de ambigüedad no puede reconstruir la intención del usuario. No se probó un DM real equivocado ni que la UI normal siempre use prefijos.

#### FE-08 [P3] El mapa conserva marcadores ausentes del snapshot nuevo

Fuente map.js:649-659/748-765. mapMarkers tiene una entrada; updateMapMarkers([]) deja **una entrada**. Se actualiza lista pero no se reconcilia ni elimina marker previo. Esperado que un snapshot completo vacío retire los marcadores. Repro estado JS real con mapa mínimo, sin Leaflet/render real. Si el array representara un delta la retención podría ser válida; su consumidor NODE_UPDATED usa también arrays de la consulta completa. No se afirma filtración de ubicación externa.

#### FE-09 [P2] Borrar capturas vacía la UI pese a rechazo HTTP

Fuente sniffer.js:331-342. fetch DELETE devuelve 503/ok=false/status error; método real vacía rfPackets y refresca la tabla sin leer el resultado. Esperado mantener caché y mostrar fallo. Repro contiene una captura antes, cero después; el buffer del servidor no se modificó. Contraste: otros formularios sí comprueban el resultado.

#### FE-10 [P2] Paleta inaccesible por teclado, con etiqueta inexistente y foco inconsistente

Fuente app.js:228-310; index.html:1419-1436. Diez comandos son div, tabindex=-1 y sin role; ArrowDown+Enter conserva modal abierto y tab-chat sin ejecutar. Después de cinco Tab, foco sale a langToggleBtn con dialog aria-modal=true. Escape desde input puede dejar cmdPaletteInput enfocado dentro de hidden; el resultado depende del foco anterior y no siempre ocurre. aria-labelledby apunta a cmdPaletteTitle que **no existe**. Esperado poder navegar/activar comandos, nombre accesible válido y restauración de foco. Browser real, capturas y DOM; no acredita toda la conformidad WCAG. La prueba mantenida sólo abre/cierra el modal y por eso pasa.

#### FE-11 [P3] La paleta anuncia búsqueda de nodos pero sólo filtra comandos fijos

Fuente app.js:230-236; texto de input index.html. Nodo Bravo visible en contactos; buscar Bravo produce **cero coincidencias**, aunque placeholder promete buscar nodo. Esperado resultados de nodos o texto que declare alcance real. Repro browser; no fallo de la consulta backend.

#### FE-12 [P3] Paleta permanece en español tras cambiar a inglés

Fuente app.js/paleta estática e i18n.js DOM_MAP. I18n.lang=en y document.lang=en, pero placeholder, primera acción y aria-label siguen en español. Repro llama API real I18n.toggle y abre modal; screenshot command-palette-english.png. Esperado traducción coherente con idioma seleccionado. No se afirma que toda la SPA falle: la navegación sí se traduce.

#### FE-13 [P2] Botón Importar de contactos no abre su modal

Fuente settings.js:_bindElements omite btnHeaderImportContact; :381 sólo registra listener si la propiedad existe. HTML index:288 sí tiene el botón. Click real en tab-contacts deja **importModal invisible**. Esperado abrir formulario, como el botón de sidebar que sí se enlaza. Repro browser, no petición REST ni lectura de fichero.

#### FE-14 [P2] Controles de mapa quedan fuera del área visible en móvil

Fuente HTML/CSS de controles mapa; captura map-390x844.png. Con viewport390, botón btnCenterLocalNode tiene left359, right479, y chkMapHeatmap se posiciona en x611. scrollWidth sigue390 por clipping, así que el test general de overflow no detecta el problema. Esperado controles visibles/usables dentro del viewport. Botón aparece recortado/oculto en captura revisada. Los botones del sidebar chat fuera de pantalla se descartaron: corresponden al drawer cerrado previsto por diseño. Leaflet/CDN omitido no explica la posición de estos controles HTML.

### Mejoras y límites

- Marcado de claims públicos «sin cifrar» también aparece en chat (captura desktop); remite a ADM-08: MeshCore Public usa PSK conocida y carece de confidencialidad frente a participantes, lo que es distinto de no cifrar.
- Linter frontend imprimió 100% pese a FE-10/14. Sus búsquedas de tokens y atributos sólo son heurísticas; ajustar lenguaje y añadir pruebas por comportamiento sin confundir presencia de escapeHtml con todos los sinks protegidos.
- Fixture browser_page escribe meshcore_lang pero i18n.js usa mc_lang. El driver final fija idioma con API real; revisar fixture para que no dependa del idioma del navegador. No se modificó.
- No se usó red externa ni mapa CDN real; no se auditaron exhaustivamente vendors qrcode/icons, todas las traducciones, todos los sinks ni todas las combinaciones de formularios. Se revisaron las rutas relevantes y se dejó esa cobertura explícita después del bloqueo de cuota de agentes.

## Capa 7 — Instaladores, entrypoints, servicio, CI y MCP SSH

Revisión cerrada, sin cambios del código auditado. Lectura completa de install.sh, install.ps1, meshcore-bridge.service, ambos entrypoints, requisitos, pyproject.toml y .github/workflows/ci.yml; revisión dirigida de DEPLOYMENT_GUIDE, pendientes PROJECT_KNOWLEDGE y herramientas SSH MCP. Skill installer-release-maintenance. No se ejecutaron instaladores sobre una estación real, actualizaciones de paquetes, systemd, conexiones SSH ni transmisiones.

Evidencia: installers/reproduce.py y results.json, ejecución final exit 0, ocho escenarios incluyendo un control. PowerShell 7 y Git Bash locales ejecutan **copias** de los scripts en scratch. Python/pip/systemctl/apt-get/chown/sleep simulados, rutas /opt y /etc reemplazadas por directorios sintéticos comprobados dentro de scratch; EUID sustituido sólo en copia. cp/rm reales de Git Bash sólo operaron esas rutas verificadas. Los fallos iniciales USER ausente, mkdir bloqueado por sandbox y prioridad del PATH de Git Bash se corrigieron en el fixture; un chown real rechazó el usuario sintético y no cambió propietarios. No son fallos de un Linux operativo. Las comprobaciones de entrada usan dotenv y Bridge/logging mock; run_forever nunca se ejecuta.

### Hallazgos reproducidos

#### INS-01 [P2] Windows ignora el entorno virtual que utiliza para decidir si instalar

install.ps1:26-42,51-54. Con .venv/Scripts/python.exe presente, PythonPath sigue apuntando a python/py de PATH. Con ambos ausentes termina 1 por Python no encontrado pese existir el intérprete local; con mock global invoca pip y lanzamiento en ese global. No crea .venv cuando falta. Presencia del directorio tampoco acredita dependencias instaladas. Esperado selección y uso coherente de un mismo intérprete/entorno verificado; actualmente puede instalar/ejecutar otro Python. InstallDev instala global y busca Chromium en .venv, una divergencia adicional por inspección, sin instalación real.

#### INS-02 [P2] Windows silencia códigos de salida nativos y anuncia instalación correcta

install.ps1:41-43,51-56,81-84. Python simulado invoca un proceso nativo con exit 42 en ambas llamadas pip y en -Run. Con el comportamiento por defecto PSNativeCommandUseErrorActionPreference=false, continúa, muestra «Dependencias instaladas correctamente» y la invocación PowerShell envolvente acaba 0. ErrorActionPreference=Stop no comprueba LASTEXITCODE. Esperado propagar fallo antes de anunciar éxito o lanzar. No se confundió error de red real con fallo de pip: éste se inyectó de forma determinista.

#### INS-03 [P2] -Run depende del directorio del llamador

install.ps1:22,84. Ejecutar el script por ruta absoluta desde installers/ registra -m src con cwd installers/, no el directorio de la copia. Esperado resolver el paquete del proyecto que contiene el instalador. Python puede no encontrar src o cargar un paquete homónimo. Reproducción acredita argumentos/cwd; no afirma carga de otro src realmente instalado.

#### INS-04 [P2] Linux --dev devuelve 0 aunque falle toda la QA

install.sh:67,71,76-85. Python sintético de venv devuelve 42 para Chromium y pytest fallback; se conserva «synthetic-QA-failure», se imprime verificación finalizada y exit 0. La ruta run_checks también tiene || true. Esperado salida no cero con fallos. El banner incluye Bandit, pero el runner canónico ejecuta pytest/mypy/ruff/docs; Bandit independiente no se acredita por ese banner.

#### INS-05 [P1] --update reemplaza la política de seguridad existente del broker

install.sh:155-163. Fixture meshcore_local.conf con listener loopback, allow_anonymous false y password_file termina reemplazada por listener 1883 0.0.0.0 y allow_anonymous true; se llama restart mosquitto simulado. Esperado conservar o migrar explícitamente la política del operador. Puede abrir publicación/suscripción a la red alcanzable y permitir inyectar comandos bridge según ACL/rutas de la instalación. No se probó explotación de un broker real. DEPLOYMENT_GUIDE:41 reconoce la exposición de la instalación inicial, pero actualizar una política endurecida sigue reintroduciéndola.

#### INS-06 [P2] Linux --update anuncia éxito con servicio inactivo

install.sh:186-198. Systemctl simulado devuelve 3 para is-active; aparece aviso y luego «ACTUALIZACIÓN COMPLETADA CON ÉXITO», exit 0. Esperado diferenciar despliegue de archivos y servicio arrancado, y propagar comprobación fallida. La rama instalación completa tiene lógica análoga :326-336, revisada pero no ejecutada íntegramente; no atribuirle una segunda reproducción.

#### INS-07 [P2] Actualización desde el propio directorio detiene el servicio y falla antes de copiar

install.sh:101,104,114. CURRENT_DIR=INSTALL_DIR: primero llama stop, después cp config.py sobre sí mismo devuelve 1 y set -e aborta. src/marker.py **permanece**. Esperado actualización segura o rechazo antes de detener servicio. El hallazgo histórico PROJECT_KNOWLEDGE que afirma pérdida de src en esta secuencia no se confirmó: la primera copia falla antes del rm. Si se omitiera/modificara esa copia, el riesgo posterior de borrado existiría, pero ese camino no es el observado en el checkout actual.

#### INS-08 [P2] Opción desconocida cae en instalación completa

install.sh:40-89,206. --help no coincide con ninguna rama y llama apt-get update -qq. El mock registra esa operación y devuelve 42, deteniendo el fixture antes de cualquier instalación. Esperado ayuda/rechazo sin efectos, especialmente bajo sudo. No se instalaron paquetes.

#### INS-09 [P2] python -m src pierde las opciones y el logging del entrypoint raíz

src/__main__.py:12-20 frente a meshcore_bridge.py:57-92; Windows recomienda y ejecuta el primero. Con --version, raíz imprime versión sin construir Bridge (control); paquete construye Bridge y llama run_forever simulado. El paquete tampoco configura logging persistente ni el LOG_LEVEL del entrypoint raíz. Esperado contrato de lanzamiento común o documentar diferencias; un comando informativo puede iniciar la estación al usar el entrypoint recomendado. Se capturó invocación, no se arrancó hardware.

### Mejoras y límites

- Servicio ejecuta User=root y KillMode=process. Considerar usuario mínimo con permisos serial y política de cierre del grupo. No se reprodujo una escalada ni un proceso hijo huérfano; no presentarlos como explotación/fuga demostrada.
- Requisitos producción/QA coinciden con pyproject por lectura y declaran mínimos abiertos, sin lock. Mejora de reproducibilidad de despliegue; no se auditó CVE por paquete ni se actualizaron versiones.
- Script Linux no comprueba versión mínima de python3 antes de modificar servicios. La guía exige Python >=3.10; verificar precondiciones antes de desplegar. No se probó instalación en cada distribución indicada.
- CI usa matriz 3.10/3.12 y navegador aislado; no se ejecutó GitHub Actions ni se acreditó su último resultado remoto. Helpers de auditoría con falsos exit 0 descritos en capa 1 pueden hacer verdes sus steps; la suite mantenida y mypy/ruff no comparten esas limitaciones. Bandit -ll -ii filtra hallazgos, no certifica seguridad.
- MCP tools/ssh_mcp/server.py y README inspeccionados íntegramente: fingerprint antes de auth, destino fijo, to_thread, límites de tiempo/salida, staging exclusivo y bloqueo de rutas operativas presentes. Redacción declarada heurística y descubrimiento sin autenticación declarados explícitamente. No hay MCP SSH conectado ni se llamó una estación. Revisión de código dirigida, sin prueba de interoperabilidad Paramiko/SFTP remoto; no hay defecto adicional confirmado de este módulo.

## Capa 8 — Verificación global y límites finales

### Matriz final

| Verificación | Resultado | Alcance y límite |
|---|---|---|
| Pytest mantenido completo | 663 aprobadas, 1 omitida; 81,88 s | 664 casos; hardware y broker simulados; fixtures aisladas |
| Cobertura pytest-cov | 8.541/12.762 líneas ejecutables de src, 66,93%; 4.221 sin cubrir | Sólo cobertura de líneas; no incluye config.py, scripts, skills ni drivers propios; sin medición de ramas |
| Mypy --strict src | Exit 0, 59 archivos, 2,922 s | Objetivo configurado Python 3.10; bibliotecas externas con overrides ignore_missing_imports |
| Ruff check src tests scripts | Exit 0, 0,718 s | Reglas configuradas de pyproject; no auditó vendors ni todos los JS |
| Validador documental | Exit 0, 54 archivos/skills, 0 incidencias, 0,422 s | Estructura/enlaces locales admitidos; no valida semántica, anchors ni portabilidad de file:// |
| Bandit -r src -ll -ii | Exit 0, sin findings del filtro, JSON conservado | SAST heurístico filtrado; no detectó las exposiciones P1 reproducidas |
| Bandit -r src sin filtro | Exit 1, 54 señales LOW, 0 MEDIUM/HIGH | Señales inspeccionadas; detalle y clasificación debajo; no 54 bugs acreditados |
| Navegador mantenido, dirigido | 19 aprobadas, 34,31 s; también incluido en suite final | Chromium 151 / Playwright 1.62, loopback propio, recursos externos bloqueados |
| Drivers específicos | Manifestaciones observadas y assertions aprobadas | Reproducción por función/handler o red según cada sección; no son tests de corrección |
| Python 3.10 local / systemd / RF / GitHub Actions | No ejecutados | Python local 3.12.14; matriz CI inspeccionada, no resultado remoto acreditado |

Se comprobó además parseo AST con feature_version=(3,10) de los 59 módulos src y ambos archivos raíz config.py/meshcore_bridge.py: 61 aceptados. Esto comprueba sintaxis, no compatibilidad de APIs ni runtime Python 3.10.

El skip final corresponde a tests/test_web_official_compatibility.py:228: la plataforma no permite crear el symlink de la regresión de mapas. Es una limitación de esa prueba, no evidencia a favor o en contra de la contención por symlinks. La configuración del proyecto filtra DeprecationWarning y PendingDeprecationWarning; la salida sin warnings no implica que se inspeccionaran todas las deprecaciones.

Comando de la verificación final desde la raíz:

```powershell
$env:PYTHONPATH = 'C:/Users/Ruby/Desktop/meshcore-bridge/scratch/qa-results/audit-20261001/frontend-browser'
$env:COVERAGE_FILE = 'C:/Users/Ruby/Desktop/meshcore-bridge/scratch/qa-results/audit-20261001/full/.coverage'
.venv/Scripts/python.exe scripts/run_quality_checks.py --timeout 900 --report scratch/qa-results/audit-20261001/full/results.json -- tests -ra -p audit_artifacts_plugin -o cache_dir=scratch/qa-results/audit-20261001/full/cache --basetemp=scratch/qa-results/audit-20261001/full/temp --junitxml=scratch/qa-results/audit-20261001/full/junit.xml --cov-report=json:scratch/qa-results/audit-20261001/full/coverage.json --cov-report=term
```

El plugin propio sólo redirige los dos screenshots de test_playwright_e2e_simulation desde tests/artifacts hacia scratch. No altera lógica ni expectativas. Chromium se ejecutó con la elevación autorizada después de EPERM del sandbox. El runner capturó resultados originales de las cuatro herramientas; todos exit 0. Duración de su proceso pytest 83,813 s, diferente del tiempo interno de la suite 81,88 s.

### Revisión complementaria de SAST sin filtro

El primer comando Bandit reprodujo el filtro de CI (-ll -ii) y devolvió 0. Al revisar sus métricas aparecieron 54 señales LOW, por lo que se ejecutó **Bandit -r src sin filtro**: exit 1, 54 resultados LOW, 0 MEDIUM/HIGH. Se conservaron todos en full/bandit-unfiltered.json. Este resultado no se ocultó ni se convirtió artificialmente en un pass.

- **49 B110 y 1 B112:** capturas amplias de Exception con pass/continue. Se revisó su contexto de limpieza, fallback de SDK, conversión de telemetría y presentación. Varias preservan cierre best effort o descartan un registro inválido; otras pueden ocultar fallo de un subpaso. Constituyen candidatos de observabilidad/precisión de excepciones, no 50 defectos funcionales reproducidos adicionales. Los errores observables de éxito falso, sensores, persistencia o rutas tienen sus reproducciones en las capas respectivas; para los restantes no se afirma pérdida de datos ni incumplimiento demostrado.
- **2 B105:** password="" en repeater_executor:661 borra la credencial tras autenticar; la constante en channels_controller:231 es la PSK pública canónica conocida por protocolo. No son dos credenciales privadas hardcodeadas descubiertas. El uso incorrecto del fallback de canal al compartir sí consta en FE-03.
- **2 B311:** random.uniform para jitter de cola y random.randint para tag de traceroute. El primero no tiene propósito criptográfico; el segundo correlaciona respuesta, no autentica al repetidor. No se reprodujo suplantación o colisión; no elevar estas señales a vulnerabilidades de autenticación comprobadas.
- Supresiones nosec inspeccionadas: B104 para bind a todas las interfaces y B324 para SHA1 del handshake WebSocket, con usedforsecurity=False. Bind público requiere considerar la política de despliegue (INS-05/HTTP); el SHA1 aquí forma parte del formato del handshake, no almacena contraseñas. La heurística filtrada no sustituye las pruebas de autorización.

Localizaciones de las 54 señales, conservadas para revisión, **sin sumarlas como errores confirmados**:

| Regla | Archivo/línea | Clasificación |
|---|---|---|
| B110 | `src/admin/cli_command_executor.py:268` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/admin/cli_command_executor.py:393` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/admin/cli_command_executor.py:450` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/admin/cli_command_executor.py:510` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/admin/cli_command_executor.py:690` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/admin/cli_command_executor.py:805` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/admin/cli_command_executor.py:832` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/admin/local_config_executor.py:186` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/admin/local_config_executor.py:414` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/admin/repeater_executor.py:323` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/admin/repeater_executor.py:592` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B105 | `src/admin/repeater_executor.py:661` | Vaciar credencial o PSK pública; no secreto privado descubierto |
| B110 | `src/admin/repeater_executor.py:795` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/admin/repeater_executor.py:1067` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B311 | `src/admin/traceroute_executor.py:79` | Jitter o correlación; explotación no acreditada |
| B110 | `src/bridge_core.py:1043` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B112 | `src/rate_limiter.py:274` | Registro inválido omitido; candidato de observabilidad |
| B311 | `src/rate_limiter.py:748` | Jitter o correlación; explotación no acreditada |
| B110 | `src/repeater_manager.py:666` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/repeater_manager.py:678` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/repeater_manager.py:685` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/repeater_manager.py:698` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/repeater_manager.py:705` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/repeater_manager.py:718` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/repeater_manager.py:725` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/repeater_manager.py:732` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/repeater_manager.py:747` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/sensor_decoder.py:227` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/serial/sdk_adapter.py:321` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/serial/sdk_adapter.py:375` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/serial/sdk_adapter.py:392` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/serial/sdk_adapter.py:434` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/tcp_companion_server.py:86` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/tcp_companion_server.py:165` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/tcp_companion_server.py:195` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/tcp_companion_server.py:251` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/tcp_companion_server.py:268` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/virtual_mesh_adapter.py:554` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/api_router.py:350` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B105 | `src/web/controllers/channels_controller.py:231` | Vaciar credencial o PSK pública; no secreto privado descubierto |
| B110 | `src/web/controllers/contacts_controller.py:325` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/controllers/system_controller.py:24` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/controllers/system_controller.py:32` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/http_server.py:113` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/http_server.py:216` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/http_server.py:222` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/http_server.py:278` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/http_server.py:285` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/http_server.py:805` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/http_server.py:807` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/http_server.py:818` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/http_server.py:939` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/map_tile_service.py:49` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |
| B110 | `src/web/map_tile_service.py:172` | Captura/fallback; contexto inspeccionado, candidato no confirmado individualmente |

### Índice de evidencia local

Los paths siguientes son relativos al checkout y no contienen credenciales operativas. El informe conserva el comportamiento y las referencias suficientes para revisión; los artefactos scratch no forman parte de la publicación Git.

| Capa | Driver/evidencia principal |
|---|---|
| 1 | scratch/audit-20261001/governance/reproduce_governance.py, results.json; scratch/qa-results/audit-20261001/architecture_metrics.py |
| 2 | scratch/qa-results/audit-20261001/protocol/reproduce.py, reproduce.json; protocol_sdk.py, protocol-sdk-result.json |
| 3 | scratch/qa-results/audit-20261001/domain/reproduce.py, reproduce-results.json |
| 4 runtime | scratch/qa-results/audit-20261001/runtime/reproduce_runtime.py, reproduction-results.json |
| 4 administración | scratch/qa-results/audit-20261001/admin/reproduce.py, reproduce.json |
| 4 MQTT/TCP/n8n | scratch/qa-results/audit-20261001/mqtt-tcp/reproduce.py, n8n_actual.cjs, resultados JSON |
| 4 observabilidad | scratch/qa-results/audit-20261001/observability_reproduce.py, observability-results.json |
| 5 HTTP/WS | scratch/qa-results/audit-20261001/http/auth_reproduce.py, auth-results.json, reproduce_maps_compat.py, maps-compat-results.json |
| 5 controladores/router | scratch/qa-results/audit-20261001/controllers/reproduce.py, reproduction.json; router-config/reproduce.py, resultados JSON |
| 6 | scratch/qa-results/audit-20261001/frontend-browser/reproduce_browser.py, browser-results.json, core_reproduce.mjs, core-results.json y 14 capturas |
| 7 | scratch/qa-results/audit-20261001/installers/reproduce.py, results.json, run-output-final.txt y fixtures de scripts copiados |
| 8 | scratch/qa-results/audit-20261001/full/results.json, junit.xml, coverage.json; bandit.json |

### Límites y alcance de las conclusiones

- El informe documenta los problemas encontrados en el checkout base. No garantiza haber descubierto todos los errores existentes. La inspección, los ejemplos reproducidos y la cobertura de tests se complementan; ninguno demuestra ausencia de fallos.
- SPA recibió revisión completa de cuatro módulos core y revisión dirigida de módulos grandes/HTML/CSS, con 14 vistas y escenarios de contratos/teclado. No hay auditoría exhaustiva de cada línea de todos los módulos JS, WCAG completa, todos los sinks XSS, IndexedDB real, código de vendors o fallos de CDN reales.
- Las referencias oficiales fueron sólo lectura. No se actualizaron ni se certificó equivalencia completa de copias sin Git con upstream; se cotejaron layouts, opcodes y callsites concretos. La especificación MBTiles 1.3 enlazada fue verificada en su fuente primaria para el eje TMS.
- No se probaron radios físicos, firmware compilado, airtime medido por radio, topologías LoRa reales, broker/SSH de producción, servicios systemd, todas las distribuciones de Linux ni instalaciones reales. Estimadores, mocks y simuladores conservan esa condición.
- La revisión no incluyó actualizaciones de dependencias, búsqueda exhaustiva de CVE ni benchmark real del servicio o stress sostenido con agotamiento de recursos. Backpressure y fugas concretas se limitan a las cantidades/ciclos observados.
- Sólo report.md es el entregable versionable de esta tarea. Los intentos fallidos de fixture no se atribuyen al producto; las expectativas mantenidas no fueron relajadas. Recomendaciones y propuestas descritas no están implementadas.
