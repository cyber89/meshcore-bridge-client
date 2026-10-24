# Revisión de documentación y scripts — 2026-10-23

## Alcance y base

Solicitud: comprobar que la documentación y los scripts estén actualizados.
Base: `main`, `4ea20bf8080003ea3bd5ebed2c603450052189b9`; remoto declarado
`https://github.com/cyber89/meshcore-bridge-client.git`.
Se inventarían documentos, código fuente, scripts, launchers, workflows y helpers
propios; la conciliación semántica se dirige a guías vigentes, contratos, planes
y scripts de mantenimiento. Los informes fechados y ADRs sustituidos conservan
su historia: un inventario o enlace válido no convierte sus resultados en QA
vigente. `auditoria.reporte.md` era un archivo local ajeno sin seguimiento y se
excluye de la edición y publicación.

Se delegaron áreas de edición separadas de instalación/despliegue,
arquitectura/planes y scripts/QA documental; el principal revisó diffs e integró
README, índice, procedencia, contratos F0 e inventarios.

No se ejecutaron suites pytest, Playwright o fuzzing, servicios, instaladores,
recuperación de credenciales, simulaciones ni generadores de mapas. No se leyó
`.env` activo ni se conectó a hardware, broker o estación operativa. No se
cambiaron parámetros RF, timers, notificaciones o límites de transmisión.

## Discrepancias corregidas

| Área | Hallazgo y corrección | Evidencia de implementación |
| --- | --- | --- |
| Navegación | Índice de ADRs terminaba en 0022 pese a existir hasta 0024; ADR 0019 carecía de dos secciones obligatorias. Se actualiza índice y estructura sin alterar la decisión. | `docs/adr/`, `scripts/validate_project_docs.py`. |
| Evolución | `nuevo.md` afirmaba que ninguna mejora estaba implementada; F0 citaba rutas/controladores/eventos inexistentes. Se conserva el diagnóstico original y se concilian rutas y eventos actuales. | Historial Git F0–F7, `src/web/asgi_route_catalog.py`, routers RX y `src/bridge_core.py`. |
| Arquitectura | Referencias a `BridgeCore`, `RxRouter`, `AuthService`, `external_mqtt.py` y decoder inexistentes. Se sustituyen por símbolos y archivos reales. | AST de `src/`, especialmente `bridge_core.py`, `rx_router.py`, `web/authentication.py`, `sensor_decoder.py`. |
| Persistencia | Tablas SQL ficticias y descripciones JSON/IndexedDB como autoridad. Se documentan tablas reales, SQLite autoritativo, migración JSON y caché del navegador. | DDL de `src/station_database.py` y `src/web/auth_store.py`; `src/contact_manager.py`, `src/repeater_manager.py`. |
| Perfiles | Guías prometían extras pip mínimos y checker core sin Paho. Se distingue opcionalidad runtime, perfiles de comprobación y empaquetado aditivo actual. | `pyproject.toml`, `scripts/check_runtime_dependencies.py`, `src/application/capabilities.py`. |
| Recuperación | Planes decían que el CLI no existía. Se documenta el comando implementado y sus diferencias frente al diseño propuesto. | `scripts/reset_web_password.py`, `AuthStore.recover_credentials()`. |
| Instalación | La instalación/actualización podía dejar fuera los documentos raíz; se añaden al payload, junto con herramientas de mantenimiento ausentes en instalación inicial. | `install.sh`, `scripts/staged_update.py`; lista `REQUIRED` conservada. |
| Despliegue | Ejemplo descrito como loopback escuchaba en todas las interfaces; ayuda de perfiles incompleta. Se concilian ejemplo, permisos del archivo de contraseñas y ayuda del checker. | `docs/DEPLOYMENT_GUIDE.md`, `scripts/check_runtime_dependencies.py`. |
| Scripts auxiliares | Selector obsoleto `#chatMessageInput`, generador MBTiles con ruta absoluta y sobrescritura, runner parcial presentado como completo. Se usa `#chatInputText`, salida sintética en artefactos sin sobrescritura y alcance parcial explícito. | `src/web/static/index.html`, `scripts/check_frontend_health.py`, `generate_sample_mbtiles.py`, `run_all_test_categories.py`. |
| QA documental | Inventario antiguo con resultados históricos codificados como actuales. Se regenera desde fuentes, incluye CommonJS y distingue artefactos existentes de verificaciones ejecutadas. | `scripts/inventory_verification.py`, `docs/TEST_INVENTORY.md`, `requirements-dev.txt`. |
| Mapas/visor | Se prometía interfaz completamente offline y detección automática de MBTiles; visor ASGI aún se llamaba candidato. Se documenta dependencia CDN, recarga explícita y servidor actual. | `src/web/map_tile_service.py`, `src/web/asgi_docs.py`, activos de la SPA. |
| Inventario | Snapshot anterior a los servicios F3/F4; faltaban hashes de scripts. Se amplían alcance y clasificación histórica y se regenera deliberadamente. | `scripts/inventory_project_knowledge.py`, `docs/PROJECT_INVENTORY.json`. |

## Verificación estática

Entorno: Windows PowerShell, Python 3.12.10 del PATH y herramientas locales del
proyecto. Comandos ejecutados y salida comprobada:

| Comprobación | Resultado |
| --- | --- |
| `python scripts/validate_project_docs.py` | 130 documentos/skills; 0 incidencias de estructura/enlaces locales. No comprueba anchors o URLs remotas. |
| `python .agents/skills/domain-adr-keeper/scripts/audit_domain_adr.py` | CONTEXT y 24 ADRs con secuencia y secciones válidas. |
| `ast.parse(..., feature_version=(3, 12))` sin imports de producción | 57 scripts/entrypoints Python; 0 errores de sintaxis. |
| Parser PowerShell sobre `install.ps1` | 0 errores de sintaxis. |
| Git Bash `bash -n install.sh` | Código 0; sólo parseo. El primer intento de MSYS falló por restricciones del sandbox; el mismo parseo con permiso ampliado pasó. |
| `node --check` sobre los 3 CommonJS de `scripts/` | Código 0 en los tres. |
| Ruff local sobre los 12 scripts Python modificados | `All checks passed!`. No se ejecutaron mypy ni suites. |
| `python scripts/inventory_verification.py` | 180 archivos: 139 módulos test, 3 helpers y 38 scripts Python/CommonJS; no se ejecutan escenarios. |
| `python scripts/inventory_project_knowledge.py --write` | 103 documentos, 15 referencias, 161 fuentes y 64 scripts/entrypoints, además de 22 skills propias y 8 vendors. Snapshot con HEAD de base y hashes del árbol de trabajo. |

La ejecución de estos comandos no acredita interoperabilidad, instalación en SBC
ni ausencia de vulnerabilidades. Los hashes se contrastan con disco y el diff se
comprueba antes de publicar. No se atribuyen resultados de XML históricos al
checkout actual.

## Pendientes comprobados y límites

- **Empaquetado:** `project.dependencies` todavía incluye web y Paho. Los extras
  `core`, `mqtt`, `web`, `all` no restan esas dependencias. La documentación ya no
  promete paquetes mínimos independientes.
- **Mosquitto del instalador Linux:** el bloque de creación utiliza contraseñas
  fallback fijas si falla su generación, silencia algunos fallos de
  `mosquitto_passwd`/`systemctl` y aplica `root:600` al archivo de contraseñas sin
  ajustar explícitamente lectura para el daemon. Son hallazgos estáticos previos;
  no se modificó ni ejecutó ese aprovisionamiento. El ejemplo manual de la guía
  usa `root:mosquitto` y `640`; eso no corrige automáticamente el instalador.
- **Recuperación local:** el CLI acepta contraseña por argumento, no impide el
  fallback con eco de `getpass`, no compara la generación de la cuenta tras el
  prompt y `--project-dir` por sí solo no garantiza seleccionar la configuración
  de otra instalación. La guía recomienda `--db-path` absoluto y prompt local;
  no se restableció ninguna cuenta.
- **MQTT/ledger:** la reserva existe, pero la cobertura de deduplicación no es
  universal. El tópico administrativo por repetidor evita la reserva; el handler
  general puede continuar si una reserva rechazada no tiene resultado guardado;
  ausencia/error de BD admite modo legado. No atribuir garantía exactamente una
  vez ni recuperación durable de reintentos. La retención tiene tope de 10 000
  filas; su poda permite reutilizar un identificador antiguo.
- **Scripts históricos:** varios escenarios aún usan puertos fijos o estado del
  operador. Se clasifican y documentan sus límites; no se ejecutan para demostrar
  que estén actualizados ni se convierten en fixtures mantenidas.
- **Catálogo OpenAPI:** `/api/capabilities` y `/api/services/capabilities` se
  despachan en `WebAPIRouter._dispatch_services()` y son accesibles mediante el
  fallback REST; no figuran en `ROUTE_CONTRACTS` ni en el esquema generado.
  La guía identifica la diferencia y el controlador real `ServicesController`.
- **Referencias/terceros:** las tres fuentes oficiales se consultaron en
  [firmware](https://github.com/meshcore-dev/MeshCore),
  [SDK](https://github.com/meshcore-dev/meshcore_py) y
  [CLI](https://github.com/meshcore-dev/meshcore-cli). Se releyeron SHA y estado de
  los cuatro árboles locales con Git propio; siguen limpios. No se comparó HEAD
  remoto ni se actualizaron referencias. Once copias carecen de Git propio;
  no se acredita su revisión. No se actualizan dependencias ni vendors.
- **Diagramas y registros históricos:** conservan su contexto de generación;
  para símbolos, contratos y capacidades actuales prevalecen las guías corregidas
  y el código. No se realizó aceptación visual nueva ni se recertificaron
  resultados históricos de QA.

## Publicación

La política de `AGENTS.md` autoriza commit y push a `origin/main` de los archivos
propios tras revisar el diff. El estado final de publicación se comunica en la
entrega; un push no acredita instalación ni despliegue operativo.
