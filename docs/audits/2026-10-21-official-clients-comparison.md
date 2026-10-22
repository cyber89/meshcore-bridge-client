# Comparación con los clientes oficiales MeshCore y verificación del Bridge

**Fecha de consulta:** 2026-10-21, America/New_York.

**Checkout evaluado:** `af6f2b2afd2d5f059663bd5701d41c269a32aafe`.

**Equipo:** especialistas en cliente web y arquitectura, iOS y funcionalidades, QA/protocolo, con contraste e integración del agente principal.

## 1. Resultado principal

MeshCore Bridge ofrece una estación persistente con radio bajo control del host, historial central, API, automatizaciones y proxy Companion. Los clientes oficiales resuelven principalmente la interacción del usuario con su Companion. Hay capacidades compartidas y otras complementarias; una lista de funciones no demuestra superioridad, eficiencia o estabilidad global.

La revisión encontró tres problemas funcionales concretos, reproducidos sin radio física:

1. Incoherencia entre la fragmentación de texto del compositor y el presupuesto real de canales.
2. Descarte de chat ordinario por una heurística textual de respuestas CLI antes de persistir/notificar.
3. Pérdida de `region_scope` al interpretar y volver a compartir un enlace de canal oficial.

También encontró oportunidades de producto: soporte explícito de salas ROOM/BBS, búsqueda de historial, lectura QR, borradores persistentes y avisos de segundo plano. Algunas operaciones existen en el SDK o firmware, pero eso no acredita una función completa de la aplicación.

No se implementaron correcciones, funciones nuevas ni cambios de dependencias. Se añadieron únicamente este informe y sondas/resultados locales de QA en `tests/artifacts/`, no versionados. El [plan previo](../../nuevo.md) continúa siendo una propuesta, no una descripción de mejoras ya aplicadas.

## 2. Referencias correctas y alcance de la comparación

### Cliente web oficial actual

El [repositorio de firmware oficial](https://github.com/meshcore-dev/MeshCore#-meshcore-clients) enlaza [app.meshcore.nz](https://app.meshcore.nz/). Se leyó su [version.json público](https://app.meshcore.nz/version.json): versión **1.50.0**, build **78**, aplicación `meshcore_flutter`. Las [notas oficiales](https://app.meshcore.nz/assets/CHANGELOG.md) fechan esa versión el **25 de septiembre de 2026**.

El [repositorio liamcottle/meshcore-web](https://github.com/liamcottle/meshcore-web) corresponde al cliente anterior: su README declara que dejó de actualizarse y fue sustituido por Flutter multiplataforma. No se tomó su código como implementación de la web actual. No se acreditó acceso al código fuente Flutter de la versión servida.

### Aplicación iOS oficial

La aplicación examinada documentalmente es **MeshCore**, desarrollador **Liam Cottle**, [App Store ID 6742354151](https://apps.apple.com/us/app/meshcore/id6742354151), enlazada desde [meshcore.io](https://meshcore.io/). La ficha abierta directamente mostraba **1.50.0, 25 de septiembre**; un resultado de búsqueda anterior mostraba una versión desactualizada y se descartó. **MeshCore One es otra aplicación y no fue usada como equivalente oficial.**

La [FAQ oficial](https://docs.meshcore.io/faq/#57-q-is-meshcore-open-source) distingue firmware/herramientas abiertas de las aplicaciones móviles cerradas de Liam. No había un iPhone o simulador iOS disponible: no se ejecutó la app iOS ni se verificaron sus conexiones, batería o comportamiento con pantalla bloqueada. La familia Flutter compartida no garantiza paridad entre plataformas.

### Referencias de protocolo locales

Se comprobó `.git` propio antes de atribuir revisiones:

| Referencia de sólo lectura | Revisión y procedencia |
| --- | --- |
| `reference/meshcore/` | `d92964352441e53b93e8667b802e04f6e072b39e`, origen `meshcore-dev/MeshCore`; inventariada como Companion 1.17.1. |
| `reference/meshcore_py/` | `c487efbe187f4b000020afdfc0349c4cdf503c5a`, origen `meshcore-dev/meshcore_py`. |

No se actualizaron referencias. La referencia firmware local no se presenta como última versión upstream ni como prueba de todas las funciones de firmware 1.18.

## 3. Qué se comprobó realmente

| Nivel de evidencia | Alcance |
| --- | --- |
| Observación web oficial | Pantalla inicial y opciones/herramientas anteriores a conectar radio. |
| Documentación oficial | Versiones, cambios publicados, formatos QR y protocolo. Las secciones «In Development» no se atribuyen a una release. |
| Lectura del Bridge | Rutas, frontend, adaptador SDK, persistencia, clasificación y pruebas mantenidas. |
| Ejecución del Bridge | Pruebas backend focalizadas, navegador con estación virtual y sondas de límites/QR/chat con datos sintéticos. |
| No comprobado | iOS ejecutado, radio real, enlace RF, interoperabilidad física entre el cliente oficial y el proxy, estabilidad prolongada y comparación de rendimiento en condiciones iguales. |

En la web oficial se observaron Contacts, Channels y Map; conexión BLE/USB/WIFI; y herramientas de trazado, cobertura de antena, línea de vista, RX Log, descubrimiento y ruido. Se observaron opciones, no el funcionamiento de esas herramientas con radio. En el navegador IAB utilizado, WIFI presentó «no soportado en este dispositivo»; eso no demuestra ausencia de TCP en iOS/desktop ni una limitación universal de la web. No se concedieron permisos Bluetooth/USB ni se conectó hardware.

## 4. Matriz funcional

**Leyenda:** O = opción observada; D = función documentada, no ejecutada en cliente oficial; E = Bridge ejercitado en pruebas; C = verificado por código; P = parcial/no acreditado completamente.

Las capacidades de la columna oficial proceden de las [notas de la aplicación actual](https://app.meshcore.nz/assets/CHANGELOG.md), la [ficha iOS](https://apps.apple.com/us/app/meshcore/id6742354151) y la observación descrita; no se presupone que todas las opciones sean utilizables en todas las plataformas.

### Diferencias de plataforma acreditadas

| Aspecto | Web oficial | iOS oficial | Bridge |
| --- | --- | --- | --- |
| Versión consultada | 1.50.0 build 78, metadata pública. | 1.50.0, ficha App Store. | Checkout indicado; SDK instalado no coincide con el pin. |
| Conexión a radio | Selector BLE/USB/WIFI observado; WIFI rechazado en IAB. | Bluetooth y TCP documentados; no ejecutados. | Serie/TCP desde el host; navegador consume REST/WS. |
| Avisos | Push web documentado. | Notificaciones documentadas; mecanismo y segundo plano no probados. | Sonidos y avisos con la SPA; push no acreditado. |
| Verificación dinámica de esta revisión | Sólo interfaz sin radio. | Ninguna ejecución. | Backend, navegador y sondas aisladas. |

La matriz siguiente compara capacidades de la familia oficial documentada con el Bridge. Una nota común no se convierte automáticamente en una prueba individual de web e iOS.

| Área | Oficial web/iOS | Bridge actual | Evaluación |
| --- | --- | --- | --- |
| Transporte | Web: BLE/USB/WIFI O; móvil: Bluetooth y TCP D. | Host serie/TCP C/E; navegador REST/WS. BLE no expuesto. | Arquitecturas distintas, no fallo por carecer de WebBluetooth. |
| Chat de canales y DM | D. | E: canales, aislamiento DM, render y envío virtual. | Base funcional compartida. |
| Confirmaciones | D. | C/E: correlación ACK y persistencia. | Conservar diferencia entre aceptado, enviado y entregado. |
| Historial | Búsqueda/export SQLite D. | SQLite/IndexedDB/paginación C/E; búsqueda global no encontrada. | Oportunidad local sin RF. |
| Compartir | URI/QR D. | URI/QR C; sonda detecta scope perdido. | Interoperabilidad parcial. |
| Lectura QR | Integración móvil D. | Importación por texto C; cámara no encontrada. | Añadible con vista previa y permisos explícitos. |
| Canales/scopes | D. | CRUD y scope global C; round-trip de scope incompleto. | No equiparar scope global y por canal. |
| Infraestructura/contactos | Tipos Companion/Repeater/Room/Sensor D. | Contacts sólo CLIENT; otros en Nodos C/E. | Organización intencional del proyecto. |
| ROOM/BBS | Sesión/historial/permisos D. | Administración C; apertura como DM genérico C/P. | No acreditar soporte completo de sala. |
| Sensores | Telemetría/compartición D. | Subscribe/unsubscribe y persistencia C/E. | Ya existe trabajo implementado; no confundir compartir con suscripción iOS. |
| Administración local/remota | CLI y WiFi D. | CLI, preferencias, WiFi y guardas C/E. | No proponer como ausentes funciones existentes. |
| Rutas | Herramientas O; adaptación 3B D. | Traceroute C; 3B rechazado explícitamente. | Limitación visible y segura, no ruta fabricada. |
| Diagnóstico geográfico | Cobertura/LOS/ruido O. | Mapas, trazas y sniffer C; equivalentes completos no acreditados. | Evaluar utilidad y proveedores antes de ampliar. |
| Avisos de segundo plano | Web push D. | Sonido/toasts C; infraestructura push no encontrada. | WebSocket abierto no equivale a push. |
| Estación permanente/automatización | Fuera del alcance acreditado. | SQLite central, MQTT, API y proxy C. | Valor propio del Bridge. |
| Sin Internet | Distribuciones descargables D. | Host accesible por LAN, activos y MBTiles C. | Caché de historial no acredita arranque completo sin host. |

### Evidencia local principal de la matriz

- Transporte: [selector](../../src/companion_connection.py), líneas 23–56; [SDK adapter](../../src/serial/sdk_adapter.py), 714–745. El SDK de referencia posee `create_ble`; el producto no selecciona esa ruta.
- Historial: [HistoryController](../../src/web/controllers/history_controller.py), 18–37, expone paginación, conversaciones e importación, no búsqueda textual global equivalente.
- QR: [utils.js](../../src/web/static/js/core/utils.js), 261–373; [export de canales](../../src/web/controllers/channels_controller.py), 252–301; [Settings](../../src/web/static/js/modules/settings.js), 1551–1558 y 2586–2601.
- ROOM: [tarjeta de nodos](../../src/web/static/js/modules/nodes.js), 788–791; [chat genérico](../../src/web/static/js/modules/chat.js), 1090–1110. El soporte de administración/ACL no equivale a membresía y sincronización BBS.
- Sensores: [nodos](../../src/web/static/js/modules/nodes.js), 780–827; [ejecutor](../../src/admin/repeater_executor.py), 416–552.
- Avisos: [chat.js](../../src/web/static/js/modules/chat.js), 2230–2248, usa `AudioContext`; la búsqueda en fuentes no minimizadas no encontró Service Worker/PushManager/Notification.
- Ubicación: [chat.js](../../src/web/static/js/modules/chat.js), 1144–1178, coloca coordenadas en el compositor; el usuario todavía debe enviar. El fallback de estación debe distinguirse de la posición del teléfono.

## 5. Problemas reproducidos

### F01 — El compositor y el adaptador discrepan sobre el tamaño de canal

**Clasificación:** defecto funcional de contrato UI/backend; prioridad alta para la fiabilidad de mensajería.

El compositor usa `MAX_LORA_TEXT_BYTES = 160` y fragmenta con ese valor ([utils.js](../../src/web/static/js/core/utils.js), 408/441; [chat.js](../../src/web/static/js/modules/chat.js), 1860). El adaptador descuenta el nombre UTF-8 del remitente más `": "` antes de admitir canales ([sdk_adapter.py](../../src/serial/sdk_adapter.py), 1599–1605).

La fuente [BaseChatMesh.cpp](../../reference/meshcore/src/helpers/BaseChatMesh.cpp), 487–496, confirma que el prefijo ocupa el presupuesto del mensaje grupal. No debe interpretarse el límite de un cliente como cantidad universal de caracteres.

**Sonda sintética ejecutada:** el splitter real recibe 160 caracteres ASCII y produce un bloque de 160 bytes. El adaptador real, con transporte/SDK simulado y nombre `Estacion`, produce:

| Texto | Resultado del adaptador | Llamadas SDK del caso |
| --- | --- | --- |
| 150 bytes | `SENT`, mock. | 1 |
| 151 bytes | Rechazado: excede 150 bytes. | 0 |
| 160 bytes | Rechazado: excede 150 bytes. | 0 |

Esto acredita la discrepancia entre componentes; no mide una emisión RF ni afirma fallo de todo mensaje largo. El backend evita truncar/enviar un mensaje que excede su presupuesto; el error está en presentar/fragmentar un presupuesto diferente en la UI y validarlo tan tarde.

**Recomendación:** obtener un presupuesto efectivo por operación/destino desde una política común; validar antes de encolar; recalcular al cambiar nombre/canal/configuración. Incluir las restricciones de scope que correspondan al firmware y mostrar paquetes/airtime. No fijar 150 para todos: es sólo el ejemplo de esta sonda. Mantener la guarda final del adaptador.

### F02 — Chat ordinario se pierde en persistencia y WebSocket por texto parecido a CLI

**Clasificación:** inconsistencia de clasificación y pérdida de historial/visibilidad; prioridad alta.

[RxEventRouter](../../src/rx_router.py), 1079–1091, distingue remitentes conocidos CLIENT/ROOM/SENSOR y texto normal. Pero [publish_chat_event](../../src/bridge_core.py), 179–195, vuelve a llamar `is_common_chat_message` sin ese contexto. La heurística de [rx_router.py](../../src/rx_router.py), 123–190, considera prefijos como `get ` y `set ` señales de administración aunque `txt_type=0`.

**Sonda sobre el método real `publish_chat_event`, con registro y persistencia mock:**

| Texto de usuario, tipo oficial 0 | Admitido por el método | Llamadas a persistencia |
| --- | --- | --- |
| `hello` | Sí. | 1 |
| `ok` | Sí. | 1 |
| `get home safely` | No. | 0 |
| `set de herramientas` | No. | 0 |

La referencia [MyMesh.cpp](../../reference/meshcore/examples/companion_radio/MyMesh.cpp), 432–534, diferencia texto normal y datos CLI mediante el tipo. No se ejecutó el cliente oficial con esas frases: la comparación de clasificación se sustenta en firmware y en la sonda local.

Para un remitente conocido, la ruta del router puede publicar a MQTT y después descartar persistencia/WS. Por tanto, no se afirma desaparición de toda salida: el riesgo es que los consumidores discrepen y falte historial en la estación. En emisores desconocidos hay filtrado más temprano.

**Recomendación:** una clasificación compartida basada en tipo, rol y correlación administrativa confiable, conservando protección explícita de secretos. No eliminar todas las guardas CLI ni convertir contenido suministrado por el usuario en prueba de procedencia. Añadir una regresión de extremo a extremo para mensaje normal conocido, historial, WS y MQTT.

### F03 — El round-trip de QR descarta el alcance regional

**Clasificación:** incompatibilidad parcial de importación/compartición; prioridad media.

La [especificación oficial QR](https://docs.meshcore.io/qr_codes/) permite `region_scope` opcional. Se pasó al parser real una URI sintética con ese campo; se regeneró el enlace mediante el builder real.

```text
Entrada: region_scope = #qa-local
Resultado parseado: region_scope = null/ausente
Resultado regenerado: region_scope = null/ausente
Preservación de alcance: false
```

El export de backend tampoco incluye el campo ([channels_controller.py](../../src/web/controllers/channels_controller.py), 285–295). La sonda devuelve código 1 al exigir preservación del campo: es una detección deliberada del defecto, no una prueba mantenida aprobada.

**Recomendación:** preservar y validar metadata de alcance de extremo a extremo, o advertir/rechazar el campo si la operación concreta no lo soporta. No aplicar silenciosamente un scope global para simular uno de canal, porque afectaría otras transmisiones. La importación QR no debe transmitir ni añadir sondeos por sí misma.

## 6. Diferencias que requieren desarrollo, no corrección de un bug demostrado

| Propuesta | Valor y alcance | Prioridad sugerida | Coste RF y condición |
| --- | --- | --- | --- |
| Búsqueda de historial en servidor | Buscar mensajes sin descargar todo el historial al navegador; paginar resultados. | Alta tras F01/F02. | Ninguno si sólo consulta SQLite. Revisar índices con medición. |
| Lectura QR y vista previa | Completar importación desde cámara/imagen y presentar tipo, clave y alcance. | Media-alta. | Ninguno para interpretar; confirmar antes de mutaciones o envío. |
| Borradores persistentes por conversación | Preservar texto durante recargas/cambios de vista. No confundir recuperación de un mensaje fallido con autosave completo. | Media. | Ninguno; privacidad y aislamiento por estación. |
| ROOM como capacidad explícita | Sesión de usuario, permisos de publicación/lectura, historial y sincronización. | Alta si se utilizan salas. | Login/sync pueden transmitir; checklist RF y límites acordados. Mantener ROOM en Nodos. |
| Avisos de segundo plano | Contrato de entrega y preferencias por conversación; evaluar PWA/Web Push. | Media según uso móvil. | No requiere RF adicional para avisar de RX; sí infraestructura IP, permisos y pruebas iOS específicas. No prometer APNs u offline universal. |
| Gestión manual de rutas | Exponer capacidad real, formato/multibyte y recuperación de ruta bajo demanda. | Media según operación. | Puede transmitir; sin retries o descubrimiento periódico nuevos por defecto. |
| Adaptación de trazas 3B | Mejorar explicación del rechazo actual y evaluar conversión válida. | Media-baja. | Diagnóstico RF explícito. Nunca truncar identificadores ambiguos sin comprobar colisiones. |
| Cobertura/LOS | Herramientas útiles para planificación si existe demanda. | Baja frente a mensajería. | Puede ser cálculo local; proveedores de elevación externos implican tráfico IP y privacidad de coordenadas. |
| BLE en host | Añadir transporte opcional del SDK cuando el entorno y la necesidad lo justifiquen. | Condicionada al despliegue. | Requiere validar plataforma/concurrencia; no sustituye el diseño de estación por WebBluetooth. |

La tabla sugiere prioridad, no autoriza implementar timers, límites, reintentos o notificaciones automáticas. Las cifras y políticas RF nuevas deben acordarse conforme a `AGENTS.md`.

El [traceroute actual](../../src/admin/traceroute_executor.py), 79–82, rechaza rutas de hashes de tres bytes. Es una limitación explícita y segura. El hecho de que otra app adapte una ruta no obliga a copiar la transformación sin comprobar la representación y ambigüedad. Tampoco se deben copiar defaults de intentos de envío: algunos cambios de reintentos del changelog están en desarrollo y el presupuesto RF del Bridge es propio.

## 7. Qué está bien orientado y qué optimizar

### Conservar

- Una autoridad de radio y arbitraje Companion con serialización del SDK y del proxy; no introducir MQTT entre la web y el núcleo.
- Protección de LOCAL/REPEATER y separación de Contactos frente a Nodos, aun si el cliente oficial organiza los tipos de otra manera.
- Historial central SQLite más caché por estación: tiene sentido para varios navegadores frente a una estación permanente.
- Distinción entre envío y entrega ACK; administración y configuración ya implementadas; soporte de sensores real en lugar de un botón sin backend.
- El auto-fetch de mensajes se delega al SDK ([sdk_adapter.py](../../src/serial/sdk_adapter.py), 786–787), en consonancia con el flujo [Companion documentado](https://docs.meshcore.io/companion_protocol/).

### Mejorar sin reescritura masiva

1. Unificar presupuesto de payload y clasificación de eventos antes de añadir funciones visibles. Los tres adaptadores deben producir el mismo estado observable del mensaje.
2. Validar el tamaño antes de ocupar la cola TX y registrar un error tardío; conservar validación al transmitir porque la configuración puede cambiar.
3. Consultar historial mediante cursores/consulta filtrada, no cargar toda la base en la SPA para implementar búsqueda.
4. Mantener el aislamiento RX/persistencia/fanout y perfiles opcionales propuestos en `nuevo.md`; esta comparación no demuestra que ya estén implementados.
5. Exponer capacidades y firmware mínimo: soportado por SDK, expuesto por producto y validado físicamente son estados distintos.
6. Limpiar la reproducibilidad de QA antes de declarar compatibilidad con los pins de producción; reparar fixtures y manejo Unicode del runner en una tarea específica.
7. Medir CPU, memoria, lag del event loop y latencias con la misma carga/plataforma antes de afirmar mayor eficiencia que Flutter/iOS. Los tiempos de ejecución de pytest no son un benchmark comparativo de los clientes.

## 8. Verificación ejecutada

### Entorno y limitaciones

Windows 11 AMD64, CPython **3.12.14**, entorno `.venv` existente. No se alteró la instalación. Versiones relevantes:

| Herramienta/dependencia | Instalada | Pin del proyecto |
| --- | --- | --- |
| MeshCore SDK | 2.3.15 | 2.3.17 |
| Websockets | 17.2 | 17.3 |
| Pydantic | 2.14.0 | 2.14.1 |
| Playwright | 1.62.0 | 1.64.0 |
| Mypy | 2.3.1 | 2.4.0 |
| Ruff | 0.16.3 | 0.17.1 |

FastAPI 0.143.0, Uvicorn 0.54.0, pytest 9.1.1 y Paho 2.1.0 estaban disponibles. `pip check` detectó un conflicto del entorno: `amqtt 0.12.0` exige `websockets==15.0.1`. No se atribuye ese conflicto a las dependencias de producción declaradas: `amqtt` pertenece al entorno disponible, no es una dependencia directa de producción del Bridge.

Los resultados verifican el checkout con esas versiones, no certifican el entorno exacto fijado ni una instalación real con firmware 1.18.

### Resultados

| Comprobación | Resultado | Alcance |
| --- | --- | --- |
| Pytest backend/protocolo | **370 pasan, 3 fallan**, 373 casos, 0 skips. | 20 módulos seleccionados; no suite completa. |
| Cobertura de esa selección | **44,42 %** de líneas de `src`, sin branches. | No cobertura global del proyecto; navegador ejecutado sin cobertura para evitar carreras. |
| Navegador | **18 pasan**: 1 arranque + 17 restantes. | Navegación, canales/DM, exclusiones, escape de markup y preferencias TCP desktop/móvil. |
| Mypy `--strict src` | Correcto, 87 archivos. | Versión instalada 2.3.1. |
| Ruff `check src tests scripts` | Correcto. | Versión instalada 0.16.3. |
| `pip check` | Falla. | Conflicto `amqtt`/`websockets` descrito. |
| Sonda QR real | Campo perdido, comprobación de preservación falla. | Parser/builder reales, datos sintéticos. |
| Sonda de tamaño | Incoherencia UI/adaptador reproducida. | Adaptador real, SDK mock, ningún paquete RF. |
| Sonda de chat normal | Dos frases rechazadas antes de persistir. | Método real del core, persistencia mock. |
| Bandit/fuzz/benchmarks | No ejecutados en esta selección. | No anunciar seguridad exhaustiva o eficiencia medida. |
| iOS/enlace RF real | No ejecutados. | Sin dispositivo iOS ni hardware de radio utilizado. |

### Los tres fallos de pytest

Los tres casos parametrizados de [test_tcp_official_compatibility.py](../../tests/test_tcp_official_compatibility.py), 39, crean un `SimpleNamespace` sin `rate_limiter`. [handle_tcp_companion_command](../../src/bridge_core.py), 364, accede a ese componente antes de la comprobación objetivo y falla con `AttributeError`.

Es una fixture incompleta respecto al contrato actual, no evidencia de un bypass de guardas en producción. Tampoco se cuenta como prueba aprobada: esos tres casos deben repararse y ejecutarse nuevamente. No se relajaron expectativas ni se modificó el fixture durante la auditoría.

El runner [run_quality_checks.py](../../scripts/run_quality_checks.py), 121, también falló al imprimir salida con Unicode en una consola CP1252, después de guardar el JSON. Los resultados de pytest se recuperaron del JSON/JUnit; el fallo de presentación no se ocultó como éxito del runner.

### Pruebas de navegador y aislamiento

Se ejecutaron `tests/test_e2e_playwright.py` y `tests/test_companion_connection_browser.py`. Las fixtures de [conftest.py](../../tests/conftest.py) bloquean dotenv, usan directorios temporales, adaptador virtual y puerto HTTP asignado por el SO. El propietario QA inicia sesión y cambia credenciales sólo en esa base temporal. Los mapas externos se sustituyen por fixtures neutrales; no se acredita disponibilidad ni calidad cartográfica de proveedores reales.

Se comprobaron viewports de 1920×1080 y 390×844 en los casos de conexión. No se realizó una auditoría exhaustiva de accesibilidad o rendimiento móvil. Las pruebas de preferencias TCP interceptan respuestas de configuración para verificar UI; no acreditan una conexión física TCP con iOS.

Los primeros intentos no produjeron evidencia funcional: pytest no pudo crear temporales en el sandbox y el loopback interno de asyncio quedó bloqueado. Se usaron directorios QA nuevos en el workspace y ejecución aprobada fuera del sandbox. Un caso de arranque pasó en 7,12 s; los 17 restantes, en 114,13 s. No interpretar esos tiempos como latencia de producto. Los intentos bloqueados se conservaron y no se suman como defectos de la app.

### Reproducción y evidencia local

Comandos base ejecutados con el intérprete `.venv/Scripts/python.exe`:

```text
python -m mypy --strict src
python -m ruff check src tests scripts
python -m pytest <20 módulos backend seleccionados> -ra --basetemp=<directorio QA nuevo> --junitxml=<reporte> --cov-report=xml:<reporte>
python -m pytest tests/test_e2e_playwright.py::test_e2e_page_loads_and_has_title --no-cov -q -ra -s --tb=short -o faulthandler_timeout=30 --basetemp=<directorio QA nuevo>
python -m pytest tests/test_e2e_playwright.py tests/test_companion_connection_browser.py -k 'not test_e2e_page_loads_and_has_title' --no-cov -q -ra --tb=short --basetemp=<otro directorio QA nuevo>
node tests/artifacts/official-clients-js-probe.mjs
python tests/artifacts/official-clients-channel-probe.py
```

Los placeholders resumen rutas únicas de la ejecución; no son comandos para copiar literalmente. No reutilizar `--basetemp` sobre un directorio con evidencia que se quiera conservar. La lista exacta de 20 módulos, argumentos, salida y códigos de retorno se guardó en `tests/artifacts/official-clients-pytest-run3.json`.

Evidencia local no publicada: `official-clients-summary.json`, `official-clients-environment.json`, reportes `official-clients-pytest-run3.json`/JUnit/cobertura, `official-clients-mypy.json`, `official-clients-ruff.json`, `official-clients-browser-run4.xml`, `official-clients-browser-run5.xml`, `official-clients-js-probe.json`, `official-clients-behavior-probe.log`, sondas fuente y snapshots públicos de versión/changelog. Todos bajo `tests/artifacts/`. Ningún archivo de una estación operativa forma parte de esa evidencia.

## 9. Orden recomendado de trabajo

1. Corregir F01 y F02 con regresiones observables que crucen UI/admisión/persistencia/transportes; no añadir más reintentos para ocultar un rechazo.
2. Completar o advertir el round-trip de scopes QR; mantener compatibilidad con canales sin scope y proteger secretos compartidos.
3. Reparar los tres fixtures TCP, corregir presentación Unicode del runner y repetir en un entorno de QA que coincida con los pins.
4. Priorizar búsqueda, borradores y lectura QR, que aportan valor sin tráfico RF adicional.
5. Decidir si ROOM completo y avisos móviles son requisitos del producto; diseñar sus contratos y límites antes de implementarlos.
6. Continuar la modularización y aislamiento del plan `nuevo.md`; medir antes de adoptar más procesos, otro framework o nuevas capas de mensajería.

La comparación no acredita que uno de los clientes sea globalmente más rápido o fiable. Sí acredita funciones concretas, dos incoherencias de mensajería, un defecto de round-trip y carencias de evidencia que impiden afirmar paridad completa.
