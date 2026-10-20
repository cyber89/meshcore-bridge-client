# Validación y remediación de auditoria.reporte.md

Fecha: 2026-10-20. Base de revisión: `b4e7fde` en `main`. El informe de entrada
declara `2b796a7`; se contrastaron sus 69 IDs con el checkout actual antes de
editar. El archivo original, inicialmente sin seguimiento, se conserva intacto.

## Alcance y decisiones

Equipo: principal de integración/documentación/calidad; especialista de
backend/protocolo/refactorización; especialista de web/seguridad/frontend;
especialista de MQTT/persistencia. Se separó propiedad de archivos y se hizo
revisión cruzada de los cambios de servicios y TCP antes de integrar.

El usuario mantuvo expresamente **solo revisión y verificaciones estáticas**.
No se ejecutaron pytest, colección, Playwright, sondas de comportamiento,
instaladores, servicios, radio ni broker. No se leyó `.env` ni estado operativo.
Las regresiones nuevas y actualizadas son código pendiente de ejecución.

Decisiones explícitas del usuario:

1. Conservar compatibilidad con la app oficial: framing Companion binario sin
   imponer `TOKEN`. El listener comienza en loopback; acceso remoto requiere IPs
   explícitas o un cliente que implemente el token propio. CLI no clasificado y
   opcodes desconocidos se rechazan; compatibilidad completa requiere hardware.
2. Conservar `admin:admin`, con configuración inicial restringida a loopback.
   Socket original, cliente efectivo y Host deben ser locales, sin cabeceras de
   forwarding; siempre se exige contraseña actual para cambiar credenciales.
3. Denegar `/admin` no autorizado sin respuesta RF y conservar eco limitado a
   **120 bytes UTF-8**, sin partir caracteres.

## Correcciones al diagnóstico original

- CORE-05: `get_time` consulta el RTC por Companion. Firmware
  `reference/meshcore/examples/companion_radio/MyMesh.cpp`, rama
  `CMD_GET_DEVICE_TIME`, responde con `writeFrame`; no es un ping por LoRa.
- CORE-07: el parser raw es un seam en memoria sin transporte físico, pero el
  sniffer recibe eventos SDK. No corresponde retirar todo el sniffer ni atribuir
  `crc_errors` a los paquetes RF del transceptor.
- CORE-11: el código ya usa `critical=observation_key is None`; una observación
  rechazada no se etiqueta crítica. Se descarta ese hallazgo.
- CORE-12: `size_bytes` mide contenido observado antes de redacción, no contenido
  retenido ni necesariamente la trama RF completa. Se aclara el contrato.
- CORE-13: el cierre ante historial de airtime corrupto protege el presupuesto
  persistente. No se sustituye por historial vacío.
- WEB-06: el límite 429 ya estaba en el perímetro. Se corrige la denegación de
  autenticación WS con HTTP cuando la extensión ASGI lo permite.
- WEB-10: probar un broker LAN es una capacidad del único operador autenticado,
  que también puede configurar el broker. Bloquear rangos privados rompe ese
  contrato; una política de destinos/egress requiere definir otra frontera.
- WEB-12: KDF de una plaza y presupuesto global son defensas existentes; la
  auditoría no demostró que ampliar concurrencia fuese seguro o necesario.
- UI-11: tema raíz y selección ya se aplicaban antes del login. FOUC y descarga
  redundante requieren medición; no se presentan como regresión reproducida.
- UI-12: las cifras fechadas describen entregas históricas. Se conservan y se
  enlaza el manifest actual en la guía de entrega.
- DATA-08: MQTT admite `keepalive=0`. Se valida 0..65535 y QoS 0/1/2, sin inventar
  mínimos de cinco segundos ni intervalos de operación.
- DATA-15: el instalador prepara el entorno candidato y `COMPONENTS` incluye
  `venv`; `apply()` conserva el anterior antes de `relocate_environment`.
  `rollback()` restaura ese componente completo. Se descarta el defecto alegado.
- QA-01: las cláusulas SQL eran constantes y los valores parametrizados; B608
  no probaba SQLi. Cuatro consultas literales conservan filtros y eliminan el
  hallazgo estático sin silenciarlo mediante `nosec`.
- QA-04: el diagrama ya permite L3 → L5. Los imports de persistencia citados no
  son infracciones por sí solos. Sí quedaba sin ejecutar el contrato declarado.

## Matriz de los 69 hallazgos

**Aplicado** indica cambio revisado en código, sin acreditar funcionamiento
dinámico. **Conservado** indica decisión o contrato mantenido. **Parcial** y
**Pendiente** no se consideran cerrados. Cada ruta es relativa a la raíz.

| ID | Estado | Evidencia y resultado |
|---|---|---|
| CORE-01 | Aplicado | `src/serial/sdk_adapter.py`, `bridge_core.py`, `tcp_companion_server.py`: clasificación explícita, RF por cola/cutoff existentes, remoto cerrado sin política. |
| CORE-02 | Aplicado | `src/services_manager.py`: inyecta `max_clients` y `allowed_ips` guardados al servidor. |
| CORE-03 | Aplicado | `src/rx_router.py`: fin de worker vuelve a asegurar consumo; drain espera cola y workers. |
| CORE-04 | Aplicado | `src/tcp_companion_server.py`: un drenaje por cliente, presupuesto/timeout existentes, RX no espera lectura TCP. |
| CORE-05 | Aplicado | `src/serial/sdk_adapter.py`: lock ocupado aplaza comprobación local sin contar falso fallo. |
| CORE-06 | Aplicado | `src/serial/sdk_adapter.py`: consumidor único, cola 256 y reserva de handoff entre hilos 256; overflow visible. |
| CORE-07 | Conservado | Raw permanece seam en memoria; sniffer SDK activo, CRC raw no mide CRC de hardware. |
| CORE-08 | Aplicado | `src/rx_router.py`: hash de contenido/origen/destino/secuencia/tipo; excluye hop mutable. Frames idénticos tras wrap siguen ambiguos sin identidad más amplia. |
| CORE-09 | Aplicado | `src/metrics_aggregator.py`: reconoce `0xffff` como broadcast. |
| CORE-10 | Aplicado | `src/rx_router.py`: conversión tolerante de canal/hops; conserva evento ante valor no numérico. |
| CORE-11 | Descartado | Indicador de críticos ya correcto en código actual. |
| CORE-12 | Conservado | `src/packet_buffer.py`: contrato explícito de tamaño observado previo a redacción. |
| CORE-13 | Conservado | `src/rate_limiter.py`: se mantiene cierre ante historial corrupto, sin reset de airtime. |
| CORE-14 | Aplicado | Apps oficiales usan allowlist y protocolo binario; token propio sigue opcional para clientes compatibles. |
| WEB-01 | Aplicado | `authentication.py`, `auth_store.py`, protocolos ASGI: bootstrap local y contraseña actual siempre, estado anónimo no revela setup. |
| WEB-02 | Aplicado | `security_inspector.py`: inspección de rutas sin blacklist de texto arbitrario; validación de campos/controladores y escape de salida. |
| WEB-03 | Pendiente | HTTP local/LAN se conserva; configurar HTTPS en proxy para transporte remoto pertenece al despliegue. No se afirma cifrado nativo. |
| WEB-04 | Aplicado | `asgi_security.py`: ausencia del servicio de autenticación responde 503 y falla cerrado. |
| WEB-05 | Aplicado | `authentication.py` y perímetro: error de almacenamiento/auth controlado con 503 sin detalle secreto. |
| WEB-06 | Aplicado | `authentication.py`: HTTP denial WS 401/403/503 cuando ASGI lo admite; fallback de cierre no acepta socket. |
| WEB-07 | Aplicado | `authentication.py`: cache de autorización limitada a una petición HTTP; WS persistente vuelve a validar. |
| WEB-08 | Aplicado | Teselas autenticadas conservan caché privada y Vary por credenciales; errores usan no-store. |
| WEB-09 | Aplicado | `config.py`, `asgi_websocket.py`: una fuente validada para timeout WS, finitud y mínimo existentes. |
| WEB-10 | Condicionado | Capacidad de conexión del operador se conserva, incluidos brokers LAN; falta política egress si cambia el modelo de amenaza. |
| WEB-11 | Aplicado | `access_policy.py`: origen propio por defecto, allowlist exacta explícita para otros orígenes. |
| WEB-12 | Conservado | Presupuestos de login y KDF acotado conservados; sin medir disponibilidad ni ampliar concurrencia. |
| WEB-13 | Aplicado | Preflight/refresh usan POST; GET refresh=true devuelve 405; SPA, catálogos y expectativas actualizados. |
| UI-01 | Aplicado | `index.html`, `app.css`: skip link a main enfocable y oculto mientras autentica/login. |
| UI-02 | Aplicado | `chat.js`: drawer deja de autoabrirse al iniciar en móvil. |
| UI-03 | Aplicado | `chat.js`, HTML: aria-expanded, inert cerrado/fondo abierto y trampa Tab. |
| UI-04 | Aplicado | `chat.js`: Escape respeta modal superior y eventos ya atendidos. |
| UI-05 | Aplicado | `settings.js`: nombre accesible de canal incluye índice, nombre y cifrado. |
| UI-06 | Aplicado | `index.html`, `app.css`: wrapper desplazable y fondos sobre celdas; aceptación visual pendiente. |
| UI-07 | Aplicado | `app.css`: backdrop con opacity/visibility y transición. |
| UI-08 | Aplicado | `asgi_assets.py`: HTML vuelve a no-store conforme al contrato. |
| UI-09 | Aplicado | `.github/workflows/ci.yml`: build-check y sintaxis JS con herramientas Node fijadas. CI no ejecutado en esta entrega. |
| UI-10 | Aplicado | `settings.js`: promesa única para QR, token de petición y error visible; evita modal tardío. |
| UI-11 | Condicionado | No se demuestra FOUC ni coste de red; no se cambia la estrategia de temas sin medición. |
| UI-12 | Conservado | `docs/FRONTEND_DELIVERY.md`: evidencia histórica conservada y manifest vigente enlazado. |
| UI-13 | Aplicado | `app.css`: reglas compartidas y tokens de rol con colores anteriores. |
| DATA-01 | Aplicado | `external_mqtt_client.py`: TLS falla cerrado, CA privada y contexto compartido con prueba de conexión. |
| DATA-02 | Aplicado | LWT se configura con identidad antes de CONNECT jerárquico y usa el mismo tópico de estado. |
| DATA-03 | Aplicado | `services_manager.py`: candidatos validados, commit/rollback de referencias y persistencia con propiedad de transacción. |
| DATA-04 | Aplicado | Workflow n8n: whitelist vacía/configurable con claves completas 64hex; denegación sin comando ni respuesta RF. |
| DATA-05 | Aplicado | Flags clear_password/clear_token explícitos en API y checkboxes UI; vacío/máscara conservan secretos. |
| DATA-06 | Aplicado | `scripts/export_logs.py`: Bearer desde entorno; elimina construcción de bridge y apertura de SQLite como fallback. |
| DATA-07 | Aplicado | `external_mqtt_client.py`: rechazo Paho reencola al frente y termina el drenaje, sin timer nuevo. |
| DATA-08 | Aplicado | `services_config.py`: tipos/dominios antes de guardar/conectar; UI/API CA y errores 422. |
| DATA-09 | Aplicado | `contact_manager.py`: lookup y actualización de discovery bajo RLock. |
| DATA-10 | Aplicado | Adaptador JSON explícito falla conservando bytes originales; SQLite ya falla cerrado. |
| DATA-11 | Aplicado | `config.py`: MQTT_MAX_PAYLOAD_BYTES exige entero positivo. |
| DATA-12 | Aplicado | Cuatro nodos TX de n8n limitan texto a 120 bytes UTF-8, sin dividir caracteres. |
| DATA-13 | Aplicado | `diagnostics.py`: describe SQLite/legacy según backend inyectado, sin afirmar salud del disco. |
| DATA-14 | Aplicado | `scripts/staged_update.py`: flush/fsync de journal y fsync de directorio POSIX; prepare comparte escritor. |
| DATA-15 | Descartado | Entorno virtual anterior ya está dentro del backup/rollback del instalador. |
| QA-01 | Aplicado | `station_database.py`: cuatro SQL literales parametrizados; Bandit sin medios/altos en comprobación local. |
| QA-02 | Aplicado | Rutas de servicios resueltas al llamar y fixture temporal explícito. |
| QA-03 | Aplicado | db_path/data_dir reales; inspecciones comparten estación virtual temporal, autenticación y cierre. |
| QA-04 | Parcial | `check_layer_contracts.py` aplica en CI el contrato forbidden existente por AST transitivo; cinco capas/imports dinámicos no verificados completamente. |
| QA-05 | Aplicado | CI añade pip check, Node, build-check y sintaxis JS; no se afirma ejecución remota. |
| QA-06 | Pendiente | Entorno instalado difiere de pins y contiene amqtt incompatible. No se sustituye la venv compartida durante esta tarea. |
| QA-07 | Parcial | Se extraen responsabilidades de recarga/TLS/TCP y se acotan tareas; no se impone gate de complejidad arbitrario ni se divide todo módulo grande. |
| QA-08 | Aplicado | Runner usa rutas existentes, valida ausencias y calcula porcentaje real. |
| QA-09 | Aplicado | Test SENSOR renombrado static_contract; no se presenta como prueba de navegador. |
| QA-10 | Aplicado | CI prepara Leaflet con hash fijado; ausencia de fixtures falla en CI, skip local explícito. |
| QA-11 | Aplicado | `server_protocol.py`: seam del ASGI de producción, sin servidor nativo futuro. |
| QA-12 | Pendiente | Pack histórico 465,98 MiB; purga requiere reescritura/force-push y aprobación específica, fuera de esta entrega. |
| QA-13 | Aplicado | Scripts de inspección usan bind loopback con puerto cero y obtienen puerto del socket real. |
| QA-14 | Regresión preparada | Importación ya transaccional/idempotente; se añaden casos truncado/markers/bytes conservados sin ejecutar. No se demuestra defecto de producción. |

## Checklist de impacto RF

| Cambio | Airtime y frecuencia | Spam/bucles | Persistencia/timers |
|---|---|---|---|
| TCP Companion | Un comando solicitado por cliente; RF por cola existente, consultas locales sin RF. No se añaden sondeos. | Rol/clave local de chat y cutoff conservados; opcodes no clasificados rechazados. | Misma persistencia de airtime y cuotas; sin nuevos intervalos/reintentos. |
| Watchdog | Sigue consultando Companion local con parámetros existentes; lock ocupado aplaza consulta. | No crea respuesta RF ni reconexión por contención del lock. | No cambia scheduler, umbral ni persistencia. |
| n8n /admin | Denegación: cero TX. Autorizado conserva ruta existente. | Claves completas; guardas de origen/dedup existentes conservadas. | Sin timer/reintento nuevo. |
| n8n eco | Misma respuesta por mensaje entrante, texto hasta 120 bytes UTF-8 autorizado por el usuario. | Conserva guardas existentes y cola TX del bridge; no garantiza ausencia de loops en workflows externos modificados. | No cambia periodicidad ni rearma scheduler. |

No se midió airtime físico ni se simuló reinicio de una estación real. La revisión
preserva el fallo cerrado ante corrupción de historial y no modifica cooldowns.

## Verificación y límites

Resultado de clasificación: **54 Aplicado, 5 Conservado, 2 Descartado,
3 Pendiente, 2 Condicionado, 2 Parcial y 1 Regresión preparada**. No son 54
defectos acreditados dinámicamente como resueltos.

Verificación final local con CPython 3.12.14 sobre Windows, tras integrar
correcciones de referencias provisionales, cancelación repetida e identidad:

| Comando / revisión | Resultado |
|---|---|
| `python -m ruff check src tests scripts` | Pasa con Ruff 0.16.3 instalado. |
| `python -m mypy --strict src` | Pasa, 87 archivos, mypy 2.3.1 instalado. |
| `python -m bandit -r src -ll -ii` | Pasa: 0 medios/altos; 68 bajos fuera del gate, 9 supresiones específicas existentes. No acredita ausencia de vulnerabilidades. |
| `python scripts/validate_project_docs.py` | 116 documentos, 0 problemas de estructura/enlaces. |
| `python scripts/check_layer_contracts.py` | 1 contrato forbidden, 0 infracciones; alcance AST declarado. |
| `node scripts/build_frontend.cjs --check` | 32 activos; 2.413.339 bytes fuente, 2.083.225 servidos, 426.473 gzip. Fuentes normalizadas LF según .gitattributes antes de construir. |
| `node scripts/check_frontend_syntax.cjs` | 24 archivos JavaScript, 0 fallos. |
| AST Python / JSON n8n | Sintaxis de 265 archivos Python y JSON válida; no importa ni ejecuta la aplicación. |
| JavaScript embebido n8n | Sintaxis de 8 nodos verificada con `node --check`, sin ejecutarlos. |
| `git diff --check` | Sin errores de whitespace. |
| `python -m pip check` | **Falla**: amqtt 0.12.0 pide websockets 15.0.1; instalado 17.2. Conflicto preexistente, no ocultado. |
| pytest / colección / cobertura / Playwright / hardware | **No ejecutados**, según decisión explícita del usuario. |

Los pins declarados de QA son más recientes que algunas herramientas instaladas;
los resultados anteriores identifican el entorno real. La nueva configuración
de CI queda preparada para futuras ejecuciones. El commit de esta entrega usa
`[skip ci]` para evitar activar suites con el push autorizado por AGENTS.md.

Build y validadores estáticos no prueban interoperabilidad, accesibilidad
completa, durabilidad ante corte eléctrico ni comportamiento de concurrencia.

Quedan acciones de entorno/despliegue: HTTPS para acceso remoto, entorno QA limpio
desde requisitos y eventual purga coordinada del historial Git. Una política de
egress MQTT, métricas de complejidad como gate y aceptación dinámica necesitan
alcance propio. No se instala ni se despliega esta entrega en una estación.
